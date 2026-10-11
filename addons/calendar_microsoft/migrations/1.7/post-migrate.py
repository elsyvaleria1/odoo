from odoo import SUPERUSER_ID, api
from odoo.tools import SQL


def migrate(cr, version):
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
    cr.execute(
        SQL(
            "DROP TABLE IF EXISTS %s",
            SQL.identifier("wizard_res_users_reset_microsoft_calendar"),
        )
    )
