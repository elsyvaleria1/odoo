from odoo import SUPERUSER_ID, api
from odoo.tools import SQL


def migrate(cr, version):
    """The first synchronization's date, kept for the whole database, becomes
    each account's floor; the parameters and the wizard nothing reads any
    more go."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env["ir.config_parameter"]
    first = env.registry.settings.get(
        env, "calendar_microsoft.sync.first_synchronization_date", False
    )
    accounts = env["calendar.sync.account"].search([("provider", "=", "microsoft")])
    if first:
        accounts.write({"insert_since": first})
    else:
        # synchronized before the date was kept: everything was sent
        accounts.filtered("sync_token").write({"insert_since": False})
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
