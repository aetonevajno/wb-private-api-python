"""Python interface to the tested Wildberries storefront methods"""

from __future__ import annotations

import math
from typing import Any, Self

from . import routes
from .models import Getter, WBCatalog, WBProduct
from .transport import BrowserSession


class WBPrivateAPI:
    def __init__(
        self,
        destination: int = routes.MOSCOW_DEST,
        *,
        session: Getter | None = None,
    ) -> None:
        self.destination = destination
        if session is None:
            self._owned_session: BrowserSession | None = BrowserSession()
            self.session: Getter = self._owned_session
        else:
            self._owned_session = None
            self.session = session

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owned_session is not None:
            self._owned_session.close()

    def _products(self, raw_products: list[dict[str, Any]]) -> list[WBProduct]:
        return [
            WBProduct(product, self.session, self.destination)
            for product in raw_products
        ]

    @staticmethod
    def get_page_count(total_products: int) -> int:
        return min(
            math.ceil(max(total_products, 0) / routes.PRODUCTS_PER_PAGE),
            routes.MAX_CATALOG_PAGES,
        )

    def search_total_products(self, keyword: str) -> int:
        response = self.session.get(
            routes.SEARCH,
            params={
                "appType": 1,
                "curr": "rub",
                "locale": "ru",
                "lang": "ru",
                "dest": self.destination,
                "query": keyword,
                "resultset": "catalog",
                "limit": 0,
            },
            headers={"x-queryid": routes.search_query_id()},
        )
        return response.get("total", 0)

    def get_query_metadata(
        self,
        keyword: str,
        *,
        limit: int = 0,
        page: int = 1,
        suppress_spellcheck: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "appType": 1,
            "curr": "rub",
            "dest": self.destination,
            "query": keyword,
            "resultset": "catalog",
            "sort": "popular",
            "spp": 30,
            "suppressSpellcheck": str(suppress_spellcheck).lower(),
        }
        if page != 1:
            params["page"] = page
        if limit != 100:
            params["limit"] = limit
        response = self.session.get(
            routes.SEARCH,
            params=params,
            headers={"x-queryid": routes.search_query_id()},
        )
        metadata = response.get("metadata") or {}
        if "catalog_type" in metadata and "catalog_value" in metadata:
            return {
                **metadata,
                "products": (response.get("data") or {}).get(
                    "products", response.get("products", [])
                ),
            }
        if "shardKey" in response and "query" in response:
            return {
                "catalog_type": response["shardKey"],
                "catalog_value": response["query"],
                "products": [],
            }
        return {"catalog_type": None, "catalog_value": None, "products": []}

    def get_catalog_page(
        self,
        keyword: str,
        page: int = 1,
        filters: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "appType": 1,
            "curr": "rub",
            "dest": self.destination,
            "query": keyword.lower(),
            "resultset": "catalog",
            "sort": "popular",
            "spp": 30,
            "suppressSpellcheck": "false",
        }
        if page != 1:
            params["page"] = page
        for filter_value in filters or []:
            params[filter_value["type"]] = filter_value["value"]
        response = self.session.get(
            routes.SEARCH,
            params=params,
            headers={"x-queryid": routes.search_query_id()},
        )
        if (response.get("metadata") or {}).get("catalog_value") == "preset=11111111":
            raise ValueError("Wildberries returned an invalid catalog preset")
        products = (response.get("data") or {}).get(
            "products", response.get("products")
        )
        if not isinstance(products, list):
            raise TypeError("Wildberries search response has no product list")
        return products

    def search(
        self,
        keyword: str,
        page_count: int = 0,
        filters: list[dict[str, str]] | None = None,
    ) -> WBCatalog:
        if not keyword.strip():
            raise ValueError("keyword must not be empty")
        if page_count < 0:
            raise ValueError("page_count must be nonnegative")
        total = self.search_total_products(keyword)
        if total == 0:
            return WBCatalog([], 0, 0)
        metadata = self.get_query_metadata(keyword)
        pages = self.get_page_count(total)
        if page_count:
            pages = min(pages, page_count)
        raw_products = [
            product
            for page in range(1, pages + 1)
            for product in self.get_catalog_page(keyword, page, filters)
        ]
        return WBCatalog(
            self._products(raw_products),
            pages,
            total,
            metadata["catalog_type"],
            metadata["catalog_value"],
        )

    def search_custom_filters(self, keyword: str, filters: list[str]) -> dict[str, Any]:
        response = self.session.get(
            routes.SEARCH,
            params={
                "appType": 1,
                "curr": "rub",
                "dest": self.destination,
                "lang": "ru",
                "query": keyword,
                "resultset": "filters",
                "sort": "popular",
                "filters": ";".join(filters),
            },
            headers={"x-queryid": routes.search_query_id()},
        )
        return response.get("data") or {}

    def key_hint(self, query: str) -> dict[str, Any]:
        return self.session.get(
            routes.SEARCH_HINT,
            params={
                "query": query,
                "gender": "common",
                "locale": "ru",
                "lang": "ru",
                "appType": 1,
            },
        )

    def search_similar_by_nm(self, product_id: int) -> list[Any]:
        return self.session.get(routes.SIMILAR, params={"nm": product_id})

    def get_list_of_products(self, product_ids: list[int]) -> list[dict[str, Any]]:
        response = self.session.get(
            routes.PRODUCT_LIST,
            params={
                "appType": 1,
                "dest": self.destination,
                "curr": "rub",
                "lang": "ru",
                "nm": ";".join(map(str, product_ids)),
            },
        )
        return (response.get("data") or {}).get(
            "products", response.get("products", [])
        )

    def get_delivery_data_by_nms(self, product_ids: list[int]) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "The source fork's /cards/list delivery route returned HTTP 404 in live checks"
        )

    def get_promos(self) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "The source fork's /webapi/settings/promo/get route returned HTTP 404 in live checks"
        )

    def get_brand_product_count(self, brand_id: int) -> int:
        response = self.session.get(
            routes.BRAND_CATALOG,
            params={
                "appType": 1,
                "curr": "rub",
                "dest": self.destination,
                "brand": brand_id,
                "limit": 0,
            },
        )
        return response.get("total", 0)

    def get_brand_catalog(self, brand_id: int, page: int = 1) -> dict[str, Any]:
        return self.session.get(
            routes.BRAND_CATALOG,
            params={
                "appType": 1,
                "curr": "rub",
                "dest": self.destination,
                "lang": "ru",
                "page": page,
                "sort": "popular",
                "spp": 30,
                "brand": brand_id,
            },
        )

    def get_brand_catalog_page(
        self, brand_id: int, page: int = 1
    ) -> list[dict[str, Any]]:
        response = self.get_brand_catalog(brand_id, page)
        return (response.get("data") or {}).get(
            "products", response.get("products", [])
        )

    def get_supplier_info(self, seller_id: int) -> dict[str, Any]:
        return self.session.get(routes.SUPPLIER_INFO.format(seller_id))

    def get_supplier_shipment(self, seller_id: int) -> dict[str, Any]:
        return self.session.get(
            routes.SUPPLIER_SHIPMENT.format(seller_id),
            headers={"x-client-name": "site"},
        )

    def get_supplier_product_count(self, supplier_id: int) -> int:
        response = self.session.get(
            routes.SUPPLIER_CATALOG,
            params={
                "appType": 1,
                "curr": "rub",
                "dest": self.destination,
                "supplier": supplier_id,
                "limit": 0,
            },
        )
        return response.get("total", 0)

    def get_supplier_catalog(self, supplier_id: int, page: int = 1) -> dict[str, Any]:
        return self.session.get(
            routes.SUPPLIER_CATALOG,
            params={
                "appType": 1,
                "curr": "rub",
                "dest": self.destination,
                "lang": "ru",
                "page": page,
                "sort": "popular",
                "spp": 30,
                "supplier": supplier_id,
            },
        )

    def get_supplier_catalog_page(
        self, supplier_id: int, page: int = 1
    ) -> list[dict[str, Any]]:
        response = self.get_supplier_catalog(supplier_id, page)
        return (response.get("data") or {}).get(
            "products", response.get("products", [])
        )

    def get_supplier_catalog_all(
        self, supplier_id: int, page_count: int = 0
    ) -> WBCatalog:
        if page_count < 0:
            raise ValueError("page_count must be nonnegative")
        total = self.get_supplier_product_count(supplier_id)
        pages = self.get_page_count(total)
        if page_count:
            pages = min(pages, page_count)
        raw_products = [
            product
            for page in range(1, pages + 1)
            for product in self.get_supplier_catalog_page(supplier_id, page)
        ]
        return WBCatalog(
            self._products(raw_products),
            pages,
            total,
            "supplier",
            f"supplier={supplier_id}",
        )
