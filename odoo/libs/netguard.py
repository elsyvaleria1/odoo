from __future__ import annotations

import dataclasses
import enum
import ipaddress
import re
import socket
import typing

from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

from odoo.libs.redact import mask_url

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
    IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
    Resolver = Callable[..., Sequence[tuple[typing.Any, ...]]]

__all__ = [
    "LOCAL_SCOPES",
    "PRIVATE_ALLOWED",
    "PUBLIC_ONLY",
    "TIMEOUTS_PASSED_OVER",
    "Destination",
    "DestinationRefused",
    "Policy",
    "RefusalKind",
    "Scope",
    "UnresolvableDestination",
    "check_host",
    "check_url",
    "check_url_syntax",
    "classify",
    "classify_peer",
    "dial",
    "resolve",
]


class Scope(enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SHARED = "shared"
    LOOPBACK = "loopback"
    LINK_LOCAL = "link_local"
    METADATA = "metadata"
    MULTICAST = "multicast"
    UNSPECIFIED = "unspecified"
    RESERVED = "reserved"


RefusalKind = typing.Literal["policy", "unresolvable", "syntax"]


class DestinationRefused(ValueError):
    kind: RefusalKind = "policy"

    def __init__(self, *args: object, kind: RefusalKind | None = None) -> None:
        super().__init__(*args)
        if kind is not None:
            self.kind = kind


class UnresolvableDestination(DestinationRefused):
    kind: RefusalKind = "unresolvable"


_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
        "fec0::/10",
        "64:ff9b:1::/48",
    )
)
_SHARED_NETWORK = ipaddress.ip_network("100.64.0.0/10")
_SRV6_SIDS = ipaddress.ip_network("5f00::/16")
_NAT64_WELL_KNOWN = ipaddress.ip_network("64:ff9b::/96")
_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")
_IPV4_TRANSLATED = ipaddress.ip_network("::ffff:0:0:0/96")
_NAT64_LOCAL_USE = ipaddress.ip_network("64:ff9b:1::/48")
_METADATA_ADDRESSES = frozenset(
    ipaddress.ip_address(address)
    for address in (
        "169.254.169.254",
        "169.254.170.2",
        "169.254.170.23",
        "fd00:ec2::254",
        "fd00:ec2::23",
        "100.100.100.200",
        "169.254.0.23",
        "168.63.129.16",
    )
)


def _as_address(address: str | IPAddress) -> IPAddress:
    if isinstance(address, str):
        return ipaddress.ip_address(address.strip("[]"))
    return address


def _unwrap(address: IPAddress) -> IPAddress:
    if isinstance(address, ipaddress.IPv4Address):
        return address
    if address.scope_id is not None:
        address = ipaddress.IPv6Address(address.packed)
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address in _NAT64_WELL_KNOWN:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    if address.sixtofour is not None:
        return address.sixtofour
    if address.teredo is not None:
        return address.teredo[1]
    return address


def classify(address: str | IPAddress) -> Scope:
    return _classify_ip(_unwrap(_as_address(address)))


LOCAL_SCOPES = frozenset(
    {Scope.LOOPBACK, Scope.PRIVATE, Scope.SHARED, Scope.LINK_LOCAL}
)


def classify_peer(address: str | IPAddress | None) -> Scope | None:
    if not address:
        return None
    try:
        ip = _as_address(address)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.scope_id is not None:
            ip = ipaddress.IPv6Address(ip.packed)
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
    return _classify_ip(ip)


def _classify_ip(ip: IPAddress) -> Scope:
    if ip in _METADATA_ADDRESSES or (
        ip in _NAT64_LOCAL_USE
        and ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF) in _METADATA_ADDRESSES
    ):
        return Scope.METADATA
    if ip.is_unspecified:
        return Scope.UNSPECIFIED
    if ip.is_loopback:
        return Scope.LOOPBACK
    if ip.is_link_local:
        return Scope.LINK_LOCAL
    if ip.is_multicast:
        return Scope.MULTICAST
    if ip in _SHARED_NETWORK:
        return Scope.SHARED
    if any(ip in network for network in _PRIVATE_NETWORKS):
        return Scope.PRIVATE
    if ip.version == 6 and (
        ip in _IPV4_COMPATIBLE or ip in _IPV4_TRANSLATED or ip in _SRV6_SIDS
    ):
        return Scope.RESERVED
    if ip.is_global:
        return Scope.PUBLIC
    return Scope.RESERVED


@dataclasses.dataclass(frozen=True, slots=True)
class Policy:
    name: str
    scopes: frozenset[Scope]
    networks: tuple[IPNetwork, ...] = ()

    def permits(self, address: str | IPAddress) -> bool:
        ip = _as_address(address)
        if classify(ip) in self.scopes:
            return True
        unwrapped = _unwrap(ip)
        return any(
            candidate.version == network.version and candidate in network
            for network in self.networks
            for candidate in {ip, unwrapped}
        )

    def with_networks(self, *networks: str | IPNetwork) -> Policy:
        parsed = tuple(ipaddress.ip_network(network) for network in networks)
        return dataclasses.replace(self, networks=self.networks + parsed)


