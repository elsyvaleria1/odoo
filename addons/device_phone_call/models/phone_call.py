import logging
from bisect import bisect_left, bisect_right
from datetime import timedelta
from itertools import groupby
from operator import itemgetter
from typing import NamedTuple

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.device.tools.ingest import DeviceIngest, parse_epoch_or_iso
from odoo.addons.phone_call.models.phone_call import number_key

_logger = logging.getLogger(__name__)

CALL_TYPES = {
    "1": ("incoming", "terminated"),
    "7": ("incoming", "terminated"),
    "incoming": ("incoming", "terminated"),
    "in": ("incoming", "terminated"),
    "2": ("outgoing", "terminated"),
    "outgoing": ("outgoing", "terminated"),
    "out": ("outgoing", "terminated"),
    "3": ("incoming", "missed"),
    "missed": ("incoming", "missed"),
    "4": ("incoming", "voicemail"),
    "voicemail": ("incoming", "voicemail"),
    "5": ("incoming", "rejected"),
    "rejected": ("incoming", "rejected"),
    "6": ("incoming", "blocked"),
    "blocked": ("incoming", "blocked"),
}
UNKNOWN_CALL_TYPE = (False, "unknown")

MATCH_WINDOW = timedelta(seconds=60)
LONGEST_CALL = timedelta(hours=3)
CALL_LOG_GRACE = timedelta(minutes=40)
AWAITING_HORIZON = timedelta(days=7)


class RecordingIngest(NamedTuple):
    call: object
    matched: bool
    attachment: object
    duplicate: bool


