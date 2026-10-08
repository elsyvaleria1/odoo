from odoo import SUPERUSER_ID, Command, api

from odoo.addons.telegram.tools.authority import keeping


def migrate(cr, version):
    # /estadoctapropio is /estadocuentaperiodo's current year now: a bot that
    # offered it offers the period command, and the old command goes before
    # the data cleanup drops it from the bots unannounced. The end stage, so
    # the menus each bot's people get name every feature's commands.
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    own = env.ref("account_telegram.command_estadocuenta", raise_if_not_found=False)
    if not own:
        return
    period = env.ref("account_telegram.command_estadocuentaperiodo")
    for bot in keeping(env["telegram.bot"]).search([("command_ids", "in", own.ids)]):
        bot.command_ids = [Command.unlink(own.id), Command.link(period.id)]
    own.unlink()
