import unittest

from wb_private_api import WBPrivateAPI, routes
from wb_private_api.models import WBFeedback, WBProduct


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, *, params=None, headers=None):
        self.calls.append((url, params, headers))
        return next(self.responses)


class ClientTests(unittest.TestCase):
    def test_search_returns_products_in_page_order(self):
        session = FakeSession(
            [
                {"total": 101},
                {"metadata": {"catalog_type": "preset", "catalog_value": "preset=7"}},
                {"products": [{"id": 1}]},
                {"products": [{"id": 2}]},
            ]
        )
        catalog = WBPrivateAPI(session=session).search("Платье")
        self.assertEqual([product.id for product in catalog.products], [1, 2])
        self.assertEqual(catalog.pages, 2)
        self.assertEqual(catalog.get_position(2), 1)
        self.assertEqual([product.id for product in catalog.page(1)], [1, 2])
        self.assertEqual(session.calls[3][1]["page"], 2)

    def test_empty_search_skips_catalog_calls(self):
        session = FakeSession([{"total": 0}])
        catalog = WBPrivateAPI(session=session).search("несуществующий товар")
        self.assertEqual(catalog.pages, 0)
        self.assertEqual(catalog.products, [])
        self.assertEqual(len(session.calls), 1)

    def test_delivery_data_uses_current_product_list(self):
        session = FakeSession(
            [{"products": [{"id": 142766410, "time1": 2, "time2": 24}]}]
        )
        products = WBPrivateAPI(session=session).get_delivery_data_by_nms([142766410])
        self.assertEqual(products[0]["time2"], 24)
        self.assertEqual(session.calls[0][0], routes.PRODUCT_LIST)
        self.assertEqual(session.calls[0][1]["nm"], "142766410")

    def test_promos_return_published_panels(self):
        session = FakeSession([{"panels": [{"id": 1058385, "url": "sale"}]}])
        promos = WBPrivateAPI(session=session).get_promos()
        self.assertEqual(promos, [{"id": 1058385, "url": "sale"}])
        self.assertEqual(session.calls[0][0], routes.PROMOTION_CREATIVES)

    def test_promos_reject_unexpected_response(self):
        client = WBPrivateAPI(session=FakeSession([{"panels": {"id": 1}}]))
        with self.assertRaisesRegex(TypeError, "no panel list"):
            client.get_promos()

    def test_product_details_and_stocks(self):
        session = FakeSession(
            [
                {
                    "products": [
                        {
                            "sizes": [
                                {
                                    "price": {"product": 12300},
                                    "stocks": [{"qty": 2}, {"qty": 3}],
                                }
                            ]
                        }
                    ]
                }
            ]
        )
        product = WBProduct({"id": 142766410}, session)
        self.assertEqual(product.get_stocks(), [{"qty": 2}, {"qty": 3}])
        self.assertEqual(product.total_stocks, 5)
        self.assertEqual(product.current_price, 12300)
        self.assertEqual(session.calls[0][0], routes.PRODUCT_DETAILS)

    def test_questions_report_partial_results(self):
        session = FakeSession(
            [
                {"count": 31},
                {"questions": [{"id": index} for index in range(30)]},
                {"questions": []},
            ]
        )
        product = WBProduct({"id": 1, "imt_id": 2}, session)
        questions = product.get_questions()
        self.assertEqual(questions["totalQuestions"], 31)
        self.assertEqual(questions["fetchedQuestions"], 30)
        self.assertTrue(questions["truncated"])
        self.assertEqual(session.calls[2][1]["skip"], 30)

    def test_product_promo_uses_catalog_data_without_another_request(self):
        session = FakeSession([])
        product = WBProduct({"id": 1, "panelPromoId": 1058385}, session)
        self.assertEqual(product.get_promo()["panelPromoId"], 1058385)
        self.assertEqual(session.calls, [])

    def test_product_promo_uses_details_when_created_by_id(self):
        session = FakeSession([{"products": [{"panelPromoId": 9}]}])
        product = WBProduct({"id": 1}, session)
        self.assertEqual(product.get_promo()["panelPromoId"], 9)
        self.assertEqual(session.calls[0][0], routes.PRODUCT_DETAILS)

    def test_feedback_photos_support_current_and_legacy_responses(self):
        feedback = WBFeedback(
            {
                "photos": [
                    {"key": "6/8a8957e3-257c-4053-9776-4bcb72248491"},
                    {
                        "minSizeUri": "feedbacks/1/2/min.jpg",
                        "fullSizeUri": "feedbacks/1/2/full.jpg",
                    },
                ]
            }
        )
        self.assertEqual(
            feedback.get_photos(),
            [
                "https://feedback-06.wbbasket.ru/8a8957e3-257c-4053-9776-4bcb72248491/ms.webp",
                "https://feedbackphotos.wbstatic.net/feedbacks/1/2/min.jpg",
            ],
        )
        self.assertEqual(
            feedback.get_photos("full")[0],
            "https://feedback-06.wbbasket.ru/8a8957e3-257c-4053-9776-4bcb72248491/fs.webp",
        )

    def test_feedback_photos_reject_unsupported_size(self):
        feedback = WBFeedback({"photos": [{"key": "6/photo"}]})
        with self.assertRaisesRegex(ValueError, "size must"):
            feedback.get_photos("large")


if __name__ == "__main__":
    unittest.main()
