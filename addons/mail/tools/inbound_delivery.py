import base64
import binascii
from dataclasses import dataclass
from typing import Any

from odoo.tools.mail import email_normalize

INBOUND_MAIL_PURPOSE = "mail_inbound"
INBOUND_MAIL_MAX_BYTES = 50 * 1024 * 1024
MAX_ENVELOPE_RECIPIENTS = 1000


class MailRouteNotFound(ValueError):
    pass


class MailRouteMisconfigured(ValueError):
    pass


@dataclass(frozen=True)
class InboundDelivery:
    sender: str
    recipients: tuple[str, ...]
    message: bytes

    @classmethod
    def from_envelope(cls, envelope: dict[str, Any]) -> InboundDelivery:
        sender = envelope.get("sender")
        if sender is None:
            sender = ""
        if not isinstance(sender, str) or any(c in sender for c in "\r\n<>"):
            raise ValueError("sender must be a bare address; the null sender is empty")
        recipients = envelope.get("recipients")
        if (
            not isinstance(recipients, list)
            or not recipients
            or len(recipients) > MAX_ENVELOPE_RECIPIENTS
        ):
            raise ValueError(
                "recipients must list between 1 and %d addresses"
                % MAX_ENVELOPE_RECIPIENTS
            )
        normalized = []
        for recipient in recipients:
            address = email_normalize(recipient) if isinstance(recipient, str) else None
            if not address:
                raise ValueError("recipient %r is not an email address" % (recipient,))
            normalized.append(address)
        encoded = envelope.get("message")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("message must be the base64 of the message as received")
        try:
            message = base64.b64decode(encoded, validate=True)
        except binascii.Error as error:
            raise ValueError("message is not valid base64: %s" % error) from None
        if not message.strip():
            raise ValueError("message is empty")
        # an MTA names the null sender (Postfix: MAILER-DAEMON) unless told not to
        sender = email_normalize(sender) or ""
        return cls(sender, tuple(dict.fromkeys(normalized)), message)

    def stamped(self) -> bytes:
        # What a final delivery agent writes (RFC 5321 4.4): the envelope the
        # gateway routes on, since a Bcc recipient appears in no other header.
        trace = [b"Return-Path: <%s>" % self.sender.encode()]
        trace += [b"Delivered-To: %s" % rcpt.encode() for rcpt in self.recipients]
        newline = b"\r\n" if b"\r\n" in self.message[:4096] else b"\n"
        return newline.join(trace) + newline + self.message
