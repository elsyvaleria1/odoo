from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Self


@dataclasses.dataclass(frozen=True, slots=True)
class FollowupRequest:
    """One reminder, for one customer, resolved once.

    Every field is settled by :meth:`prepare` before any of it is read, so no
    consumer resolves a fallback of its own. That is not a style preference:
    each of the three faults below was a fallback resolved late, in the wrong
    place, and each is unrepresentable here.

    - ``partner`` is a record, so it cannot arrive as an id in one caller and a
      recordset in the next.
    - ``followup_line`` and ``mail_template`` are read off the customer once,
      rather than off whichever recordset happened to be in scope -- a billing
      contact carries no receivables, so resolving there silently produced an
      empty template.
    - one name per concept, so a wizard cannot write ``template_id`` while the
      renderer reads ``mail_template``.

    Frozen, because the dict this replaces was mutated in place inside a loop
    over the recipients, which made the caller's value depend on how far the
    loop had got. Derive a changed copy with :meth:`replace`.
    """

    partner: Any
    followup_line: Any
    manual: bool = False
    mail_template: Any = None
    sms_template: Any = None

    # Content. None means "the renderer builds the default"; the manual wizard
    # fills these in with whatever the user edited.
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

    # Per-channel overrides. Absent means "ask the follow-up level", which is
    # what `is_channel_enabled` does. Channels are open: snailmail and whatsapp add their own
    # without this class knowing their names.
    channels: Mapping[str, bool] = MappingProxyType({})
    extra: Mapping[str, Any] = MappingProxyType({})

    @classmethod
    def prepare(cls, partner: Any, followup_line: Any = None, **values: Any) -> Self:
        """Resolve a request for `partner`, defaulting from its follow-up level."""
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
        """Return a copy with `changes` applied, normalised the same way as prepare."""
        if "attachment_ids" in changes:
            changes["attachment_ids"] = tuple(changes["attachment_ids"] or ())
        for key in ("channels", "extra"):
            if key in changes:
                changes[key] = MappingProxyType(dict(changes[key]))
        return dataclasses.replace(self, **changes)

    def with_channel(self, channel: str, enabled: bool) -> Self:
        """Return a copy that forces `channel` on or off.

        The seam a module adding a channel extends, so it never has to know how
        the others are stored.
        """
        return self.replace(channels={**self.channels, channel: enabled})

    def with_extra(self, **values: Any) -> Self:
        """Return a copy carrying module-specific values the core does not model."""
        return self.replace(extra={**self.extra, **values})

    def is_channel_enabled(self, channel: str, default: bool) -> bool:
        """Whether `channel` should be used, `default` being the level's own setting."""
        return bool(self.channels.get(channel, default))

    @property
    def env(self):
        return self.partner.env

    @property
    def lang(self):
        return self.partner.lang or self.partner.env.user.lang
