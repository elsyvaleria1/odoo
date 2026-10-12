import logging
from email.message import EmailMessage
from typing import NamedTuple

from lxml import etree
from lxml.etree import LxmlError

from odoo.libs.debug_log import DebugLog
from odoo.tools.mail import add_html_content, html_sanitize

from .html_body import (
    iter_fragment_elements,
    parse_body_fragments,
    render_body_fragments,
)

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class Attachment(NamedTuple):
    fname: str
    content: str | bytes | EmailMessage | None
    info: dict[str, str | None]


class Payload(NamedTuple):
    body: str
    attachments: list[Attachment]


class DeliveryStatus(NamedTuple):
    failed_recipients: list[str]
    has_failure: bool


BAD_CONTENT_TYPES = (
    "binary/octet-stream",
    "*/*",
    "bin/plain",
)


def _alternative_rank(content_type: str) -> int:
    if content_type.startswith("multipart/") or content_type == "text/html":
        return 2
    if content_type == "text/plain":
        return 1
    return 0


def part_content(part: EmailMessage) -> str | bytes | EmailMessage | None:
    try:
        return part.get_content()
    except LookupError, UnicodeDecodeError, ValueError:
        _logger.warning(
            "Unresolvable charset %r on inbound mail part; decoding as utf-8 "
            "with replacement.",
            part.get_content_charset(),
        )
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def repair_part_headers(part: EmailMessage) -> None:
    if part.get_content_type().startswith("text/") and not part.get_param("charset"):
        part.set_charset("utf-8")
    content_type = part.get("Content-Type", "")
    if content_type.startswith("pdf;"):
        part.replace_header("Content-Type", "application/pdf" + content_type[3:])
    elif (bad_content_type := part.get_content_type()) in BAD_CONTENT_TYPES:
        _debug.logic("part_content_type_repaired", content_type=bad_content_type)
        _logger.warning(
            "Message containing an unexpected Content-Type %r, assuming "
            "'application/octet-stream'",
            bad_content_type,
        )
        part.replace_header("Content-Type", "application/octet-stream")


def _children(part: EmailMessage) -> list[EmailMessage]:
    payload = part.get_payload()
    return payload if isinstance(payload, list) else []


def _is_carried_file(part: EmailMessage, filename: str | None) -> bool:
    return bool(filename) or part.get_content_disposition() == "attachment"


def _is_attachment(part: EmailMessage, filename: str | None) -> bool:
    return _is_carried_file(part, filename) or part.get_content_type() not in (
        "text/plain",
        "text/html",
    )


class _Fragment(NamedTuple):
    body: str
    attachments: list[Attachment]
    html: bool


def _attachment_from(
    part: EmailMessage, filename: str | None, content: str | bytes | EmailMessage | None
) -> Attachment:
    info = {"encoding": part.get_content_charset()}
    if content_id := part.get("content-id"):
        info["cid"] = content_id.strip("><")
    return Attachment(filename or "attachment", content, info)


def _part_attachment(part: EmailMessage) -> Attachment:
    filename = part.get_filename()
    repair_part_headers(part)
    return _attachment_from(part, filename, part_content(part))


def _embedded_attachments(part: EmailMessage) -> list[Attachment]:
    payload = part.get_payload()
    inner = payload[0] if isinstance(payload, list) and payload else None
    if not isinstance(inner, EmailMessage):
        return []
    return [
        _part_attachment(sub)
        for sub in inner.walk()
        if sub is not inner
        and sub.get_content_maintype() != "multipart"
        and _is_carried_file(sub, sub.get_filename())
    ]


def _leaf(part: EmailMessage, stop_at_first_body: bool = False) -> _Fragment:
    filename = part.get_filename()
    repair_part_headers(part)
    content = part_content(part)

    if _is_attachment(part, filename):
        attachments = [_attachment_from(part, filename, content)]
        if not stop_at_first_body and part.get_content_type() == "message/rfc822":
            attachments += _embedded_attachments(part)
        return _Fragment("", attachments, False)
    if part.get_content_type() == "text/html":
        return _Fragment(content, [], True)
    return _Fragment(add_html_content("", content, preserve=True), [], False)


def _alternative(part: EmailMessage, stop_at_first_body: bool) -> _Fragment:
    children = _children(part)
    if not children:
        return _Fragment("", [], False)
    fragments = [_get_fragment(child, stop_at_first_body) for child in children]
    best = max(
        enumerate(children),
        key=lambda pair: (_alternative_rank(pair[1].get_content_type()), pair[0]),
    )[0]
    _debug.logic(
        "alternative_chosen",
        candidates=[child.get_content_type() for child in children],
        chosen=children[best].get_content_type(),
    )
    return _Fragment(
        fragments[best].body,
        [a for fragment in fragments for a in fragment.attachments],
        fragments[best].html,
    )


