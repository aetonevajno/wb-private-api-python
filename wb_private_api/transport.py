"""Browser transport for Wildberries storefront requests"""

from __future__ import annotations

import gzip
import json
import time
import zlib
from collections.abc import Callable
from importlib import import_module
from threading import RLock
from typing import Any, Self
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

_PROXY_HOSTS = frozenset(
    {
        "catalog",
        "search",
        "card",
        "suggests",
        "recom",
        "meta",
        "banners",
        "user-geo-data",
        "u-catalog",
        "u-search",
        "u-card",
        "u-suggests",
        "u-recom",
        "search-tags",
        "u-search-tags",
    }
)

_FETCH_SCRIPT = """
const url = arguments[0];
const extraHeaders = arguments[1];
const timeoutMs = arguments[2];
const done = arguments[arguments.length - 1];
const controller = new AbortController();
const timer = setTimeout(() => controller.abort(), timeoutMs);
const headers = {...extraHeaders};
const deviceId = window.localStorage.getItem('wbx__sessionID');
if (deviceId) headers.deviceid = deviceId;
fetch(url, {method: 'GET', credentials: 'same-origin', headers,
            signal: controller.signal})
  .then(async response => ({status: response.status,
                            contentType: response.headers.get('content-type') || '',
                            body: await response.text()}))
  .then(done, error => done({networkError: String(error)}))
  .finally(() => clearTimeout(timer));
"""


class WBHTTPError(Exception):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"Wildberries returned HTTP {status} for {url}")
        self.status = status
        self.url = url
        self.body = body


class WBTokenRefreshError(RuntimeError):
    """The browser did not receive a replacement anti-bot cookie"""


def _browser_driver() -> Any:
    try:
        seleniumbase = import_module("seleniumbase")
    except ImportError as error:
        raise RuntimeError(
            "Browser support is missing; install with pip install '.[browser]'"
        ) from error
    return seleniumbase.Driver(uc=True, headless=False, browser="chrome")


def _proxy_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Wildberries endpoints must use HTTPS")
    host = parsed.hostname
    if host.endswith(".wb.ru") and host[:-6] in _PROXY_HOSTS:
        return urlunsplit(
            (
                "https",
                "www.wildberries.ru",
                f"/__internal/{host[:-6]}{parsed.path}",
                parsed.query,
                parsed.fragment,
            )
        )
    return url


def _add_params(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    parsed = urlsplit(url)
    query = urlencode(params, doseq=True)
    if parsed.query:
        query = f"{parsed.query}&{query}"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _decode_response(body: str, content_type: str) -> Any:
    if "json" in content_type or body.lstrip().startswith(("{", "[")):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            if "json" in content_type:
                raise
    return body


def _read_body(response: Any) -> str:
    body = response.read()
    encoding = response.headers.get("content-encoding", "").lower()
    if encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding == "deflate":
        body = zlib.decompress(body)
    elif encoding and encoding != "identity":
        raise ValueError(f"Unsupported content encoding: {encoding}")
    return body.decode("utf-8")


class BrowserSession:
    """Run protected requests in Chrome so WB supplies its own cookie

    SeleniumBase's WebDriver is serialized by a lock. On HTTP 498 the page is
    refreshed. If the cookie does not change, a new browser is opened. A changed
    x_wbaas_token is required before retrying the request exactly once
    """

    def __init__(
        self,
        *,
        driver_factory: Callable[[], Any] = _browser_driver,
        timeout: float = 20,
        cookie_timeout: float = 20,
    ) -> None:
        self._driver_factory = driver_factory
        self._timeout = timeout
        self._cookie_timeout = cookie_timeout
        self._driver: Any | None = None
        self._lock = RLock()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._driver is not None:
                driver, self._driver = self._driver, None
                driver.quit()

    def _cookie(self) -> str | None:
        assert self._driver is not None
        cookies = self._driver.execute_cdp_cmd("Network.getAllCookies", {})
        return next(
            (
                cookie["value"]
                for cookie in cookies.get("cookies", [])
                if cookie.get("name") == "x_wbaas_token"
            ),
            None,
        )

    def _wait_for_cookie(
        self, previous: str | None = None, *, timeout: float | None = None
    ) -> str:
        deadline = time.monotonic() + (
            self._cookie_timeout if timeout is None else timeout
        )
        while time.monotonic() < deadline:
            cookie = self._cookie()
            if cookie and cookie != previous:
                return cookie
            time.sleep(0.25)
        raise WBTokenRefreshError("Wildberries did not issue a new x_wbaas_token")

    def _ensure_browser(self, previous_cookie: str | None = None) -> None:
        if self._driver is not None:
            return
        driver = self._driver_factory()
        try:
            driver.open("https://www.wildberries.ru/")
            self._driver = driver
            self._wait_for_cookie(previous_cookie)
        except BaseException:
            self._driver = None
            driver.quit()
            raise

    def _browser_get(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        assert self._driver is not None
        self._driver.set_script_timeout(self._timeout + 2)
        response = self._driver.execute_async_script(
            _FETCH_SCRIPT, url, headers, int(self._timeout * 1000)
        )
        if not isinstance(response, dict) or "networkError" in response:
            detail = (
                response.get("networkError") if isinstance(response, dict) else response
            )
            raise OSError(f"Browser request failed: {detail}")
        return response

    def _renew_cookie(self) -> None:
        previous_cookie = self._cookie()
        assert self._driver is not None
        self._driver.refresh()
        try:
            self._wait_for_cookie(previous_cookie, timeout=min(2, self._cookie_timeout))
        except WBTokenRefreshError:
            self.close()
            self._ensure_browser(previous_cookie)

    def _direct_get(self, url: str, headers: dict[str, str]) -> Any:
        request = Request(
            url, headers={"Accept": "application/json, text/plain, */*", **headers}
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = _read_body(response)
                return _decode_response(body, response.headers.get("content-type", ""))
        except HTTPError as error:
            raise WBHTTPError(error.code, url, _read_body(error)) from error

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        target = _add_params(_proxy_url(url), params)
        request_headers = headers or {}
        if urlsplit(target).hostname != "www.wildberries.ru":
            return self._direct_get(target, request_headers)

        with self._lock:
            self._ensure_browser()
            response = self._browser_get(target, request_headers)
            if response["status"] == 498:
                self._renew_cookie()
                response = self._browser_get(target, request_headers)
            status = response["status"]
            if not 200 <= status < 300:
                raise WBHTTPError(status, target, response["body"])
            return _decode_response(response["body"], response["contentType"])
