from odoo import SUPERUSER_ID, api
from odoo.db import schema
from odoo.tools import SQL

COLUMNS = (
    "id",
    "device_id",
    "phone_call_id",
    "phone_number",
    "timestamp",
    "duration",
    "file_name",
    "mimetype",
)


def _recordings(cr):
    optional = [
        column
        for column in ("segment_id", "conversation_id")
        if schema.column_exists(cr, "device_call_recording", column)
    ]
    names = (*COLUMNS, *optional)
    cr.execute(
        SQL(
            "SELECT %s FROM device_call_recording",
            SQL(", ").join(SQL.identifier(name) for name in names),
        )
    )
    return [dict(zip(names, row, strict=True)) for row in cr.fetchall()]


def _own_conversation(cr, call_id, conversation_id):
    # a recording that came ahead of its call log had a conversation of its
    # own; the call made for it now owns that conversation. The pre-migration
    # gave both tables the columns when conversations named call logs.
    if not schema.column_exists(cr, "phone_call", "conversation_id"):
        return
    cr.execute(
        "UPDATE phone_call SET conversation_id = %s"
        " WHERE id = %s AND conversation_id IS NULL",
        [conversation_id, call_id],
    )
    cr.execute(
        "UPDATE conversation_conversation SET phone_call_id = %s"
        " WHERE id = %s AND phone_call_id IS NULL",
        [call_id, conversation_id],
    )


def migrate(cr, version):
    if not version or not schema.column_exists(
        cr, "device_call_recording", "phone_call_id"
    ):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Call = env["phone.call"]
    Attachment = env["ir.attachment"]
    for row in _recordings(cr):
        device = env["device.device"].browse(row["device_id"]).exists()
        call = Call.browse(row["phone_call_id"]).exists()
        if not call and device:
            # a recording that never found its call-log entry waits for it, as
            # one arriving now would
            call = Call._create_awaiting_call(
                device,
                row["phone_number"] or "",
                row["timestamp"],
                row["duration"] or 0,
            )
        if not call:
            continue
        if row.get("conversation_id") and not row["phone_call_id"]:
            _own_conversation(cr, call.id, row["conversation_id"])
        if row.get("segment_id"):
            continue
        audio = Attachment.search(
            [
                ("res_model", "=", "device.call.recording"),
                ("res_id", "=", row["id"]),
                ("res_field", "=", "audio"),
            ],
            limit=1,
        )
        if not audio:
            continue
        audio.write(
            {
                "res_model": "phone.call",
                "res_id": call.id,
                "res_field": False,
                "name": row["file_name"] or audio.name,
                "mimetype": row["mimetype"] or audio.mimetype,
            }
        )
        timeline = call._recording_timeline()
        start_ms = timeline._next_media_offset_ms()
        seconds = row["duration"] or 0
        length = seconds * 1000 if seconds else audio._media_length_ms()
        # filed, not transcribed: these were never heard when they came in,
        # and _file_recording would queue the whole archive at once
        timeline._add_media_segment(audio, start_ms, start_ms + max(length, 1))
    schema.drop_columns(cr, "phone_call", ["migrated_device_call_log_id"])
    # every row moved onto phone.call; nothing defines these models any more,
    # so nothing else would drop their tables
    cr.execute("DROP TABLE device_call_recording, device_call_log CASCADE")
