"""Catalog and product values returned by the storefront client"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import routes


class Getter(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any: ...


@dataclass
class WBFeedback:
    raw: dict[str, Any]

    def get_photos(self, size: str = "min") -> list[str]:
        if size not in {"min", "full"}:
            raise ValueError("size must be 'min' or 'full'")
        field_name = f"{size}SizeUri"
        photo_urls = []
        for photo in self.raw.get("photos") or []:
            if photo.get("key"):
                photo_urls.append(routes.feedback_photo_url(photo["key"], size))
            elif photo.get(field_name):
                photo_urls.append(routes.FEEDBACK_PHOTO + photo[field_name])
        return photo_urls


@dataclass
class WBQuestion:
    raw: dict[str, Any]


@dataclass
class WBProduct:
    raw: dict[str, Any]
    session: Getter = field(repr=False)
    destination: int = routes.MOSCOW_DEST
    card: dict[str, Any] = field(default_factory=dict)
    seller: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] | None = None
    total_questions: int | None = None

    @property
    def id(self) -> int:
        return int(self.raw["id"])

    @classmethod
    def create(
        cls, product_id: int, session: Getter, destination: int = routes.MOSCOW_DEST
    ) -> WBProduct:
        product = cls({"id": product_id}, session, destination)
        product.get_product_data()
        product.get_details_data()
        product.get_seller_data()
        product.get_questions_count()
        return product

    def get_product_data(self) -> dict[str, Any]:
        self.card = self.session.get(routes.card_url(self.id, "ru/card.json"))
        return self.card

    def get_seller_data(self) -> dict[str, Any]:
        self.seller = self.session.get(routes.card_url(self.id, "sellers.json"))
        return self.seller

    def get_details_data(self) -> dict[str, Any] | None:
        response = self.session.get(
            routes.PRODUCT_DETAILS,
            params={
                "appType": 1,
                "curr": "rub",
                "dest": self.destination,
                "spp": 30,
                "lang": "ru",
                "nm": self.id,
            },
        )
        self.details = next(iter(response.get("products", [])), None)
        return self.details

    @property
    def current_price(self) -> int | None:
        sizes = (self.details or {}).get("sizes") or []
        if not sizes:
            return None
        price = sizes[0].get("price")
        return price.get("product") if isinstance(price, dict) else None

    @property
    def total_stocks(self) -> int:
        sizes = (self.details or {}).get("sizes") or []
        return (
            sum(stock.get("qty", 0) for stock in sizes[0].get("stocks", []))
            if sizes
            else 0
        )

    def get_stocks(self) -> list[dict[str, Any]]:
        if self.details is None:
            self.get_details_data()
        sizes = (self.details or {}).get("sizes") or []
        return sizes[0].get("stocks", []) if sizes else []

    def get_promo(self) -> dict[str, Any]:
        if "panelPromoId" in self.raw:
            promo_source = self.raw
        else:
            if self.details is None:
                self.get_details_data()
            promo_source = self.details or {}
        if "panelPromoId" not in promo_source:
            return {"active": False}
        return {
            "active": True,
            "panelPromoId": promo_source["panelPromoId"],
            "promoTextCard": promo_source.get("promoTextCard"),
            "promoTextCat": promo_source.get("promoTextCat"),
        }

    def get_feedbacks(self) -> list[WBFeedback]:
        imt_id = self.raw.get("imt_id") or self.card.get("imt_id")
        if not imt_id:
            return []
        crc = 0
        number = int(imt_id)
        for _ in range(8):
            crc ^= number & 0xFF
            number >>= 8
            for _ in range(8):
                crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
        partition = 2 if crc % 100 >= 50 else 1
        response = self.session.get(routes.FEEDBACKS.format(partition, imt_id))
        return [WBFeedback(feedback) for feedback in response.get("feedbacks", [])]

    def get_questions_count(self) -> int:
        imt_id = self.raw.get("imt_id") or self.card.get("imt_id")
        if not imt_id:
            self.total_questions = 0
            return 0
        response = self.session.get(
            routes.QUESTIONS, params={"imtId": imt_id, "onlyCount": "true"}
        )
        self.total_questions = response.get("count", 0)
        return self.total_questions

    def get_questions(self) -> dict[str, Any]:
        count = (
            self.total_questions
            if self.total_questions is not None
            else self.get_questions_count()
        )
        imt_id = self.raw.get("imt_id") or self.card.get("imt_id")
        questions: list[WBQuestion] = []
        for page in range(math.ceil(count / routes.QUESTIONS_PER_PAGE)):
            response = self.session.get(
                routes.QUESTIONS,
                params={
                    "imtId": imt_id,
                    "skip": page * routes.QUESTIONS_PER_PAGE,
                    "take": routes.QUESTIONS_PER_PAGE,
                },
            )
            page_questions = response.get("questions", [])
            if not page_questions:
                break
            questions.extend(WBQuestion(question) for question in page_questions)
        return {
            "items": questions,
            "totalQuestions": count,
            "fetchedQuestions": len(questions),
            "truncated": len(questions) < count,
        }

    def get_video(self, quality: str = "1440p") -> dict[str, Any]:
        view_flags = (self.details or {}).get("viewFlags")
        media = self.card.get("media")
        if view_flags is not None:
            has_video = bool(view_flags & 16)
        else:
            has_video = (
                bool(media.get("has_video")) if isinstance(media, dict) else False
            )
        if not has_video:
            return {"hasVideo": False}
        playlist_url = routes.video_url(self.id, "hls", quality)
        playlist = self.session.get(playlist_url)
        durations = [
            float(value) for value in re.findall(r"#EXTINF:([\d.]+)", playlist)
        ]
        return {
            "hasVideo": True,
            "quality": quality,
            "playlistUrl": playlist_url,
            "duration": round(sum(durations)),
            "chunks": len(durations),
            "hls": [
                playlist_url.replace("index.m3u8", f"{index}.ts")
                for index in range(1, len(durations) + 1)
            ],
            "mp4Preview": routes.video_url(self.id, "mp4", "360p"),
        }


@dataclass
class WBCatalog:
    products: list[WBProduct]
    pages: int
    total_products: int
    catalog_type: str | None = None
    catalog_value: str | None = None

    def page(self, number: int) -> list[WBProduct]:
        if not isinstance(number, int) or number < 1:
            return []
        start = (number - 1) * routes.PRODUCTS_PER_PAGE
        return self.products[start : start + routes.PRODUCTS_PER_PAGE]

    def get_position(self, product_id: int) -> int:
        return next(
            (
                index
                for index, product in enumerate(self.products)
                if product.id == product_id
            ),
            -1,
        )
