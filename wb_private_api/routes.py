"""Storefront routes observed in rrrublev/wb-private-api 0.8.10"""

from __future__ import annotations

from datetime import UTC, datetime
from random import randrange

SEARCH = "https://search.wb.ru/exactmatch/ru/common/v18/search"
SEARCH_HINT = "https://suggests.wb.ru/suggests/api/v7/hint"
SIMILAR = "https://in-similar.wildberries.ru/"
PRODUCT_LIST = "https://card.wb.ru/cards/v4/list"
PRODUCT_DETAILS = "https://card.wb.ru/cards/v4/detail"
BRAND_CATALOG = "https://catalog.wb.ru/brands/v4/catalog"
SUPPLIER_CATALOG = "https://catalog.wb.ru/sellers/v4/catalog"
SUPPLIER_INFO = "https://static-basket-01.wbbasket.ru/vol0/data/supplier-by-id/{}.json"
SUPPLIER_SHIPMENT = "https://suppliers-shipment-2.wildberries.ru/api/v1/suppliers/{}"
FEEDBACKS = "https://feedbacks{}.wb.ru/feedbacks/v2/{}"
QUESTIONS = "https://questions.wildberries.ru/api/v1/questions"
FEEDBACK_PHOTO = "https://feedbackphotos.wbstatic.net/"
PROMOTION_CREATIVES = (
    "https://static-basket-01.wbbasket.ru/vol0/data/promotion-creatives.json"
)

PRODUCTS_PER_PAGE = 100
MAX_CATALOG_PAGES = 100
QUESTIONS_PER_PAGE = 30
MOSCOW_DEST = -1257786

# WB origin route maps, recorded in the source fork's v0.8.10 snapshot
MEDIA_BASKET_RANGES = (
    143,
    287,
    431,
    719,
    1007,
    1061,
    1115,
    1169,
    1313,
    1601,
    1655,
    1919,
    2045,
    2189,
    2405,
    2621,
    2837,
    3053,
    3269,
    3485,
    3701,
    3917,
    4133,
    4349,
    4565,
    4877,
    5189,
    5501,
    5813,
    6125,
    6437,
    6749,
    7061,
    7373,
    7685,
    7997,
    8309,
    8741,
    9173,
    9605,
    10373,
    11141,
    11909,
    12677,
    13445,
    14213,
    14981,
    15749,
    16517,
    17285,
    18053,
    18821,
    19589,
    20357,
    21125,
    21893,
    22661,
    23429,
    24197,
    24965,
    25733,
    26501,
    27269,
    28037,
    28805,
)


def basket_number(product_id: int) -> str:
    volume = product_id // 100_000
    basket = next(
        (index for index, top in enumerate(MEDIA_BASKET_RANGES, 1) if volume <= top),
        len(MEDIA_BASKET_RANGES) + 1,
    )
    return f"{basket:02d}"


def card_url(product_id: int, filename: str) -> str:
    volume = product_id // 100_000
    part = product_id // 1_000
    return (
        f"https://basket-{basket_number(product_id)}.wbbasket.ru/"
        f"vol{volume}/part{part}/{product_id}/info/{filename}"
    )


def video_url(product_id: int, kind: str = "hls", quality: str = "1440p") -> str:
    if kind not in {"hls", "mp4"}:
        raise ValueError("kind must be 'hls' or 'mp4'")
    volume = product_id % 144
    basket = volume // 12 + 1
    part = product_id // 10_000
    base = (
        f"https://videonme-basket-{basket:02d}.wbbasket.ru/"
        f"vol{volume}/part{part}/{product_id}"
    )
    if kind == "mp4":
        return f"{base}/mp4/{quality}/1.mp4"
    return f"{base}/hls/{quality}/index.m3u8"


def feedback_photo_url(key: str, size: str) -> str:
    photo_sizes = {"min": "ms", "full": "fs"}
    if size not in photo_sizes:
        raise ValueError("size must be 'min' or 'full'")
    partition, separator, photo_id = key.partition("/")
    if not separator or not partition.isdecimal() or not photo_id or "/" in photo_id:
        raise ValueError("Invalid Wildberries feedback photo key")
    return (
        f"https://feedback-{int(partition):02d}.wbbasket.ru/"
        f"{photo_id}/{photo_sizes[size]}.webp"
    )


def search_query_id() -> str:
    now = datetime.now(UTC)
    return f"qid{randrange(1 << 30)}{int(now.timestamp())}{now:%Y%m%d%H%M%S}"
