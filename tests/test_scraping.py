import json
import os
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException

from scrapegraph_api import api, multisource, scraping
from scrapegraph_api.models import MultiSourceRequest
from scrapegraph_api.providers import tech


class HotmartTests(unittest.TestCase):
    def test_failed_price_lookup_does_not_invent_zero(self):
        metadata = {
            "props": {
                "pageProps": {
                    "resultsData": {
                        "requestData": {
                            "results": [
                                {"title": "Python inicial", "description": "Curso", "offer": "abc"}
                            ]
                        }
                    }
                }
            }
        }
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(metadata)}</script>'
        response = Mock(text=html)
        with patch.object(scraping.requests, "get", return_value=response), patch.object(
            scraping.requests, "post", side_effect=requests.Timeout()
        ):
            rows = scraping.fetch_course_titles("Python", max_items=1)
        self.assertEqual(rows[0]["price"], "No disponible")

    def test_schema_change_is_not_reported_as_empty_result(self):
        with self.assertRaises(HTTPException) as error:
            scraping._parse_results('<script id="__NEXT_DATA__">{}</script>')
        self.assertEqual(error.exception.status_code, 502)

    def test_free_and_unknown_prices_are_distinct(self):
        self.assertEqual(scraping._format_price(0, "USD"), "$0.00")
        self.assertEqual(scraping._format_price(None, "USD"), "No disponible")
        self.assertEqual(scraping._format_price(19.9, "BRL"), "19.90 BRL")


class MultiSourceTests(unittest.TestCase):
    def test_tech_provider_accepts_normal_byte_html(self):
        response = Mock(
            status_code=200,
            url="https://training.linuxfoundation.org/catalog/",
            text="<html><title>Catalog</title></html>",
            content=b"<html><title>Catalog</title></html>",
        )
        with patch.object(tech.requests, "get", return_value=response):
            soup = tech._fetch("https://training.linuxfoundation.org/catalog/")
        self.assertEqual(soup.title.get_text(), "Catalog")

    def test_tech_provider_rejects_redirect_outside_official_domains(self):
        response = Mock(
            status_code=200,
            url="https://attacker.example/catalog/",
            text="<html><title>Catalog</title></html>",
            content=b"<html><title>Catalog</title></html>",
        )
        with patch.object(tech.requests, "get", return_value=response):
            with self.assertRaises(tech.CatalogBlocked):
                tech._fetch("https://training.linuxfoundation.org/catalog/")

    def test_linux_price_does_not_infer_currency_from_dollar_symbol(self):
        self.assertEqual(tech._observed_card_price("Kubernetes Fundamentals $299"), "$299")
        self.assertEqual(
            tech._observed_card_price("Course $299, original $399"), "No disponible"
        )

    def test_at_least_ten_sources_are_registered(self):
        self.assertGreaterEqual(len(multisource.available_adapters()), 10)

    def test_multisource_requires_its_own_key(self):
        request = MultiSourceRequest(topic="Python", platforms=["hotmart"])
        with patch.dict(os.environ, {"SCRAPING_API_KEY": "correcta"}):
            with self.assertRaises(HTTPException) as error:
                api.recursos_multifuente(request, x_api_key="incorrecta")
        self.assertEqual(error.exception.status_code, 401)

    def test_one_failed_source_preserves_other_results(self):
        def success(topic, max_items):
            return [{"title": "Python", "description": "Introduccion", "price": "No disponible", "url": "https://www.dataquest.io/course/python/"}]

        def failure(topic, max_items):
            raise requests.Timeout("timeout")

        with patch.object(
            multisource,
            "available_adapters",
            return_value={"dataquest": success, "linux_foundation": failure},
        ):
            result = multisource.search_catalogs(
                "Python", ["dataquest", "linux_foundation"], 1
            )
        self.assertEqual(len(result.courses), 1)
        self.assertEqual([item.status for item in result.sources], ["ok", "error"])

    def test_rejects_a_link_outside_the_official_site(self):
        def unsafe(topic, max_items):
            return [{"title": "Python", "url": "https://dataquest.io.attacker.test/course/x"}]

        with patch.object(multisource, "available_adapters", return_value={"dataquest": unsafe}):
            result = multisource.search_catalogs("Python", ["dataquest"], 1)
        self.assertEqual(result.sources[0].status, "error")
        self.assertEqual(result.courses, [])

    def test_catalog_error_containing_rejection_word_is_not_a_block(self):
        def changed_schema(topic, max_items):
            raise ValueError("Pluralsight rechazó la consulta por cambio de esquema")

        with patch.object(
            multisource,
            "available_adapters",
            return_value={"pluralsight": changed_schema},
        ), patch.object(multisource, "_pause") as pause:
            result = multisource.search_catalogs("Python", ["pluralsight"], 1)

        self.assertEqual(result.sources[0].status, "error")
        pause.assert_not_called()

    def test_http_429_marks_source_blocked_and_pauses_it(self):
        error = requests.HTTPError("rate limited")
        error.response = Mock(status_code=429)

        def rate_limited(topic, max_items):
            raise error

        with patch.object(
            multisource,
            "available_adapters",
            return_value={"dataquest": rate_limited},
        ), patch.object(multisource, "_pause") as pause:
            result = multisource.search_catalogs("Python", ["dataquest"], 1)

        self.assertEqual(result.sources[0].status, "blocked")
        pause.assert_called_once_with("dataquest")


if __name__ == "__main__":
    unittest.main()
