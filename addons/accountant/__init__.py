from odoo import Command
import logging

from . import models

_logger = logging.getLogger(__name__)


def _accounting_post_init(env) -> None:
    # Installing a module is a database-wide act, so the question is whether ANY
    # company wants cash-basis reports -- not whichever company happened to be
    # active when `accountant` was installed. The loop below already reads the
    # database this way.
    if env["res.company"].search_count([("country_id.code", "in", ("AU", "CA", "US"))]):
        modules = env["ir.module.module"].search(
            [
                ("name", "=", "account_reports_cash_basis"),
                ("state", "=", "uninstalled"),
            ]
        )
        if modules:
            modules.sudo().button_install()

    # Both operations take a recordset: `_initiate_account_onboardings` runs one
    # onboarding search and then loops over `self`, so calling it per company
    # repeated that search N times. Neither depends on hierarchy order, which is
    # why the companies are no longer read in `parent_path` order.
    companies = env["res.company"].search(
        [("account_config_id.chart_template", "!=", False)]
    )
    companies._initiate_account_onboardings()
    companies.account_config_id.account_tax_return_journal_id.show_on_dashboard = True


def uninstall_hook(env):
    try:
        # Put back every field this module's security data overwrites, not just
        # the name: `account` declares the user group with a name and
        # implied_ids only, and res.groups gives sequence/comment/privilege_id
        # no default, so core's values for them are 0/False. Restoring the name
        # alone left the other three carrying this module's values on a database
        # where `account` stays installed.
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
        # The readonly group keeps core's name -- this module never touches it --
        # but it does replace the comment, so that one goes back too.
        group_readonly.write(
            {
                "comment": "Access to all Accounting data, journal entries, configuration and reports included, but in read-only mode, no actions allowed."
            }
        )
        # Drop the memberships that gate this module's features, so the
        # accounting menus and views it added stop being reachable.
        env["res.users.grant"]._revoke(
            None, group_user | group_readonly, reason="accountant uninstalled"
        )
    except ValueError as e:
        _logger.warning(e)

    try:
        # The manager group's name is core's and never changed here; only the
        # implied_ids this module's security data rewired are put back.
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

    # this menu should always be there, as the module depends on account.
    # if it's not, there is something wrong with the db that should be investigated.
    invoicing_menu = env.ref("account.menu_finance")
    # Hand back every menu the module's data file adopted, rather than a second
    # list of them kept by hand: ir.ui.menu.unlink() reparents the children it
    # still has to parent_id = False, so anything missed here resurfaces as a
    # root-level app once menu_accounting is deleted.
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