def _sequence(parts: list[EmailMessage], stop_at_first_body: bool) -> _Fragment:
    body = ""
    attachments: list[Attachment] = []
    html = False
    for child in parts:
        if stop_at_first_body and body:
            break
        fragment = _get_fragment(child, stop_at_first_body)
        if fragment.body:
            body = add_html_content(body, fragment.body, plaintext=False)
        attachments.extend(fragment.attachments)
        html = html or fragment.html
    return _Fragment(body, attachments, html)


def _get_fragment(part: EmailMessage, stop_at_first_body: bool) -> _Fragment:
    if part.get_content_maintype() != "multipart":
        return _leaf(part, stop_at_first_body)
    if part.get_content_type() == "multipart/alternative":
        return _alternative(part, stop_at_first_body)
    return _sequence(_children(part), stop_at_first_body)


def extract_payload(
    message: EmailMessage,
    *,
    is_bounce: bool = False,
    save_original: bool = False,
    original: bytes | None = None,
) -> Payload:
    attachments = []
    if save_original:
        content = original if original is not None else message.as_bytes()
        attachments.append(Attachment("original_email.eml", content, {}))
    fragment = _get_fragment(message, stop_at_first_body=is_bounce)
    body = fragment.body
    if fragment.html:
        body = html_sanitize(
            strip_notifications(body), sanitize_tags=False, strip_classes=True
        )
    _debug.pipeline(
        "payload_extracted",
        html=fragment.html,
        body=len(body),
        attachments=len(fragment.attachments),
        original_saved=save_original,
        is_bounce=is_bounce,
    )
    return Payload(body, attachments + fragment.attachments)


def _is_notification(node: etree._Element) -> bool:
    return any(
        "o_mail_notification" in (node.get(attribute) or "")
        for attribute in ("class", "summary")
    )


def strip_notifications(body: str) -> str:
    if not body.strip():
        return body
    try:
        fragments = parse_body_fragments(body)
    except AssertionError, ValueError, LxmlError:
        _debug.logic("notifications_unparsable", length=len(body))
        return body
    notifications = [
        node for node in iter_fragment_elements(fragments) if _is_notification(node)
    ]
    _debug.logic("notifications_stripped", count=len(notifications))
    if not notifications:
        return body
    kept = []
    for fragment in fragments:
        if isinstance(fragment, str) or not _is_notification(fragment):
            kept.append(fragment)
        elif fragment.tail:
            kept.append(fragment.tail)
    for node in notifications:
        if node.getparent() is not None:
            node.drop_tree()
    return render_body_fragments(kept)


def postprocess_payload(payload: Payload) -> Payload:
    body, attachments = payload
    if not body.strip():
        return payload
    fragments = parse_body_fragments(body)

    named = 0
    for node in iter_fragment_elements(fragments, "img"):
        if not node.get("src", "").startswith("cid:"):
            continue
        cid = node.get("src").split(":", 1)[1]
        attachment = next(
            (a for a in attachments if a.info and a.info.get("cid") == cid), None
        )
        if attachment:
            node.set("data-filename", attachment.fname)
            named += 1

    _debug.logic("payload_postprocessed", named=named)
    if named:
        body = render_body_fragments(fragments)
    return Payload(body, attachments)


def get_part(
    message: EmailMessage, content_types: tuple[str, ...]
) -> EmailMessage | None:
    return next(
        (part for part in message.walk() if part.get_content_type() in content_types),
        None,
    )


def _recipient_block_failed(block: EmailMessage) -> bool:
    if action := str(block.get("Action") or "").strip().lower():
        return action == "failed"
    status = str(block.get("Status") or "").strip()
    return not status or status.startswith("5")


def _bounced_recipient(block: EmailMessage) -> str | None:
    for header in ("Original-Recipient", "Final-Recipient"):
        _address_type, sep, address = str(block.get(header) or "").partition(";")
        if sep and (address := address.strip()):
            return address
    return None


def read_delivery_status(dsn_part: EmailMessage | None) -> DeliveryStatus:
    recipient_blocks = _children(dsn_part)[1:] if dsn_part is not None else []
    if not recipient_blocks:
        _debug.logic("delivery_status", blocks=0, failed=None)
        return DeliveryStatus([], True)
    failed_blocks = [
        block for block in recipient_blocks if _recipient_block_failed(block)
    ]
    failed_recipients = [
        recipient
        for block in failed_blocks
        if (recipient := _bounced_recipient(block)) is not None
    ]
    _debug.logic(
        "delivery_status",
        blocks=len(recipient_blocks),
        failed=len(failed_blocks),
        named=len(failed_recipients),
    )
    return DeliveryStatus(failed_recipients, bool(failed_blocks))


def get_report_type(message: EmailMessage) -> str | None:
    report = get_part(message, ("multipart/report",))
    if report is None:
        return None
    report_type = report.get_param("report-type")
    return str(report_type).strip().lower() if report_type else None
