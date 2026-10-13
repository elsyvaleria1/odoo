"""Name the Unix user on the client end of a loopback TCP connection."""

import grp
import ipaddress
import os
import pwd
import socket
import stat
import struct
from pathlib import Path

_NETLINK_SOCK_DIAG = 4
_SOCK_DIAG_BY_FAMILY = 20
_NLM_F_REQUEST = 1
_NLMSG_ERROR = 2
_NLMSG_HEADER = 16
_INET_DIAG_NOCOOKIE = 0xFFFFFFFF
# struct inet_diag_msg: 4 bytes of state, a 48-byte sockid, then expires, rqueue,
# wqueue, uid, inode (u32 each).
_INET_DIAG_MSG_SIZE = 72
_INET_DIAG_MSG_UID = 64
_KEY_TYPES = ("ssh-", "ecdsa-", "sk-")

# Only a keys file owned by this uid, and writable by nobody else, names a person:
# whoever can write it chooses which Odoo user the Unix user becomes.
TRUSTED_OWNER = 0


def is_loopback(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def tcp_owner_uid(src: str, sport: int, dst: str, dport: int) -> int | None:
    """Return the uid that owns the local TCP socket ``src:sport -> dst:dport``.

    The kernel answers (sock_diag), so the client cannot choose the result.

    :param str src: client address
    :param int sport: client port
    :param str dst: server address
    :param int dport: server port
    :return: the owner's uid, or None when no such socket exists
    :rtype: int | None
    """
    src_ip, dst_ip = ipaddress.ip_address(src), ipaddress.ip_address(dst)
    family = socket.AF_INET if src_ip.version == 4 else socket.AF_INET6
    request = struct.pack("=BBBBI", family, socket.IPPROTO_TCP, 0, 0, 0xFFFFFFFF)
    sockid = (
        struct.pack("!HH", sport, dport)
        + src_ip.packed.ljust(16, b"\0")
        + dst_ip.packed.ljust(16, b"\0")
        + struct.pack("=III", 0, _INET_DIAG_NOCOOKIE, _INET_DIAG_NOCOOKIE)
    )
    payload = request + sockid
    header = struct.pack(
        "=IHHII",
        _NLMSG_HEADER + len(payload),
        _SOCK_DIAG_BY_FAMILY,
        _NLM_F_REQUEST,
        1,
        0,
    )
    with socket.socket(
        socket.AF_NETLINK, socket.SOCK_DGRAM, _NETLINK_SOCK_DIAG
    ) as netlink:
        netlink.settimeout(1)
        netlink.sendto(header + payload, (0, 0))
        data = netlink.recv(65536)
    length, kind = struct.unpack_from("=IH", data)
    if kind == _NLMSG_ERROR or length < _NLMSG_HEADER + _INET_DIAG_MSG_SIZE:
        return None
    return struct.unpack_from("=I", data, _NLMSG_HEADER + _INET_DIAG_MSG_UID)[0]


def member_name(uid: int, group: str) -> str | None:
    """Return the name of Unix user ``uid`` if it belongs to ``group``, else None."""
    try:
        user = pwd.getpwuid(uid)
        members = grp.getgrnam(group)
    except KeyError:
        return None
    if user.pw_gid == members.gr_gid or user.pw_name in members.gr_mem:
        return user.pw_name
    return None


def login_from_keys(path: str) -> str | None:
    """Return the comment every key in an authorized_keys file shares.

    :param str path: the keys file
    :return: the shared comment, or None when the file is missing, not owned by
        :data:`TRUSTED_OWNER`, writable by others, holds no key, or its keys
        carry no comment or different ones
    :rtype: str | None
    """
    try:
        with Path(path).open(encoding="utf-8") as keys:
            info = os.fstat(keys.fileno())
            if info.st_uid != TRUSTED_OWNER or info.st_mode & (
                stat.S_IWGRP | stat.S_IWOTH
            ):
                return None
            lines = keys.read().splitlines()
    except OSError, UnicodeDecodeError:
        return None
    comments = set()
    for line in lines:
        words = line.split()
        if not words or words[0].startswith("#"):
            continue
        kind = next(
            (i for i, word in enumerate(words) if word.startswith(_KEY_TYPES)), None
        )
        if kind is None or len(words) < kind + 3:
            return None
        comments.add(" ".join(words[kind + 2 :]))
    return comments.pop() if len(comments) == 1 else None
