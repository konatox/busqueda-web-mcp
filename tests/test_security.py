import socket
import unittest
from unittest.mock import patch

from busqueda_web_mcp.security import UnsafeURL, public_ip, resolve_target


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_urls(self):
        urls = [
            'http://localhost', 'http://x.localhost', 'http://127.0.0.1', 'http://127.22.3.4',
            'http://0.0.0.0', 'http://10.0.0.1', 'http://172.16.0.1', 'http://192.168.1.1',
            'http://169.254.169.254/latest/meta-data', 'http://[::1]', 'http://[fe80::1]',
            'http://[fc00::1]', 'http://[::ffff:127.0.0.1]', 'http://100.100.100.200',
            'http://224.0.0.1', 'http://192.0.2.1', 'http://metadata.google.internal',
            'file:///etc/passwd', 'ftp://example.com', 'http://user:pass@example.com',
            'http://example.com\n', 'http://[fe80::1%25eth0]', 'http://127.1', 'http://2130706433',
        ]
        # Numeric legacy hosts are resolved deterministically, without real DNS.
        def resolve(host, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))]
        with patch('socket.getaddrinfo', resolve):
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    await resolve_target(url)

    async def test_public_literal(self):
        self.assertEqual((await resolve_target('https://8.8.8.8/a')).address, '8.8.8.8')

    async def test_public_dns_and_pinned_url(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        with patch('socket.getaddrinfo', return_value=answers):
            target = await resolve_target('https://example.com:8443/a#fragment')
        self.assertEqual(str(target.connect_url), 'https://93.184.216.34:8443/a')
        self.assertEqual(target.host_header, 'example.com:8443')

    async def test_all_public_dns_addresses_are_retained(self):
        addresses = ['2606:4700::1111', '1.1.1.1', '1.1.1.1']
        answers = [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
                   for ip in addresses]
        with patch('socket.getaddrinfo', return_value=answers):
            target = await resolve_target('https://example.com')
        self.assertEqual(target.addresses, ('2606:4700::1111', '1.1.1.1'))
        self.assertEqual(target.address, '2606:4700::1111')

    async def test_mixed_dns_is_rejected(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ['8.8.8.8', '10.0.0.1']]
        with patch('socket.getaddrinfo', return_value=answers), self.assertRaises(UnsafeURL):
            await resolve_target('https://example.com')

    async def test_dns_failure(self):
        with patch('socket.getaddrinfo', side_effect=socket.gaierror), self.assertRaisesRegex(ValueError, 'resolve'):
            await resolve_target('https://example.com')

    def test_transition_and_multicast(self):
        for ip in ['64:ff9b::a00:1', '2002:0a00:0001::', '2001::1', 'ff0e::1']:
            with self.subTest(ip=ip):
                self.assertFalse(public_ip(ip))
