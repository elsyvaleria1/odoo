from odoo.db import schema
from odoo.tools.module_data import fold_module, rename_model, rename_module


def _rename_voip_calls(cr):
    # here, not in voip: phone_call installs as a new dependency of voip and
    # of device_mobile, and whichever of those loads first would otherwise
    # fill a fresh phone_call table before voip's own migration could rename
    # voip_call onto it
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
    # one phone.call for every line: the bridges each call source carried for
    # speech analysis and conversations become one per concern, and the
    # speech bridges dissolve into the modules that now hold their timeline
    rename_module(cr, "voip_speech_analysis", "phone_call_speech_analysis")
    fold_module(cr, "device_mobile_speech_analysis", "phone_call_speech_analysis")
    rename_module(cr, "conversation_mobile", "conversation_phone_call")
    fold_module(cr, "conversation_voip", "conversation_phone_call")
    fold_module(cr, "voip_speech", "voip")
    fold_module(cr, "device_mobile_speech", "device_mobile")
    _rename_voip_calls(cr)
