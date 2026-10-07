import unittest
import ssl
import asyncio
import gzip
import zlib
from unittest.mock import patch

import httpx

from busqueda_web_mcp import config
from busqueda_web_mcp.fetcher import FetchError, extract_html, fetch_page
from busqueda_web_mcp.security import Target, UnsafeURL, parse_url
from busqueda_web_mcp.server import fetch_url

ORIGINAL_CLIENT = httpx.AsyncClient


class FetcherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        async def resolve(url):
            parsed = parse_url(url)
            if parsed.host in {'127.0.0.1', '10.0.0.1'}:
                raise UnsafeURL('Private IP blocked')
            return Target(parsed, '93.184.216.34')
        patcher = patch('busqueda_web_mcp.fetcher.resolve_target', resolve)
        patcher.start()
        self.addCleanup(patcher.stop)

    def mock_http(self, handler):
        return patch('busqueda_web_mcp.fetcher.httpx.AsyncClient', lambda **kwargs: ORIGINAL_CLIENT(
            **kwargs, transport=httpx.MockTransport(handler)))

    def test_html_cleanup(self):
        title, text = extract_html('''<html><title>A title</title><body><nav>Menu</nav>
        <script>evil()</script><style>bad css</style><main><h1>Heading</h1>
        <p>Useful paragraph</p><p>Useful paragraph</p><ul><li>Item <p>detail</p></li></ul></main>
        <footer>Copyright</footer></body></html>''')
        self.assertEqual(title, 'A title')
        self.assertEqual(text, 'Heading\n\nUseful paragraph\n\n- Item detail')

    async def test_truncation_and_pinning(self):
        def handler(request):
            self.assertEqual(request.url.host, '93.184.216.34')
            self.assertEqual(request.headers['host'], 'example.com')
            self.assertEqual(request.extensions['sni_hostname'], 'example.com')
            self.assertEqual(request.headers['user-agent'], 'busqueda-web-mcp/1.0')
            return httpx.Response(200, headers={'Content-Type': 'text/html'}, text='<title>T</title><p>abcdefghij</p>')
        with self.mock_http(handler):
            result = await fetch_page('https://example.com', 5)
        self.assertEqual(result, {'url': 'https://example.com', 'title': 'T', 'text': 'abcde', 'truncated': True})

    async def test_char_limit(self):
        for value in [0, -1, 30001, True, '4']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                await fetch_page('https://example.com', value)

    async def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout('private diagnostic', request=request)
        with self.mock_http(handler):
            result = await fetch_url('https://example.com')
        self.assertEqual(result['message'], 'Request timed out')
        self.assertEqual(result['text'], '')
        self.assertTrue(result['error'])

    async def test_private_redirect(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': 'http://127.0.0.1/secret'})
        with self.mock_http(handler), self.assertRaises(UnsafeURL):
            await fetch_page('https://example.com')
        self.assertEqual(len(calls), 1)

    async def test_relative_redirect_and_text(self):
        def handler(request):
            if request.url.path == '/':
                return httpx.Response(302, headers={'Location': '/final'})
            return httpx.Response(200, headers={'Content-Type': 'text/plain; charset=utf-8'}, text='Texto á')
        with self.mock_http(handler):
            result = await fetch_page('https://example.com')
        self.assertEqual(result['url'], 'https://example.com/final')
        self.assertEqual(result['text'], 'Texto á')
        self.assertFalse(result['truncated'])

    async def test_redirect_limit(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': '/again'})
        with self.mock_http(handler), self.assertRaisesRegex(FetchError, 'Too many redirects'):
            await fetch_page('https://example.com')
        self.assertEqual(len(calls), config.MAX_REDIRECTS + 1)

    async def test_content_type(self):
        for media_type in ['application/pdf', 'image/png', '', 'application/json']:
            with self.subTest(media_type=media_type), self.mock_http(lambda request: httpx.Response(200, headers={'Content-Type': media_type}, content=b'data')):
                with self.assertRaisesRegex(FetchError, 'Content-Type'):
                    await fetch_page('https://example.com')

    async def test_download_size(self):
        with patch.object(config, 'MAX_RESPONSE_BYTES', 10), self.mock_http(lambda request: httpx.Response(200, headers={'Content-Type': 'text/plain'}, text='x' * 11)):
            with self.assertRaisesRegex(FetchError, 'size limit'):
                await fetch_page('https://example.com')

    async def test_compressed_responses(self):
        for encoding, compress in [('gzip', gzip.compress), ('deflate', zlib.compress)]:
            for media_type, content, title, expected in [
                ('text/plain; charset=iso-8859-1', 'Texto á', '', 'Texto á'),
                ('text/html; charset=iso-8859-1', '<title>Título</title><p>Texto á</p>', 'Título', 'Texto á'),
            ]:
                def handler(request):
                    return httpx.Response(200, headers={
                        'Content-Type': media_type, 'Content-Encoding': encoding,
                    }, stream=httpx.ByteStream(compress(content.encode('iso-8859-1'))))
                with self.subTest(encoding=encoding, media_type=media_type), self.mock_http(handler):
                    result = await fetch_page('https://example.com')
                    self.assertEqual(result['title'], title)
                    self.assertEqual(result['text'], expected)
                    self.assertFalse(result['truncated'])

    async def test_compressed_download_limit_applies_to_decompressed_bytes(self):
        compressed = gzip.compress(b'x' * 1000)
        self.assertLess(len(compressed), 100)
        def handler(request):
            return httpx.Response(200, headers={
                'Content-Type': 'text/plain', 'Content-Encoding': 'gzip',
            }, stream=httpx.ByteStream(compressed))
        with patch.object(config, 'MAX_RESPONSE_BYTES', 100), self.mock_http(handler):
            with self.assertRaisesRegex(FetchError, 'size limit'):
                await fetch_page('https://example.com')

    async def test_http_error(self):
        with self.mock_http(lambda request: httpx.Response(403)):
            result = await fetch_url('https://example.com')
        self.assertEqual(result['message'], 'Page returned HTTP 403')

    async def test_connection_failure_tries_next_validated_address(self):
        target = Target(parse_url('https://example.com'), '2606:4700::1111',
                        ('2606:4700::1111', '93.184.216.34'))
        calls = []
        def handler(request):
            calls.append(request.url.host)
            self.assertEqual(request.headers['host'], 'example.com')
            self.assertEqual(request.extensions['sni_hostname'], 'example.com')
            if len(calls) == 1:
                raise httpx.ConnectError('Network unreachable', request=request)
            return httpx.Response(200, headers={'Content-Type': 'text/plain'}, text='Readable')
        with patch('busqueda_web_mcp.fetcher.resolve_target', return_value=target), self.mock_http(handler):
            result = await fetch_page('https://example.com')
        self.assertEqual(calls, list(target.addresses))
        self.assertEqual(result['text'], 'Readable')

    async def test_all_addresses_fail(self):
        target = Target(parse_url('https://example.com'), '8.8.8.8', ('8.8.8.8', '1.1.1.1'))
        calls = []
        def handler(request):
            calls.append(request.url.host)
            raise httpx.ConnectError('private diagnostic', request=request)
        with patch('busqueda_web_mcp.fetcher.resolve_target', return_value=target), self.mock_http(handler):
            result = await fetch_url('https://example.com')
        self.assertEqual(calls, list(target.addresses))
        self.assertEqual(result['message'], 'Could not connect to the page')

    async def test_fallback_preserves_overall_deadline(self):
        target = Target(parse_url('https://example.com'), '8.8.8.8', ('8.8.8.8', '1.1.1.1'))
        calls = []
        async def handler(request):
            calls.append(request.url.host)
            if len(calls) == 1:
                raise httpx.ConnectTimeout('private diagnostic', request=request)
            await asyncio.sleep(1)
            return httpx.Response(200, headers={'Content-Type': 'text/plain'}, text='Late')
        with patch.object(config, 'REQUEST_TIMEOUT', 0.02), patch('busqueda_web_mcp.fetcher.resolve_target', return_value=target), self.mock_http(handler):
            result = await fetch_url('https://example.com')
        self.assertEqual(calls, list(target.addresses))
        self.assertEqual(result['message'], 'Request timed out')

    async def test_http_status_does_not_retry_addresses(self):
        target = Target(parse_url('https://example.com'), '8.8.8.8', ('8.8.8.8', '1.1.1.1'))
        calls = []
        def handler(request):
            calls.append(request.url.host)
            return httpx.Response(403)
        with patch('busqueda_web_mcp.fetcher.resolve_target', return_value=target), self.mock_http(handler):
            result = await fetch_url('https://example.com')
        self.assertEqual(calls, ['8.8.8.8'])
        self.assertEqual(result['message'], 'Page returned HTTP 403')

    async def test_tls_error_is_identified(self):
        for error, message in [
            (ssl.SSLCertVerificationError('private certificate diagnostic'), "Could not verify the page's TLS certificate"),
            (ssl.SSLError('private TLS diagnostic'), 'Could not establish a secure TLS connection to the page'),
        ]:
            def handler(request):
                raise httpx.ConnectError('private diagnostic', request=request) from error
            with self.subTest(error=type(error)), self.mock_http(handler):
                result = await fetch_url('https://example.com')
            self.assertEqual(result['message'], message)
