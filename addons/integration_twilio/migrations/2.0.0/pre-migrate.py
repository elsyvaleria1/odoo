from odoo.db import schema
from odoo.tools.module_data import rename_field, rename_model

from odoo.addons.integration_twilio.hooks import _rehome_twilio_service


def migrate(cr, version):
    rename_model(cr, "sms_twilio.config", "integration.twilio.config")
    rename_model(cr, "sms.twilio.number", "integration.twilio.number")
    rename_model(
        cr,
        "wizard.sms_twilio.config.update",
        "wizard.integration.twilio.config.update",
    )
    rename_field(cr, "sms.tracker", "sms_twilio_sid", "twilio_message_sid")
    rename_field(
        cr, "res.company", "sms_twilio_config_id", "integration_twilio_config_id"
    )
    rename_field(cr, "res.company", "sms_twilio_number_ids", "twilio_number_ids")
    _rehome_twilio_service(cr)
    if schema.table_exists(cr, "integration_receiver"):
        cr.execute(
            """
            UPDATE integration_receiver
               SET res_purpose = 'twilio_sms_status',
                   code = replace(code, '_sms_twilio_status', '_twilio_sms_status')
             WHERE res_purpose = 'sms_twilio_status'
            """
        )
