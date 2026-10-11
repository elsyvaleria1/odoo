from . import controllers
from . import models
from . import reports
from . import utils
from . import wizards

EMSIGNER_AVAILABLE_COUNTRIES = "IN"


def _sign_post_init(env) -> None:
    country_codes = env["res.company"].search([]).mapped("country_id.code")
    if EMSIGNER_AVAILABLE_COUNTRIES in country_codes:
        module = env.ref("base.module_sign_emsigner")
        if module:
            module.sudo().button_install()


def uninstall_hook(env):
    if env["ir.module.module"]._get("account").state == "installed":
        env["res.company"].search([]).account_config_id.sign_invoice = False

    if env["ir.module.module"]._get("document").state == "installed":
        document_query = env["document.document"]._search(
            [("res_model", "=", "sign.template")]
        )
        mail_activities = env["mail.activity"].search(
            [("res_model", "=", "document.document"), ("res_id", "in", document_query)]
        )
        mail_activities.unlink()
