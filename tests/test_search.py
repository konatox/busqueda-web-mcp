import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from busqueda_web_mcp import config
from busqueda_web_mcp.search import DuckDuckGoProvider, SearchService
from busqueda_web_mcp.server import web_search


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def search(self, query, max_results):
        self.calls += 1
        return [{'title': str(i), 'url': 'https://example.com', 'snippet': 'text'} for i in range(20)]


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_results_and_cache(self):
        provider = FakeProvider()
        service = SearchService(provider)
        first = await service.search(' test ', 3)
        self.assertEqual(len(first['results']), 3)
        first['results'].clear()
        self.assertEqual(len((await service.search('test', 3))['results']), 3)
        self.assertEqual(provider.calls, 1)

    async def test_result_limits(self):
        provider = FakeProvider()
        for value in [0, -1, 9, 1000, True, 1.5, '3']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                await SearchService(provider).search('test', value)
        self.assertEqual(provider.calls, 0)

    async def test_query_validation(self):
        for query in ['', '  ', 'x' * 501, None]:
            with self.subTest(query=query), self.assertRaises(ValueError):
                await SearchService(FakeProvider()).search(query)

    async def test_cache_ttl_and_capacity(self):
        provider = FakeProvider()
        service = SearchService(provider)
        await service.search('a')
        service.cache[('a', config.DEFAULT_SEARCH_RESULTS)] = (0, [])
        with patch.object(config, 'CACHE_MAX_ENTRIES', 2):
            await service.search('a')
            self.assertEqual(provider.calls, 2)
            await service.search('b')
            await service.search('c')
        self.assertEqual(len(service.cache), 2)

    async def test_cache_disabled(self):
        provider = FakeProvider()
        service = SearchService(provider, cache_enabled=False)
        await service.search('a')
        await service.search('a')
        self.assertEqual(provider.calls, 2)
        self.assertFalse(service.cache)

    def test_duckduckgo_backend_and_cleaning(self):
        calls = []

        class FakeDDGS:
            def text(self, query, **kwargs):
                calls.append(kwargs)
                return [
                    {'title': '<b>Title</b>', 'href': 'https://example.com', 'body': '<p>Short   text</p>'},
                    {'title': 'Duplicate', 'href': 'https://example.com'},
                    {'title': 'Bad', 'href': 'javascript:alert(1)'},
                    {'title': 'Other', 'href': 'https://python.org', 'body': 'x' * 900},
                ]

        exceptions = types.ModuleType('ddgs.exceptions')
        exceptions.TimeoutException = type('TimeoutException', (Exception,), {})
        engines = types.ModuleType('ddgs.engines')
        engines.ENGINES = {'text': {'duckduckgo': object()}}
        with patch.dict(sys.modules, {'ddgs.exceptions': exceptions, 'ddgs.engines': engines}), patch('busqueda_web_mcp.search.create_ddgs', return_value=FakeDDGS()):
            rows = DuckDuckGoProvider().search('test', 2)
        self.assertEqual(calls, [{'max_results': 2, 'backend': 'duckduckgo'}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['title'], 'Title')
        self.assertEqual(rows[0]['snippet'], 'Short text')
        self.assertEqual(len(rows[1]['snippet']), 500)

    def test_unavailable_backend_never_falls_back(self):
        exceptions = types.ModuleType('ddgs.exceptions')
        exceptions.TimeoutException = type('TimeoutException', (Exception,), {})
        engines = types.ModuleType('ddgs.engines')
        engines.ENGINES = {'text': {'google': object()}}
        with patch.dict(sys.modules, {'ddgs.exceptions': exceptions, 'ddgs.engines': engines}), patch('busqueda_web_mcp.search.create_ddgs') as factory:
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                DuckDuckGoProvider().search('test', 2)
            factory.assert_not_called()

    async def test_timeout_is_clear(self):
        with patch('busqueda_web_mcp.server.search_service.search', AsyncMock(side_effect=TimeoutError('technical detail'))):
            result = await web_search('test')
        self.assertEqual(result, {'error': True, 'message': 'Request timed out'})

    async def test_service_timeout(self):
        async def fake_wait_for(awaitable, timeout):
            awaitable.close()
            raise TimeoutError
        with patch('busqueda_web_mcp.search.asyncio.wait_for', fake_wait_for), self.assertRaises(TimeoutError):
            await SearchService(FakeProvider()).search('a')
