import unittest

from wb_private_api import WBPrivateAPI, routes
from wb_private_api.models import WBProduct


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

    def test_broken_source_routes_fail_explicitly(self):
        client = WBPrivateAPI(session=FakeSession([]))
        with self.assertRaises(NotImplementedError):
            client.get_promos()
        with self.assertRaises(NotImplementedError):
            client.get_delivery_data_by_nms([142766410])

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


if __name__ == "__main__":
    unittest.main()
