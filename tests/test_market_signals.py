import os
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from unittest.mock import Mock, patch

import requests
from scrapegraph_api import market_signals


class MarketSignalsTests(unittest.TestCase):
    def setUp(self):
        self.official = patch.object(market_signals, "official_context", return_value=[])
        self.official.start()
        self.addCleanup(self.official.stop)

    def test_explicit_interest_is_not_lost_when_topic_is_normalized(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(market_signals, "_google_news", return_value=[]) as news:
            result = market_signals.fetch_market_signals("Java", "PE", "aplicaciones con IA")
        news.assert_called_once_with("Java aplicaciones con IA", "PE")
        self.assertEqual(result["queryTopic"], "Java aplicaciones con IA")

    def test_short_ecosystem_query_is_preserved(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(market_signals, "_google_news", return_value=[]) as news:
            market_signals.fetch_market_signals("Java Spring Boot", "PE")
        news.assert_called_once_with("Java Spring Boot", "PE")

    def test_optional_credentials_are_not_assumed(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(market_signals.requests, "get") as get:
            self.assertIsNone(market_signals._google_trends("Python", "PE"))
            self.assertIsNone(market_signals._youtube("Python", "PE"))
        get.assert_not_called()

    def test_publication_is_not_classified_as_measured_trend(self):
        date = format_datetime(datetime.now(timezone.utc))
        xml = f'<rss><channel><item><title>Python para análisis de datos</title><link>https://news.google.com/articles/example</link><pubDate>{date}</pubDate><source>Publicación</source></item></channel></rss>'.encode()
        response = Mock(content=xml)
        with patch.object(market_signals.requests, "get", return_value=response):
            signals = market_signals._google_news("Python", "PE")
        self.assertEqual(signals[0]["kind"], "publication")
        self.assertIn("no una medición de demanda", signals[0]["context"])

    def test_partial_failure_and_missing_keys_remain_explicit(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(market_signals.requests, "get", side_effect=requests.Timeout()):
            result = market_signals.fetch_market_signals("Python", "PE")
        statuses = {item["source"]: item["status"] for item in result["sources"]}
        self.assertEqual(statuses["google_news"], "error")
        self.assertEqual(statuses["youtube"], "not_configured")
        self.assertEqual(statuses["google_trends_serpapi"], "not_configured")
        self.assertEqual(result["signals"], [])
        self.assertEqual(result["comments"], [])

    def test_entity_definitions_are_rejected(self):
        response = Mock(content=b'<!DOCTYPE rss><rss/>')
        with patch.object(market_signals.requests, "get", return_value=response):
            with self.assertRaises(ValueError):
                market_signals._google_news("Python", "PE")

    def test_ambiguous_python_news_does_not_include_snakes(self):
        date = format_datetime(datetime.now(timezone.utc))
        xml = f'<rss><channel><item><title>Florida Python Challenge captura pitones</title><link>https://news.google.com/articles/example</link><pubDate>{date}</pubDate></item></channel></rss>'.encode()
        with patch.object(market_signals.requests, "get", return_value=Mock(content=xml)):
            self.assertEqual(market_signals._google_news("Python", "PE"), [])

    def test_youtube_comments_are_viewer_opinions(self):
        signal = market_signals._signal("youtube", "Python", "https://www.youtube.com/watch?v=abcdefghijk", "video_interest", "Video")
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test"}, clear=True), patch.object(market_signals, "_google_news", return_value=[]), patch.object(market_signals, "_youtube", return_value=[signal]), patch.object(market_signals, "_json", return_value={"items": [{"snippet": {"topLevelComment": {"snippet": {"textOriginal": "Me gustaría ver ejemplos de limpieza de datos"}}}}]}):
            result = market_signals.fetch_market_signals("Python", "PE")
        self.assertEqual(result["comments"][0]["audience"], "viewer")
        self.assertEqual(result["comments"][0]["source"], "youtube")

    def test_trends_query_uses_base_topic_instead_of_full_course_promise(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(market_signals, "_google_news", return_value=[]) as news:
            result = market_signals.fetch_market_signals("Python para automatización de tareas repetitivas", "PE")
        news.assert_called_once_with("Python", "PE")
        self.assertEqual(result["queryTopic"], "Python")


if __name__ == "__main__":
    unittest.main()
