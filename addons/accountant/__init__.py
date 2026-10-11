from odoo import Command
import logging

from . import models

_logger = logging.getLogger(__name__)


def _accounting_post_init(env) -> None:
    if env["res.company"].search_count([("country_id.code", "in", ("AU", "CA", "US"))]):
        modules = env["ir.module.module"].search(
            [
                ("name", "=", "account_reports_cash_basis"),
                ("state", "=", "uninstalled"),
            ]
        )
        if modules:
            modules.sudo().button_install()

    companies = env["res.company"].search(
        [("account_config_id.chart_template", "!=", False)]
    )
    companies._initiate_account_onboardings()
    companies.account_config_id.account_tax_return_journal_id.show_on_dashboard = True


def uninstall_hook(env):
    try:
        group_user = env.ref("account.group_account_user")
        group_user.write(
            {
                "name": "Show Full Accounting Features",
                "sequence": 0,
                "comment": False,
                "privilege_id": False,
            }
        )
        group_readonly = env.ref("account.group_account_readonly")
        group_readonly.write(
            {
                "comment": "Access to all Accounting data, journal entries, configuration and reports included, but in read-only mode, no actions allowed."
            }
        )
        env["res.users.grant"]._revoke(
            None, group_user | group_readonly, reason="accountant uninstalled"
        )
    except ValueError as e:
        _logger.warning(e)

    try:
        group_manager = env.ref("account.group_account_manager")
        group_manager.write(
            {
                "implied_ids": [
                    Command.link(env.ref("account.group_account_invoice").id),
                    Command.unlink(env.ref("account.group_account_user").id),
                ],
            }
        )
    except ValueError as e:
        _logger.warning(e)

    invoicing_menu = env.ref("account.menu_finance")
    try:
        accounting_menu = env.ref("accountant.menu_accounting")
    except ValueError as e:
        _logger.warning(e)
        return
    adopted_menus = (
        env["ir.ui.menu"]
        .with_context(active_test=False)
        .search([("parent_id", "=", accounting_menu.id)])
    )
    adopted_menus.parent_id = invoicing_menu
