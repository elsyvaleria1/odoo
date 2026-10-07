from odoo import SUPERUSER_ID, api

from odoo.addons.telegram.tools.authority import operating


def migrate(cr, version):
    # end stage: every feature module is loaded, so each menu names them all
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    operating(env["telegram.chat"]).search(
        [("chat_type", "=", "private"), ("account_id", "!=", False)]
    )._sync_command_menu()
