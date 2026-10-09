from odoo import SUPERUSER_ID, api
from odoo.tools import SQL


def migrate(cr, version):
    """The first synchronization's date, kept for the whole database, becomes
    the floor of each account that has none (a reset may have set a later
    one); the parameters and the wizard nothing reads any more go."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env["ir.config_parameter"]
    first = env.registry.settings.get(
        env, "calendar_microsoft.sync.first_synchronization_date", False
    )
    accounts = (
        env["calendar.sync.account"]
        .search([("provider", "=", "microsoft")])
        .filtered(lambda account: not account.insert_since)
    )
    if first:
        accounts.write({"insert_since": first})
    else:
        # no date kept: an account that synchronized did so before the date
        # existed and sent everything; one that never did starts now, as its
        # first synchronization would have
        accounts.filtered(lambda account: not account.sync_token).write(
            {"insert_since": cr.now()}
        )
    ICP.search(
        [
            (
                "key",
                "in",
                [
                    "calendar_microsoft.sync.first_synchronization_date",
                    "calendar_microsoft.sync.lower_bound_range",
                    "calendar_microsoft.microsoft_guid",
                ],
            )
        ]
    ).unlink()
    # the reset is calendar_sync's wizard now; nothing defines this one, so
    # nothing else would drop its table
    cr.execute(
        SQL(
            "DROP TABLE IF EXISTS %s",
            SQL.identifier("wizard_res_users_reset_microsoft_calendar"),
        )
    )
