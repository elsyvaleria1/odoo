import http.server
import ipaddress
import socket
import threading
import time
from unittest.mock import Mock

import pytest
import requests

from odoo.libs import guarded_http, netguard


def _get_dns_records(*addresses):
    return [
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            0,
            "",
            (address, 443),
        )
        for address in addresses
    ]


@pytest.mark.parametrize(
    "host",
    ["1.1.1.1", "[2606:4700::1111]", "::ffff:1.1.1.1"],
)
def test_literal_addresses_do_not_consult_dns(host):
    resolver = Mock()
    addresses = netguard.get_permitted_host_addresses(
        host, 443, policy=netguard.PUBLIC_ONLY, resolver=resolver
    )
    assert addresses == (ipaddress.ip_address(host.strip("[]")),)
    resolver.assert_not_called()


def test_dns_addresses_keep_order_and_remove_duplicates():
    resolver = Mock(
        return_value=_get_dns_records("1.1.1.1", "2606:4700::1111", "1.1.1.1")
    )
    result = netguard.get_host_addresses("Guarded.Example.", 443, resolver=resolver)
    assert result == (
        ipaddress.ip_address("1.1.1.1"),
        ipaddress.ip_address("2606:4700::1111"),
    )
    resolver.assert_called_once_with("guarded.example", 443, type=socket.SOCK_STREAM)


@pytest.mark.parametrize(
    "failure", [[], OSError("dns failed"), UnicodeError("invalid dns name")]
)
def test_failed_dns_resolution_is_an_unresolvable_destination(failure):
    resolver = Mock(
        **(
            {"return_value": failure}
            if isinstance(failure, list)
            else {"side_effect": failure}
        )
    )
    with pytest.raises(netguard.UnresolvableDestination) as caught:
        netguard.get_permitted_host_addresses(
            "guarded.example", 443, policy=netguard.PUBLIC_ONLY, resolver=resolver
        )
    assert caught.value.kind == "unresolvable"


@pytest.mark.parametrize("host", ["localhost", "child.localhost", "LOCALHOST."])
def test_localhost_policy_refusal_precedes_dns(host):
    resolver = Mock(return_value=_get_dns_records("1.1.1.1"))
    with pytest.raises(netguard.DestinationRefused) as caught:
        netguard.get_permitted_host_addresses(
            host, 443, policy=netguard.PUBLIC_ONLY, resolver=resolver
        )
    assert caught.value.kind == "policy"
    resolver.assert_not_called()


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "::1",
        "::ffff:127.0.0.1",
        "64:ff9b::a9fe:a9fe",
        "2002:a9fe:a9fe::",
        "fd00:ec2::254",
        "5f00::1",
        "2001:db8::1",
    ],
)
@pytest.mark.parametrize("first", [False, True])
def test_one_forbidden_dns_address_refuses_the_entire_destination(address, first):
    records = [address, "1.1.1.1"] if first else ["1.1.1.1", address]
    resolver = Mock(return_value=_get_dns_records(*records))
    with pytest.raises(netguard.DestinationRefused, match=r"guarded\.example resolves"):
        netguard.get_permitted_host_addresses(
            "guarded.example", 443, policy=netguard.PUBLIC_ONLY, resolver=resolver
        )


def test_explicit_network_permissions_do_not_mutate_the_source_policy():
    policy = netguard.PUBLIC_ONLY.with_networks("10.20.0.0/16")
    assert netguard.get_permitted_host_addresses(
        "::ffff:10.20.1.2", 443, policy=policy
    ) == (ipaddress.ip_address("::ffff:10.20.1.2"),)
    with pytest.raises(netguard.DestinationRefused):
        netguard.get_permitted_host_addresses("10.21.1.2", 443, policy=policy)
    with pytest.raises(netguard.DestinationRefused):
        netguard.get_permitted_host_addresses(
            "10.20.1.2", 443, policy=netguard.PUBLIC_ONLY
        )
    assert netguard.PUBLIC_ONLY.networks == ()


@pytest.mark.parametrize(
    "address", ["169.254.169.254", "fd00:ec2::254", "100.100.100.200"]
)
def test_private_policy_still_refuses_metadata_addresses(address):
    with pytest.raises(netguard.DestinationRefused):
        netguard.get_permitted_host_addresses(
            address, 443, policy=netguard.PRIVATE_ALLOWED
        )


@pytest.mark.parametrize(
    ("scheme", "port"),
    [
        ("http", 80),
        ("https", 443),
        ("ws", 80),
        ("wss", 443),
        ("mqtt", 1883),
        ("mqtts", 8883),
        ("modbus", 502),
        ("ssh", 22),
        ("sftp", 22),
        ("smtp", 25),
        ("smtps", 465),
        ("imap", 143),
        ("imaps", 993),
        ("pop3", 110),
        ("pop3s", 995),
    ],
)
def test_url_endpoint_parsing_names_all_three_fields_without_dns(scheme, port):
    endpoint = netguard.parse_url_endpoint(f"{scheme}://Guarded.Example./path")
    assert endpoint == (scheme, "guarded.example", port)
    assert (endpoint.scheme, endpoint.host, endpoint.port) == tuple(endpoint)