class PhoneCall(models.Model):
    _inherit = "phone.call"

    device_id = fields.Many2one(
        comodel_name="device.device",
        string="Device",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
        help="The handset or phone system that reported the call",
    )
    device_call_uid = fields.Char(
        string="Device Call ID",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="The device's own id for the call (a phone system's call uid): "
        "its recording names it, and finds this call by it",
    )
    awaits_call_log = fields.Boolean(
        index="btree_not_null",
        readonly=True,
        help="The device sent the call's recording before the call-log entry "
        "that dates and directs it; the entry completes this call on arrival.",
    )

    _device_start_idx = models.Index("(device_id, start_date)")

    @api.private
    @api.model
    def ingest_from_device(self, device, calls) -> DeviceIngest:
        prepared = []
        skipped = []
        lines = device._phone_call_lines()
        for index, call in enumerate(calls):
            vals = self._device_call_to_vals(device, call, lines)
            if vals is None:
                skipped.append(index)
            else:
                prepared.append(vals)
        skipped = tuple(skipped)
        if not prepared:
            return DeviceIngest(self.browse(), 0, skipped)
        filed, duplicates = self._in_line_companies(device, lines)._file_device_entries(
            device, prepared
        )
        return DeviceIngest(filed, duplicates, skipped)

    @api.model
    def _in_line_companies(self, device, lines=None):
        if lines is None:
            lines = device._phone_call_lines()
        companies = self.env["res.company"].union(*lines.values())
        if not companies - self.env.companies:
            return self
        allowed = dict.fromkeys([*self.env.companies.ids, *companies.ids])
        return self.with_context(allowed_company_ids=list(allowed))

    @api.model
    def _file_device_entries(self, device, prepared) -> tuple:
        fresh = self._remove_already_stored(device, prepared)
        duplicates = len(prepared) - len(fresh)
        if not fresh:
            return self.browse(), duplicates
        Company = self.env["res.company"]
        for company_id, entries in groupby(
            sorted(fresh, key=itemgetter("company_id")), key=itemgetter("company_id")
        ):
            entries = list(entries)
            partners = self._match_partners(
                [vals["phone_number"] for vals in entries], Company.browse(company_id)
            )
            for vals in entries:
                partner_id = partners.get(number_key(vals["phone_number"]))
                if partner_id:
                    vals["partner_id"] = partner_id
        adopted = self.browse()
        to_create = []
        candidates = self._calls_to_complete(device, fresh)
        for vals in fresh:
            reported = self._call_to_complete(candidates - adopted, vals)
            if reported:
                reported._complete_with_entry(vals)
                adopted |= reported
            else:
                to_create.append(vals)
        return adopted | self.create(to_create), duplicates

    @api.model
    def _device_call_to_vals(self, device, call, lines=None) -> dict | None:
        if not isinstance(call, dict):
            return None
        number = str(call.get("number") or call.get("phone_number") or "").strip()
        call_type = self._device_call_type(call)
        if not number or not call_type:
            return None
        direction, state = call_type
        start = (
            parse_epoch_or_iso(
                call.get("timestamp") or call.get("time") or call.get("date")
            )
            or fields.Datetime.now()
        )
        seconds = self._seconds(call.get("duration"))
        company = device._phone_call_company(call.get("line"), lines)
        return {
            "device_id": device.id,
            "device_call_uid": str(call.get("uid") or "").strip() or False,
            "phone_number": number,
            "contact_name": call.get("contact_name") or call.get("name") or False,
            "direction": direction,
            "state": state,
            "start_date": start,
            "end_date": start + timedelta(seconds=seconds),
            "user_id": self._device_entry_user(device, call, company).id,
            "company_id": company.id,
            "channel": device._phone_call_channel(),
        }

    @api.model
    def _device_call_type(self, call) -> tuple | None:
        raw = str(call.get("direction") or call.get("type") or "").strip().lower()
        if not raw:
            return None
        return CALL_TYPES.get(raw, UNKNOWN_CALL_TYPE if raw.isdigit() else None)

    @staticmethod
    def _seconds(value) -> int:
        try:
            return max(0, int(value or 0))
        except TypeError, ValueError:
            return 0

    @api.model
    def _remove_already_stored(self, device, prepared):
        stamps = sorted(
            {vals["start_date"] for vals in prepared if not vals["device_call_uid"]}
        )
        uids = [vals["device_call_uid"] for vals in prepared if vals["device_call_uid"]]
        within = Domain("start_date", "in", stamps)
        if uids:
            within |= Domain("device_call_uid", "in", uids)
        existing = self.search_read(
            Domain("device_id", "=", device.id)
            & Domain("awaits_call_log", "=", False)
            & within,
            [
                "device_call_uid",
                "start_date",
                "phone_number",
                "direction",
                "state",
                "user_id",
                "company_id",
            ],
            load=None,
        )
        seen_uids = {
            row["device_call_uid"] for row in existing if row["device_call_uid"]
        }
        seen = {self._stored_call_key(row) for row in existing}
        fresh = []
        for vals in prepared:
            uid = vals["device_call_uid"]
            if uid:
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
            else:
                key = self._stored_call_key(vals)
                if key in seen:
                    continue
                seen.add(key)
            fresh.append(vals)
        return fresh

    @staticmethod
    def _stored_call_key(vals) -> tuple:
        return (
            vals["start_date"],
            vals["phone_number"],
            vals["direction"],
            vals["state"],
            vals["user_id"] or False,
            vals["company_id"] or False,
        )

    @api.model
    def _device_entry_user(self, device, call, company):
        return device.user_id

    @api.model
    def _calls_to_complete(self, device, entries):
        uids = [vals["device_call_uid"] for vals in entries if vals["device_call_uid"]]
        span = Domain(
            "end_date", ">=", min(vals["start_date"] for vals in entries) - MATCH_WINDOW
        ) & Domain(
            "end_date", "<=", max(vals["end_date"] for vals in entries) + MATCH_WINDOW
        )
        if uids:
            span |= Domain("device_call_uid", "in", uids)
        return self.search(
            Domain("device_id", "=", device.id)
            & Domain("awaits_call_log", "=", True)
            & span
        )

    @api.model
    def _call_to_complete(self, candidates, vals):
        uid = vals.get("device_call_uid")
        if uid:
            return candidates.filtered(
                lambda call: call.awaits_call_log and call.device_call_uid == uid
            )[:1]
        start, end = vals["start_date"], vals["end_date"]
        key = number_key(vals["phone_number"])
        candidates = candidates.filtered(
            lambda call: (
                call.awaits_call_log
                and not call.device_call_uid
                and start - MATCH_WINDOW <= call.end_date <= end + MATCH_WINDOW
                and (not call.phone_number or number_key(call.phone_number) == key)
            )
        )
        if not candidates:
            return self.browse()
        return min(candidates, key=lambda call: abs(call.end_date - end))

    def _complete_with_entry(self, vals) -> None:
        self.check_singleton()
        self.write(
            {
                **{key: value for key, value in vals.items() if key != "contact_name"},
                "contact_name": vals.get("contact_name") or self.contact_name,
                "awaits_call_log": False,
            }
        )
        self.env["ir.attachment"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("company_id", "!=", self.company_id.id),
            ]
        ).write({"company_id": self.company_id.id})
        self._on_call_details_completed()

    def _on_call_details_completed(self) -> None:
        super()._on_call_details_completed()
        waiting = self.env["ir.attachment"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "in", self.ids),
                ("transcript_state", "=", "queued"),
            ]
        )
        for attachment in waiting:
            attachment._transcribe_later()

    @api.model
    def _cron_complete_awaiting_calls(self) -> None:
        now = fields.Datetime.now()
        waiting = self.search(
            [
                ("awaits_call_log", "=", True),
                ("device_id", "!=", False),
                ("create_date", "<=", now - CALL_LOG_GRACE),
                ("create_date", ">=", now - AWAITING_HORIZON),
            ]
        )
        named = waiting.filtered("device_call_uid")
        reported_by_uid = {
            (call.device_id, call.device_call_uid): call
            for call in self.search(
                [
                    ("device_id", "in", named.device_id.ids),
                    ("device_call_uid", "in", named.mapped("device_call_uid")),
                    ("awaits_call_log", "=", False),
                ]
            )
        }
        for call in named:
            reported = reported_by_uid.get((call.device_id, call.device_call_uid))
            if reported:
                call._merge_into(reported)
        for device, unnamed in (waiting - named).grouped("device_id").items():
            stamps = unnamed.mapped("end_date")
            timeline = list(self._reported_calls_near(device, min(stamps), max(stamps)))
            starts = [call.start_date for call in timeline]
            for call in unnamed:
                first = bisect_left(starts, call.end_date - LONGEST_CALL)
                last = bisect_right(starts, call.end_date + MATCH_WINDOW)
                reported = self._match_device_call(
                    device, call.phone_number or "", call.end_date, timeline[first:last]
                )
                if reported:
                    call._merge_into(reported)

    def _merge_into(self, call) -> None:
        self.check_singleton()
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", self._name), ("res_id", "=", self.id)]
        )
        segments = self.env["media.segment"].search(
            [("attachment_id", "in", attachments.ids)], order="start_ms"
        )
        attachments.write({"res_id": call.id, "company_id": call.company_id.id})
        timeline = call._recording_timeline()
        retention_days = timeline._media_retention_days()
        offset = timeline._next_media_offset_ms()
        for segment in segments:
            length = max(segment.duration_ms, 1)
            segment.write(
                {
                    "res_model": timeline._name,
                    "res_id": timeline.id,
                    "start_ms": offset,
                    "end_ms": offset + length,
                }
            )
            segment._stamp_content_expiry(retention_days)
            offset += length
        for attachment in attachments - segments.attachment_id:
            length = max(attachment._media_length_ms(), 1)
            timeline._add_media_segment(attachment, offset, offset + length)
            offset += length
        self._on_merged_into(call)
        self.unlink()

    @api.private
    @api.model
    def store_device_recording(self, device, vals):
        return self._in_line_companies(device)._file_device_recording(device, vals)

    @api.model
    def _file_device_recording(self, device, vals):
        audio_b64 = vals.get("audio_b64") or vals.get("audio")
        if not audio_b64:
            raise ValueError("Missing audio payload")
        number = str(vals.get("number") or vals.get("phone_number") or "").strip()
        stamped_at = parse_epoch_or_iso(
            vals.get("recorded_at") or vals.get("timestamp") or vals.get("date")
        )
        uid = str(vals.get("uid") or "").strip()
        recorded_at = stamped_at or fields.Datetime.now()
        seconds = self._seconds(vals.get("duration"))
        if uid:
            call = self.search(
                [("device_id", "=", device.id), ("device_call_uid", "=", uid)],
                limit=1,
            )
            stored = self._stored_on_call(call, vals.get("file_name"))
        else:
            call = self.browse()
            stored = self._stored_device_recording(
                device, vals.get("file_name"), stamped_at
            )
        if stored:
            call = self.browse(stored.res_id)
            return RecordingIngest(call, not call.awaits_call_log, stored, True)
        if not uid:
            call = self._match_device_call(device, number, recorded_at)
        matched = bool(call) and not call.awaits_call_log
        if not call:
            call = self._create_awaiting_call(
                device, number, recorded_at, seconds, uid=uid
            )
        attachment = self.env["ir.attachment"].create(
            {
                "name": vals.get("file_name") or "recording.m4a",
                "mimetype": vals.get("mimetype") or "audio/mp4",
                "datas": audio_b64,
                "res_model": call._name,
                "res_id": call.id,
                "company_id": call.company_id.id,
            }
        )
        start_ms = call._recording_timeline()._next_media_offset_ms()
        call._file_recording(
            attachment,
            start_ms,
            start_ms + seconds * 1000 if seconds else None,
            eta=None if matched else fields.Datetime.now() + CALL_LOG_GRACE,
        )
        return RecordingIngest(call, matched, attachment, False)

    @api.model
    def _stored_device_recording(self, device, file_name, recorded_at):
        if not file_name or not recorded_at:
            return self.env["ir.attachment"]
        calls = self.search(
            [
                ("device_id", "=", device.id),
                ("start_date", ">=", recorded_at - LONGEST_CALL - MATCH_WINDOW),
                ("start_date", "<=", recorded_at + MATCH_WINDOW),
            ]
        )
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "in", calls.ids),
                ("name", "=", file_name),
            ],
            limit=1,
        )

    @api.model
    def _stored_on_call(self, call, file_name):
        if not call or not file_name:
            return self.env["ir.attachment"]
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", call.id),
                ("name", "=", file_name),
            ],
            limit=1,
        )

    @api.model
    def _create_awaiting_call(self, device, number, recorded_at, seconds, uid=False):
        partners = self._match_partners([number], device._phone_call_company())
        return self.create(
            {
                "device_id": device.id,
                "device_call_uid": uid or False,
                "phone_number": number or False,
                "partner_id": partners.get(number_key(number), False),
                "direction": False,
                "state": "terminated",
                "start_date": recorded_at - timedelta(seconds=seconds),
                "end_date": recorded_at,
                "user_id": device.user_id.id,
                "company_id": device._phone_call_company().id,
                "channel": device._phone_call_channel(),
                "awaits_call_log": True,
            }
        )

    @api.model
    def _reported_calls_near(self, device, first, last):
        return self.search(
            [
                ("device_id", "=", device.id),
                ("awaits_call_log", "=", False),
                ("start_date", ">=", first - LONGEST_CALL),
                ("start_date", "<=", last + MATCH_WINDOW),
            ],
            order="start_date",
        )

    @api.model
    def _match_device_call(self, device, number, recorded_at, candidates=None):
        key = number_key(number)
        if not key and device._phone_call_channel() == "pbx":
            return self.browse()
        if candidates is None:
            candidates = self._reported_calls_near(device, recorded_at, recorded_at)
        covering = [
            call
            for call in candidates
            if call.start_date - MATCH_WINDOW
            <= recorded_at
            <= (call.end_date or call.start_date) + MATCH_WINDOW
            and (not key or number_key(call.phone_number) == key)
        ]
        if not covering:
            return self.browse()
        return min(
            covering,
            key=lambda call: abs((call.end_date or call.start_date) - recorded_at),
        )
