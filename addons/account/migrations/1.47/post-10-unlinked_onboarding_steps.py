from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in (
        "account.onboarding_onboarding_step_base_document_layout",
        "account.onboarding_onboarding_step_sales_tax",
    ):
        if step := env.ref(xmlid, raise_if_not_found=False):
            step.unlink()
