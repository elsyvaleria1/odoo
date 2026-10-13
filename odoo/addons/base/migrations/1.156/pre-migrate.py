from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "web_studio_ai_fields", "ai_fields_web_studio")
    rename_module(cr, "hr_recruitment_ai", "ai_hr_recruitment")
    rename_module(cr, "esg_csrd_ai", "ai_esg_csrd")
    rename_module(cr, "device_voip", "voip_device")
    rename_module(cr, "sign_ai", "ai_sign")
