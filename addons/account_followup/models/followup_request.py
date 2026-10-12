from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Self


@dataclasses.dataclass(frozen=True, slots=True)
class FollowupRequest:
    partner: Any
    followup_line: Any
    manual: bool = False
    mail_template: Any = None
    sms_template: Any = None

    subject: str | None = None
    body: str | None = None
    sms_body: str | None = None
    email_from: str | None = None
    email_recipients: Any = None
    author: Any = None

    attachment_ids: tuple[int, ...] = ()
    report_attachment_id: int | None = None

    join_invoices: bool = True
    print_letter: bool = False

    channels: Mapping[str, bool] = MappingProxyType({})
    extra: Mapping[str, Any] = MappingProxyType({})

    @classmethod
    def prepare(cls, partner: Any, followup_line: Any = None, **values: Any) -> Self:
        partner.check_singleton()
        followup_line = (
            followup_line
            if followup_line is not None
            else (partner.followup_line_id or partner._get_first_followup_level())
        )
        values.setdefault("mail_template", followup_line.mail_template_id)
        values.setdefault("sms_template", followup_line.sms_template_id)
        values.setdefault("join_invoices", followup_line.join_invoices)
        for key in ("channels", "extra"):
            if key in values:
                values[key] = MappingProxyType(dict(values[key]))
        if "attachment_ids" in values:
            values["attachment_ids"] = tuple(values["attachment_ids"] or ())
        return cls(partner=partner, followup_line=followup_line, **values)

    def replace(self, **changes: Any) -> Self:
        if "attachment_ids" in changes:
            changes["attachment_ids"] = tuple(changes["attachment_ids"] or ())
        for key in ("channels", "extra"):
            if key in changes:
                changes[key] = MappingProxyType(dict(changes[key]))
        return dataclasses.replace(self, **changes)

    def with_channel(self, channel: str, enabled: bool) -> Self:
        return self.replace(channels={**self.channels, channel: enabled})

    def with_extra(self, **values: Any) -> Self:
        return self.replace(extra={**self.extra, **values})

    def is_channel_enabled(self, channel: str, default: bool) -> bool:
        return bool(self.channels.get(channel, default))

    @property
    def env(self):
        return self.partner.env

    @property
    def lang(self):
        return self.partner.lang or self.partner.env.user.lang
