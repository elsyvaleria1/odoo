from odoo.db import schema
from odoo.tools.module_data import fold_module, rename_model, rename_module


def _rename_voip_calls(cr):
    if not schema.table_exists(cr, "voip_call"):
        return
    rename_model(cr, "voip.call", "phone.call")
    if not schema.column_exists(cr, "phone_call", "company_id"):
        schema.create_column(cr, "phone_call", "company_id", "int4")
        cr.execute(
            """
            UPDATE phone_call AS call
               SET company_id = COALESCE(
                       (SELECT u.company_id FROM res_users AS u WHERE u.id = call.user_id),
                       (SELECT MIN(c.id) FROM res_company AS c)
                   )
            """
        )


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "voip_speech_analysis", "phone_call_speech_analysis")
    fold_module(cr, "device_mobile_speech_analysis", "phone_call_speech_analysis")
    rename_module(cr, "conversation_mobile", "conversation_phone_call")
    fold_module(cr, "conversation_voip", "conversation_phone_call")
    fold_module(cr, "voip_speech", "voip")
    fold_module(cr, "device_mobile_speech", "device_mobile")
    _rename_voip_calls(cr)
