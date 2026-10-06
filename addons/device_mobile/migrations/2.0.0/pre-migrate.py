from odoo.db import schema
from odoo.libs.json import dumps as json_dumps
from odoo.tools import SQL

# what a call-log entry said in one word, as (direction, outcome)
CALL_TYPES = {
    "incoming": ("incoming", "terminated"),
    "outgoing": ("outgoing", "terminated"),
    "missed": ("incoming", "missed"),
    "voicemail": ("incoming", "voicemail"),
    "rejected": ("incoming", "rejected"),
    "blocked": ("incoming", "blocked"),
    "unknown": (None, "unknown"),
}
# the call-log columns phone.call holds under another name, or not at all
NOT_COPIED = {
    "id",
    "direction",
    "duration",
    "timestamp",
    "raw_payload",
    "data_type",
    "source",
    "phone_number",
    "contact_name",
    "partner_id",
    "device_id",
    "company_id",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
}
MAP_COLUMN = "migrated_device_call_log_id"


def _shared_columns(cr):
    log = schema.get_table_columns(cr, "device_call_log")
    call = schema.get_table_columns(cr, "phone_call")
    return sorted(set(log) & set(call) - NOT_COPIED)


def _move_call_logs(cr):
    schema.create_column(cr, "phone_call", MAP_COLUMN, "int4")
    shared = _shared_columns(cr)
    user = (
        SQL("device.user_id")
        if schema.column_exists(cr, "device_device", "user_id")
        else SQL("NULL")
    )
    log_company = (
        SQL("log.company_id")
        if schema.column_exists(cr, "device_call_log", "company_id")
        else SQL("NULL")
    )
    cr.execute(
        SQL(
            """
            INSERT INTO phone_call (
                %(map)s, phone_number, contact_name, partner_id, device_id,
                company_id, user_id, channel, direction, state, start_date,
                end_date, awaits_call_log, create_uid, create_date, write_uid,
                write_date %(shared_targets)s
            )
            SELECT log.id, log.phone_number, log.contact_name, log.partner_id,
                   log.device_id,
                   COALESCE(%(log_company)s, device.company_id,
                            (SELECT MIN(id) FROM res_company)),
                   %(user)s, 'mobile',
                   (%(types)s::jsonb -> log.direction ->> 0),
                   COALESCE(%(types)s::jsonb -> log.direction ->> 1, 'unknown'),
                   log.timestamp,
                   log.timestamp + COALESCE(log.duration, 0) * INTERVAL '1 second',
                   false, log.create_uid, log.create_date, log.write_uid,
                   log.write_date %(shared_sources)s
              FROM device_call_log AS log
              LEFT JOIN device_device AS device ON device.id = log.device_id
            """,
            map=SQL.identifier(MAP_COLUMN),
            user=user,
            log_company=log_company,
            types=SQL("%s", json_dumps(CALL_TYPES)),
            shared_targets=SQL("").join(
                SQL(", %s", SQL.identifier(column)) for column in shared
            ),
            shared_sources=SQL("").join(
                SQL(", log.%s", SQL.identifier(column)) for column in shared
            ),
        )
    )


def _repoint_references(cr):
    pairs = (("res_model", "res_id"), ("model", "res_id"))
    for model_column, id_column in pairs:
        cr.execute(
            """
            SELECT m.table_name
              FROM information_schema.columns m
              JOIN information_schema.columns i
                ON i.table_name = m.table_name AND i.table_schema = m.table_schema
             WHERE m.table_schema = current_schema()
               AND m.column_name = %s AND i.column_name = %s
            """,
            [model_column, id_column],
        )
        for (table,) in cr.fetchall():
            cr.execute(
                SQL(
                    """
                    UPDATE %(table)s AS ref
                       SET %(model)s = 'phone.call', %(id)s = call.id
                      FROM phone_call AS call
                     WHERE ref.%(model)s = 'device.call.log'
                       AND call.%(map)s = ref.%(id)s
                    """,
                    table=SQL.identifier(table),
                    model=SQL.identifier(model_column),
                    id=SQL.identifier(id_column),
                    map=SQL.identifier(MAP_COLUMN),
                )
            )


def _link_conversations(cr):
    if not schema.column_exists(cr, "conversation_conversation", "call_log_id"):
        return
    if not schema.column_exists(cr, "conversation_conversation", "phone_call_id"):
        schema.create_column(cr, "conversation_conversation", "phone_call_id", "int4")
    if not schema.column_exists(cr, "phone_call", "conversation_id"):
        schema.create_column(cr, "phone_call", "conversation_id", "int4")
    cr.execute(
        SQL(
            """
            UPDATE conversation_conversation AS conversation
               SET phone_call_id = call.id
              FROM phone_call AS call
             WHERE call.%(map)s = conversation.call_log_id
               AND conversation.phone_call_id IS NULL
            """,
            map=SQL.identifier(MAP_COLUMN),
        )
    )
    cr.execute(
        """
        UPDATE phone_call AS call
           SET conversation_id = conversation.id
          FROM conversation_conversation AS conversation
         WHERE conversation.phone_call_id = call.id
           AND call.conversation_id IS NULL
        """
    )


def _remember_recording_calls(cr):
    if not schema.table_exists(cr, "device_call_recording"):
        return
    schema.create_column(cr, "device_call_recording", "phone_call_id", "int4")
    cr.execute(
        SQL(
            """
            UPDATE device_call_recording AS recording
               SET phone_call_id = call.id
              FROM phone_call AS call
             WHERE call.%(map)s = recording.call_id
            """,
            map=SQL.identifier(MAP_COLUMN),
        )
    )


def migrate(cr, version):
    if not version or not schema.table_exists(cr, "device_call_log"):
        return
    if schema.column_exists(cr, "phone_call", MAP_COLUMN):
        return
    _move_call_logs(cr)
    _repoint_references(cr)
    _link_conversations(cr)
    _remember_recording_calls(cr)
