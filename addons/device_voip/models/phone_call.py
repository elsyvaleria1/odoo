from datetime import timedelta

from odoo import api, models
from odoo.fields import Domain

from odoo.addons.phone_call.models.phone_call import number_key

# how far the phone system's stamp of a call may sit from the softphone's own
SOFTPHONE_WINDOW = timedelta(minutes=2)
# what a softphone files for a call that rang it: the phone system's report of
# the same call stands for it
RINGING_STATES = ("calling", "missed", "rejected")


class PhoneCall(models.Model):
    _inherit = "phone.call"

    @api.model
    def _device_entry_user(self, device, call, company):
        # only a phone system answers for everyone's extensions; a handset's
        # token naming one would file calls as any colleague
        extension = str(call.get("extension") or "").strip()
        if extension and device._phone_call_channel() == "pbx":
            users = (
                self.env["res.users.settings"]
                .search(
                    [
                        ("voip_username", "=", extension),
                        ("user_id.active", "=", True),
                    ],
                    order="id",
                )
                .user_id
            )
            user = users.filtered(lambda user: company in user.company_ids)[:1]
            if user or users:
                return user or users[:1]
        return super()._device_entry_user(device, call, company)

    @api.model
    def _device_call_to_vals(self, device, call, lines=None) -> dict | None:
        vals = super()._device_call_to_vals(device, call, lines)
        if vals is not None:
            vals["sip_call_id"] = str(call.get("sip_call_id") or "").strip() or False
        return vals

    @api.private
    @api.model
    def ingest_from_device(self, device, calls):
        ingest = super().ingest_from_device(device, calls)
        if device._phone_call_channel() == "pbx" and ingest.created:
            ingest.created._absorb_ringing_softphone_calls()
        return ingest

    def _absorb_ringing_softphone_calls(self) -> None:
        """Every browser a company number rang filed a call of its own; the
        phone system's report is that call, so those copies go."""
        incoming = self.filtered(lambda call: call.direction == "incoming")
        if not incoming:
            return
        window = Domain(
            "create_date", ">=", min(incoming.mapped("start_date")) - SOFTPHONE_WINDOW
        ) & Domain(
            "create_date",
            "<=",
            max((call.end_date or call.start_date) for call in incoming)
            + SOFTPHONE_WINDOW,
        )
        ringing = self.search(
            Domain("channel", "=", "softphone")
            & Domain("device_id", "=", False)
            & Domain("direction", "=", "incoming")
            & Domain("state", "in", RINGING_STATES)
            & Domain("id", "not in", self.ids)
            & window
        )
        copies = ringing.filtered(
            lambda copy: any(
                number_key(copy.phone_number) == number_key(call.phone_number)
                and call.start_date - SOFTPHONE_WINDOW
                <= copy.create_date
                <= (call.end_date or call.start_date) + SOFTPHONE_WINDOW
                for call in incoming
            )
        )
        copies.unlink()

    @api.model
    def _calls_to_complete(self, device, entries):
        candidates = super()._calls_to_complete(device, entries)
        sip_call_ids = [
            vals["sip_call_id"] for vals in entries if vals.get("sip_call_id")
        ]
        if sip_call_ids:
            candidates |= self.search(
                [
                    ("device_id", "=", False),
                    ("channel", "=", "softphone"),
                    ("sip_call_id", "in", sip_call_ids),
                ]
            )
        users = {vals["user_id"] for vals in entries if vals["user_id"]}
        if not users:
            return candidates
        return candidates | self.search(
            [
                ("device_id", "=", False),
                ("channel", "=", "softphone"),
                ("user_id", "in", list(users)),
                (
                    "create_date",
                    ">=",
                    min(vals["start_date"] for vals in entries) - SOFTPHONE_WINDOW,
                ),
                (
                    "create_date",
                    "<=",
                    max(vals["end_date"] for vals in entries) + SOFTPHONE_WINDOW,
                ),
            ]
        )

    @api.model
    def _call_to_complete(self, candidates, vals):
        if vals.get("sip_call_id"):
            # the softphone that took the call named its dialog: no guessing
            named = candidates.filtered(
                lambda call: (
                    call.channel == "softphone"
                    and not call.device_id
                    and call.sip_call_id == vals["sip_call_id"]
                )
            )
            if named:
                return named[:1]
        key = number_key(vals["phone_number"])
        softphone = candidates.filtered(
            lambda call: (
                call.channel == "softphone"
                and not call.device_id
                and call.user_id.id == vals["user_id"]
                and number_key(call.phone_number) == key
                and abs((call.start_date or call.create_date) - vals["start_date"])
                <= SOFTPHONE_WINDOW
            )
        )
        if softphone:
            return min(
                softphone,
                key=lambda call: abs(
                    (call.start_date or call.create_date) - vals["start_date"]
                ),
            )
        return super()._call_to_complete(candidates - softphone, vals)

    def _complete_with_entry(self, vals) -> None:
        if self.channel == "softphone":
            # the softphone filed this call as it happened; the phone system
            # adds the device that recorded it, never who or what carried it
            vals = {
                key: value
                for key, value in vals.items()
                if key not in ("channel", "user_id", "partner_id") or not self[key]
            }
        super()._complete_with_entry(vals)
