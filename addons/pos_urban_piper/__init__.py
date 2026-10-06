from odoo import Command
from . import controllers
from . import models
from . import wizards
import uuid


def _urban_piper_post_init(env) -> None:
    if not env.registry.settings.get(env, "pos_urban_piper.uuid", False):
        env["ir.config_parameter"].sudo().set_param(
            "pos_urban_piper.uuid", str(uuid.uuid4())
        )
    en_US_language = env["res.lang"].sudo().search([("code", "=", "en_US")], limit=1)
    if not en_US_language:
        en_US_language = (
            env["res.lang"]
            .with_context(active_test=False)
            .sudo()
            .search([("code", "=", "en_US")], limit=1)
        )
        env["wizard.res.lang.install"].create(
            {"lang_ids": [Command.set(en_US_language.ids)]}
        ).action_install_lang()
    env["ir.config_parameter"].sudo().set_param(
        "pos_urban_piper.is_production_mode", "True"
    )
    if not env.registry.settings.get(env, "pos_urban_piper.toggle_state", False):
        env["ir.config_parameter"].sudo().set_param(
            "pos_urban_piper.toggle_state", "{}"
        )
    env["account.chart.template"]._load_urbanpiper_fiscal_positions()
