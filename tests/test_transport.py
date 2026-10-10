import gzip
import io
import json
import unittest
from email.message import Message

from wb_private_api.transport import (
    BrowserSession,
    WBHTTPError,
    WBTokenRefreshError,
    _proxy_url,
    _read_body,
)


class FakeDriver:
    def __init__(self, responses, *, replacement="new-token"):
        self.responses = iter(responses)
        self.cookie = "old-token"
        self.replacement = replacement
        self.refreshes = 0
        self.requests = []
        self.closed = False

    def open(self, url):
        self.opened = url

    def execute_cdp_cmd(self, command, params):
        return {"cookies": [{"name": "x_wbaas_token", "value": self.cookie}]}

    def set_script_timeout(self, seconds):
        self.script_timeout = seconds

    def execute_async_script(self, script, url, headers, timeout):
        self.requests.append((url, headers))
        return next(self.responses)

    def refresh(self):
        self.refreshes += 1
        self.cookie = self.replacement

    def quit(self):
        self.closed = True


def reply(status, body):
    return {
        "status": status,
        "contentType": "application/json",
        "body": json.dumps(body),
    }


class BrowserSessionTests(unittest.TestCase):
    def test_gzipped_cdns_are_decoded(self):
        response = io.BytesIO(gzip.compress(b'{"feedbacks": []}'))
        response.headers = Message()
        response.headers["content-encoding"] = "gzip"
        self.assertEqual(_read_body(response), '{"feedbacks": []}')

    def test_498_refreshes_cookie_and_replays_once(self):
        driver = FakeDriver(
            [reply(498, {"error": "INVALID_TOKEN"}), reply(200, {"total": 42})]
        )
        with BrowserSession(
            driver_factory=lambda: driver, cookie_timeout=0.05
        ) as session:
            response = session.get(
                "https://search.wb.ru/exactmatch/ru/common/v18/search",
                params={"query": "платье"},
            )
        self.assertEqual(response["total"], 42)
        self.assertEqual(driver.refreshes, 1)
        self.assertEqual(len(driver.requests), 2)
        self.assertIn("/__internal/search/", driver.requests[0][0])
        self.assertTrue(driver.closed)

    def test_second_498_raises_without_another_refresh(self):
        driver = FakeDriver([reply(498, {}), reply(498, {})])
        with (
            BrowserSession(
                driver_factory=lambda: driver, cookie_timeout=0.05
            ) as session,
            self.assertRaises(WBHTTPError) as raised,
        ):
            session.get("https://search.wb.ru/exactmatch/ru/common/v18/search")
        self.assertEqual(raised.exception.status, 498)
        self.assertEqual(driver.refreshes, 1)

    def test_404_does_not_refresh(self):
        driver = FakeDriver([reply(404, {})])
        with (
            BrowserSession(driver_factory=lambda: driver) as session,
            self.assertRaises(WBHTTPError) as raised,
        ):
            session.get("https://search.wb.ru/exactmatch/ru/common/v18/search")
        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(driver.refreshes, 0)

    def test_unchanged_cookie_is_reported(self):
        driver = FakeDriver([reply(498, {})], replacement="old-token")
        with (
            BrowserSession(
                driver_factory=lambda: driver, cookie_timeout=0.05
            ) as session,
            self.assertRaises(WBTokenRefreshError),
        ):
            session.get("https://search.wb.ru/exactmatch/ru/common/v18/search")

    def test_unchanged_cookie_restarts_browser(self):
        old_driver = FakeDriver([reply(498, {})], replacement="old-token")
        new_driver = FakeDriver([reply(200, {"total": 7})])
        new_driver.cookie = "another-token"
        drivers = iter([old_driver, new_driver])
        with BrowserSession(
            driver_factory=lambda: next(drivers), cookie_timeout=0.05
        ) as session:
            response = session.get(
                "https://search.wb.ru/exactmatch/ru/common/v18/search"
            )
        self.assertEqual(response["total"], 7)
        self.assertTrue(old_driver.closed)
        self.assertTrue(new_driver.closed)

    def test_only_known_proxy_hosts_are_rewritten(self):
        self.assertEqual(
            _proxy_url("https://card.wb.ru/cards/v4/detail"),
            "https://www.wildberries.ru/__internal/card/cards/v4/detail",
        )
        self.assertEqual(
            _proxy_url("https://feedbacks1.wb.ru/feedbacks/v2/10"),
            "https://feedbacks1.wb.ru/feedbacks/v2/10",
        )


if __name__ == "__main__":
    unittest.main()