@pytest.mark.parametrize(
    "url",
    [
        "http://",
        "file:///etc/passwd",
        "ftp://guarded.example",
        "http://1.1.1.1:0",
        "http://1.1.1.1:65536",
        "http://1.1.1.1:bad",
        "http://1.1.1.1\\@127.0.0.1",
        "http://1.1.1.1 @127.0.0.1",
        "http://1.1.1.1\n@127.0.0.1",
        "http://1.1.1.1/\x00",
    ],
)
def test_ambiguous_or_unsupported_urls_fail_before_dns(url):
    resolver = Mock()
    with pytest.raises(netguard.DestinationRefused) as caught:
        netguard.get_permitted_url_destination(
            url, policy=netguard.PUBLIC_ONLY, resolver=resolver
        )
    assert caught.value.kind == "syntax"
    resolver.assert_not_called()


def test_url_destination_contains_the_checked_address_set():
    resolver = Mock(return_value=_get_dns_records("1.1.1.1", "8.8.8.8"))
    destination = netguard.get_permitted_url_destination(
        "https://guarded.example:8443/path",
        policy=netguard.PUBLIC_ONLY,
        resolver=resolver,
    )
    assert destination == netguard.Destination(
        "https",
        "guarded.example",
        8443,
        (ipaddress.ip_address("1.1.1.1"), ipaddress.ip_address("8.8.8.8")),
    )
    resolver.assert_called_once()


def test_scheme_allowlist_and_error_redaction_are_preserved():
    with pytest.raises(netguard.DestinationRefused) as caught:
        netguard.parse_url_endpoint("https://user:secret_password@1.1.1.1:bad")
    assert "secret_password" not in str(caught.value)
    with pytest.raises(netguard.DestinationRefused):
        netguard.parse_url_endpoint("sftp://1.1.1.1", schemes=guarded_http.SCHEMES)


@pytest.fixture
def http_server():
    requests_seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests_seen.append((self.path, self.headers["Host"]))
            redirect = self.path == "/redirect"
            self.send_response(302 if redirect else 200)
            if redirect:
                self.send_header("Location", "http://169.254.169.254/metadata")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    thread.start()
    try:
        yield server.server_port, requests_seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive()


@pytest.mark.parametrize("fallback", [False, True])
def test_real_http_uses_checked_addresses_without_resolving_the_host_again(
    http_server, fallback
):
    port, requests_seen = http_server
    addresses = ["127.0.0.2", "127.0.0.1"] if fallback else ["127.0.0.1"]
    resolver = Mock(
        side_effect=[_get_dns_records(*addresses), _get_dns_records("169.254.169.254")]
    )
    policy = netguard.PUBLIC_ONLY.with_networks("127.0.0.0/8")
    with guarded_http.guarded_session(policy, resolver=resolver) as session:
        response = session.get(f"http://guarded.example:{port}/checked", timeout=(1, 1))
        assert response.status_code == 200
        assert not hasattr(response.request, "netguard_address")
    assert requests_seen == [("/checked", f"guarded.example:{port}")]
    resolver.assert_called_once()


def test_real_http_refuses_a_redirect_to_metadata_before_the_second_dial(http_server):
    port, requests_seen = http_server
    resolver = Mock(return_value=_get_dns_records("127.0.0.1"))
    policy = netguard.PUBLIC_ONLY.with_networks("127.0.0.0/8")
    with guarded_http.guarded_session(policy, resolver=resolver) as session:
        with pytest.raises(guarded_http.RefusedDestination) as caught:
            session.get(f"http://guarded.example:{port}/redirect", timeout=(1, 1))
    assert caught.value.kind == "policy"
    assert requests_seen == [("/redirect", f"guarded.example:{port}")]
    resolver.assert_called_once()


def test_dns_wait_is_bounded_and_reports_the_original_request():
    started = threading.Event()
    release = threading.Event()
    threads = []

    def resolver(*args, **kwargs):
        threads.append(threading.current_thread())
        started.set()
        if not release.wait(5):
            raise RuntimeError("test did not release DNS resolution")
        return _get_dns_records("1.1.1.1")

    adapter = guarded_http.GuardedAdapter(netguard.PUBLIC_ONLY, resolver=resolver)
    request = requests.Request("GET", "https://guarded.example").prepare()
    try:
        with pytest.raises(guarded_http.ResponseTooSlow) as caught:
            adapter._get_permitted_addresses_within_deadline(
                request, time.monotonic() + 0.01
            )
        assert started.wait(1)
        assert caught.value.request is request
    finally:
        release.set()
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
        adapter.close()
