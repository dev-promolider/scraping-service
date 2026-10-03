import unittest
from unittest.mock import Mock, patch
from scrapegraph_api.official_context import official_context


class OfficialContextTests(unittest.TestCase):
    def test_documentation_is_evidence_not_measured_demand(self):
        response = Mock(status_code=200, content=b'<html><title>React</title><main>Learn how to build components and interactive interfaces with state and reusable applications.</main></html>')
        with patch('scrapegraph_api.official_context.requests.get', return_value=response):
            rows = official_context('React')
        self.assertEqual(rows[0]['kind'], 'documentation')
        self.assertEqual(rows[0]['url'], 'https://react.dev/learn')

    def test_redirect_is_not_followed_to_unverified_domain(self):
        with patch('scrapegraph_api.official_context.requests.get', return_value=Mock(status_code=302, content=b'')) as get:
            self.assertEqual(official_context('React'), [])
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
