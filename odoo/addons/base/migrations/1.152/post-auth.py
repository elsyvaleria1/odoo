from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    api.Environment(cr, SUPERUSER_ID, {})["ir.config_parameter"].set_param(
        "base.rpc_api_key_only", "False"
    )
