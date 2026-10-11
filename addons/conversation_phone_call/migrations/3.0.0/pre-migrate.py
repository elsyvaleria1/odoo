from odoo.db import schema
from odoo.tools.module_data import drop_views

TABLE = "conversation_conversation"
RETIRED_VIEWS = (
    "conversation_conversation_view_form_mobile",
    "conversation_conversation_view_form_voip",
    "view_device_device_form_conversation",
    "view_device_call_recording_form_conversation",
    "view_device_call_recording_list_conversation",
)


def migrate(cr, version):
    if not version:
        return
    drop_views(cr, "conversation_phone_call", RETIRED_VIEWS)
    if not schema.column_exists(cr, TABLE, "voip_call_id"):
        return
    if not schema.column_exists(cr, TABLE, "phone_call_id"):
        schema.rename_column(cr, TABLE, "voip_call_id", "phone_call_id")
        return
    cr.execute(
        "UPDATE conversation_conversation"
        "   SET phone_call_id = voip_call_id"
        " WHERE phone_call_id IS NULL AND voip_call_id IS NOT NULL"
    )
    schema.drop_columns(cr, TABLE, ["voip_call_id"])