PUBLIC_ONLY = Policy("public_only", frozenset({Scope.PUBLIC}))
PRIVATE_ALLOWED = Policy(
    "private_allowed",
    frozenset(
        {
            Scope.PUBLIC,
            Scope.PRIVATE,
            Scope.SHARED,
            Scope.LOOPBACK,
            Scope.LINK_LOCAL,
        }
    ),
)


@dataclasses.dataclass(frozen=True, slots=True)
class Destination:
    scheme: str
    host: str
    port: int
    addresses: tuple[IPAddress, ...]


def _check_address(address: str | IPAddress, *, policy: Policy) -> IPAddress:
    ip = _as_address(address)
    if not policy.permits(ip):
        raise DestinationRefused(
            f"{ip} is a {classify(ip).value} address, "
            f"which the {policy.name} policy refuses"
        )
    return ip


def _literal(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_localhost_name(host: str) -> bool:
    return host == "localhost" or host.endswith(".localhost")


def _resolve(host: str, port: int, resolver: Resolver | None) -> Iterable[IPAddress]:
    try:
        infos = (resolver or socket.getaddrinfo)(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as error:
        raise UnresolvableDestination(f"{host} does not resolve: {error}") from error
    if not infos:
        raise UnresolvableDestination(f"{host} does not resolve to any address")
    return (ipaddress.ip_address(info[4][0]) for info in infos)


def _normalize(host: str) -> str:
    return host.strip("[]").rstrip(".").lower()


def resolve(
    host: str, port: int = 0, *, resolver: Resolver | None = None
) -> tuple[IPAddress, ...]:
    name = _normalize(host)
    if not name:
        raise UnresolvableDestination("the destination has no host")
    literal = _literal(name)
    if literal is not None:
        return (literal,)
    return tuple(dict.fromkeys(_resolve(name, port, resolver)))


def check_host(
    host: str,
    port: int,
    *,
    policy: Policy,
    resolver: Resolver | None = None,
) -> tuple[IPAddress, ...]:
    name = _normalize(host)
    if not name:
        raise DestinationRefused("the destination has no host", kind="syntax")
    if _literal(name) is None and _is_localhost_name(name):
        _check_address("127.0.0.1", policy=policy)
    addresses = resolve(name, port, resolver=resolver)
    for address in addresses:
        try:
            _check_address(address, policy=policy)
        except DestinationRefused as error:
            if _literal(name) is not None:
                raise
            raise DestinationRefused(f"{host} resolves to {error}") from None
    return addresses


TIMEOUTS_PASSED_OVER = 1


def dial(
    addresses: Sequence[IPAddress],
    port: int,
    *,
    timeout: float | None,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    if not addresses:
        raise ValueError("a dial needs at least one checked address")
    if timeout == 0:
        raise ValueError("a dial cannot be non-blocking (timeout=0)")
    *earlier, last = addresses
    timeouts = 0
    for address in earlier:
        try:
            return socket.create_connection(
                (str(address), port), timeout, source_address
            )
        except TimeoutError:
            timeouts += 1
            if timeouts > TIMEOUTS_PASSED_OVER:
                raise
        except OSError:
            continue
    return socket.create_connection((str(last), port), timeout, source_address)


_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
    "mqtt": 1883,
    "mqtts": 8883,
    "modbus": 502,
    "ssh": 22,
    "sftp": 22,
    "smtp": 25,
    "smtps": 465,
    "imap": 143,
    "imaps": 993,
    "pop3": 110,
    "pop3s": 995,
}


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_AUTHORITY = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)")
_AMBIGUOUS_IN_AUTHORITY = re.compile(r"[\\\s]")


def check_url(
    url: str,
    *,
    policy: Policy,
    resolver: Resolver | None = None,
    schemes: Iterable[str] | None = None,
) -> Destination:
    scheme, host, port = check_url_syntax(url, schemes=schemes)
    addresses = check_host(host, port, policy=policy, resolver=resolver)
    return Destination(scheme, host, port, addresses)


def check_url_syntax(
    url: str, *, schemes: Iterable[str] | None = None
) -> tuple[str, str, int]:
    shown = repr(mask_url(url))
    authority = _AUTHORITY.match(url)
    if _CONTROL.search(url) or (
        authority is not None and _AMBIGUOUS_IN_AUTHORITY.search(authority[1])
    ):
        raise DestinationRefused(
            f"{shown} has an ambiguous host: a control character, or a "
            "backslash or whitespace in its authority",
            kind="syntax",
        )
    try:
        parts = parse_url(url)
    except LocationParseError as error:
        raise DestinationRefused(
            f"{shown} has an invalid host or port", kind="syntax"
        ) from error
    scheme = parts.scheme or ""
    allowed = tuple(_DEFAULT_PORTS if schemes is None else schemes)
    if scheme not in allowed or scheme not in _DEFAULT_PORTS:
        raise DestinationRefused(
            f"the scheme {scheme or '(none)'!r} is not one this dial carries: "
            f"{', '.join(allowed)}",
            kind="syntax",
        )
    host = _normalize(parts.host or "")
    if not host:
        raise DestinationRefused(f"{shown} has no host", kind="syntax")
    if parts.port == 0:
        raise DestinationRefused(
            f"{shown} names port 0, which no connection reaches", kind="syntax"
        )
    port = _DEFAULT_PORTS[scheme] if parts.port is None else parts.port
    return scheme, host, port
