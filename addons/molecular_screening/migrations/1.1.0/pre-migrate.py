from odoo.db import schema
from odoo.tools.module_data import rename_model


def migrate(cr, version):
    if not version:
        return
    rename_model(cr, "molecular.sketch", "wizard.molecular.sketch")
    if not schema.column_exists(cr, "molecular_screening_campaign", "company_id"):
        schema.create_column(
            cr, "molecular_screening_campaign", "company_id", "integer"
        )
        cr.execute("""
            UPDATE molecular_screening_campaign campaign
               SET company_id = COALESCE(
                   (SELECT company_id FROM res_users WHERE id = campaign.user_id),
                   (SELECT company_id FROM res_users WHERE id = campaign.create_uid),
                   (SELECT res_id FROM ir_model_data
                     WHERE module = 'base' AND name = 'main_company')
               )
        """)
