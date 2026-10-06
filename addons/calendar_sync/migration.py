"""What an adapter's upgrade does with the synchronization state it kept on
the user's settings before accounts existed; its migrations call this."""

import logging

from odoo.db import schema
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def adopt_settings_columns(env, code, columns, dropped=()) -> None:
    """One account per user from `columns` of res_users_settings, given as
    {account field: column}, then drop them and `dropped`."""
    cr = env.cr
    present = {
        field: column
        for field, column in columns.items()
        if schema.column_exists(cr, "res_users_settings", column)
    }
    if present:
        fields_, columns_ = zip(*present.items(), strict=True)
        cr.execute(
            SQL(
                "SELECT user_id, %s FROM res_users_settings WHERE %s",
                SQL(", ").join(SQL.identifier(column) for column in columns_),
                # a user who never synchronized holds NULLs and a false stop
                SQL(" OR ").join(
                    SQL(
                        "COALESCE(%s::text, 'false') NOT IN ('false', '')",
                        SQL.identifier(column),
                    )
                    for column in columns_
                ),
            )
        )
        Account = env["calendar.sync.account"]
        Users = env["res.users"].with_context(active_test=False)
        rows = cr.fetchall()
        for user_id, *values in rows:
            Account._for(Users.browse(user_id), code).write(
                {
                    field: value or False
                    for field, value in zip(fields_, values, strict=True)
                }
            )
        _logger.info("%s %s calendar accounts from the user settings", len(rows), code)
    schema.drop_columns(cr, "res_users_settings", [*columns.values(), *dropped])
