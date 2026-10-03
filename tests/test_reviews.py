import json
import os
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException
from scrapegraph_api import api, reviews
from scrapegraph_api.models import ReviewCourseRequest, ReviewsRequest


class PublicReviewsTests(unittest.TestCase):
    url = "https://hotmart.com/es/marketplace/productos/php-test"

    def course(self):
        return ReviewCourseRequest(source="hotmart", url=self.url)

    def test_only_explicit_reviews_are_collected_and_deduplicated(self):
        body = "Faltan ejemplos prácticos sobre PDO y consultas preparadas."
        data = {"@type": "Course", "description": "Agregar proyectos sería ideal",
                "review": [{"@type": "Review", "reviewBody": body,
                            "author": "No guardar autor"}]}
        html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        html += f'<div itemprop="review"><span itemprop="reviewBody">{body}</span></div>'
        rows = reviews.parse_public_reviews(html, "hotmart", self.url)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].text, body)
        self.assertEqual(rows[0].url, self.url)
        self.assertNotIn("author", rows[0].model_dump())

    def test_marketing_description_is_not_a_review(self):
        html = '<script type="application/ld+json">{"@type":"Course","description":"Faltan proyectos prácticos"}</script>'
        self.assertEqual(reviews.parse_public_reviews(html, "hotmart", self.url), [])

    def test_access_restriction_is_reported_without_retrying(self):
        with patch.object(reviews.requests, "get", return_value=Mock(status_code=403)) as get:
            result = reviews.fetch_course_reviews(self.course())
        self.assertEqual(result.status, "blocked")
        get.assert_called_once()
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_partial_failure_preserves_other_course_results(self):
        response = Mock(status_code=200, content=b"<html/>", text="<html/>")
        second = ReviewCourseRequest(source="hotmart", url=self.url + "-2")
        with patch.object(reviews.requests, "get", side_effect=[requests.Timeout(), response]):
            results = reviews.fetch_reviews([self.course(), second])
        self.assertCountEqual([row.status for row in results], ["error", "not_exposed"])

    def test_external_url_is_rejected_before_network(self):
        course = ReviewCourseRequest(source="hotmart", url="https://attacker.example/php")
        with patch.object(reviews.requests, "get") as get:
            with self.assertRaises(ValueError):
                reviews.fetch_reviews([course])
        get.assert_not_called()

    def test_review_endpoint_requires_key(self):
        request = ReviewsRequest(courses=[self.course()])
        with patch.dict(os.environ, {"SCRAPING_API_KEY": "local-test"}):
            with self.assertRaises(HTTPException) as error:
                api.recursos_comentarios(request, x_api_key="incorrecta")
        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
