# wb-private-api-python

Библиотека получает данные с сайта Wildberries: ищет товары, показывает цены и остатки, получает отзывы, вопросы и сведения о продавцах. Это неофициальный клиент для внутреннего API сайта. За основу взят [форк `rrrublev/wb-private-api` версии 0.8.10](https://github.com/rrrublev/wb-private-api/tree/9dd14d4) проекта [Станислава Гельмана](https://github.com/glmn/wb-private-api), а код написан заново на Python.

## Что понадобится

- Python 3.11 или новее
- Google Chrome
- Доступ к интернету

Входить в аккаунт Wildberries и вручную получать токен не нужно. При первом запросе к защищённому адресу библиотека сама откроет окно Chrome.

## Установка

Откройте терминал в папке проекта и выполните:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[browser]'
```

## Первый запрос

```python
from wb_private_api import WBPrivateAPI

with WBPrivateAPI() as wb:
    catalog = wb.search("HotWheels", page_count=1)
    print("Найдено товаров:", catalog.total_products)

    if catalog.products:
        product = catalog.products[0]
        product.get_details_data()
        print("Артикул:", product.id)
        print("Цена из ответа WB:", product.current_price)
```

Сохраните пример в файл `example.py` и запустите:

```bash
.venv/bin/python example.py
```

`page_count=1` загружает одну страницу результатов. Если параметр убрать, библиотека попробует загрузить до 100 страниц, поэтому запрос может занять больше времени.

После выполнения блока `with` окно браузера закроется.

## Что умеет библиотека

- Искать товары и получать подсказки для поиска: `search`, `key_hint`
- Получать списки товаров бренда или продавца: `get_brand_catalog_page`, `get_supplier_catalog_page`
- Получать сведения о товаре: `get_list_of_products`, `WBProduct.create`, `WBProduct.get_details_data`, `WBProduct.get_stocks`
- Читать отзывы, вопросы и сведения о видео товара: `WBProduct.get_feedbacks`, `WBProduct.get_questions`, `WBProduct.get_video`
- Получать сведения о продавце: `get_supplier_info`

Остальные методы и их параметры можно посмотреть в файлах [`client.py`](https://github.com/aetonevajno/wb-private-api-python/blob/main/wb_private_api/client.py) и [`models.py`](https://github.com/aetonevajno/wb-private-api-python/blob/main/wb_private_api/models.py).

## Как работает доступ к Wildberries

Сайт выдаёт браузеру временный ключ доступа (cookie) для части запросов. Библиотека использует его автоматически и не сохраняет в файл. Если Wildberries отклонит запрос из-за устаревшего ключа, библиотека обновит страницу или откроет новое окно и повторит запрос один раз. Если это не поможет, программа покажет ошибку.

## Что пока недоступно

`get_delivery_data_by_nms` и `get_promos` вызывают `NotImplementedError`: адреса, использованные в исходном форке, вернули ошибку 404 при проверке 10 октября 2026 года. Их нужно будет подключить к новым адресам после проверки.

`get_supplier_shipment` возвращает ответ сайта как есть. Пока не подтверждено, что эти данные действительно описывают отгрузки.

Wildberries может изменить внутренний API без предупреждения. Основные запросы проверяли в браузере. Обновление ключа проверяли на смоделированной ошибке 498, но не на настоящем отказе сайта.

## Проверка

Чтобы запустить локальные тесты:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Тесты проверяют логику библиотеки на подготовленных ответах. Для них не нужен аккаунт Wildberries.
