"""What an adapter's upgrade does with the synchronization state it kept
before accounts and links existed; its migrations call this."""

import dataclasses
import logging

from odoo import SUPERUSER_ID
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


@dataclasses.dataclass(frozen=True)
class RemoteIdSource:
    table: str
    link_field: str
    # the user whose calendar holds the id of a row of `table` aliased `rec`
    owner: SQL


def link_remote_ids(env, code, sources, column) -> None:
    """Link every row of `sources` holding a remote id in `column` to it, in its
    owner's calendar, then drop the column."""
    cr = env.cr
    present = [s for s in sources if schema.column_exists(cr, s.table, column)]
    if not present:
        return
    cr.execute(
        SQL(
            "CREATE TEMP TABLE calendar_sync_upgrade ON COMMIT DROP AS %s",
            SQL(" UNION ALL ").join(
                SQL(
                    """SELECT %(field)s AS link_field, rec.id AS res_id,
                              COALESCE(%(owner)s, %(root)s) AS user_id,
                              %(column)s AS remote_id
                         FROM %(table)s rec
                        WHERE %(column)s IS NOT NULL""",
                    field=source.link_field,
                    owner=source.owner,
                    root=SUPERUSER_ID,
                    column=SQL.identifier("rec", column),
                    table=SQL.identifier(source.table),
                )
                for source in present
            ),
        )
    )
    cr.execute(SQL("SELECT DISTINCT user_id FROM calendar_sync_upgrade"))
    Account = env["calendar.sync.account"]
    Users = env["res.users"].with_context(active_test=False)
    accounts = {
        user_id: Account._for(Users.browse(user_id), code).id
        for (user_id,) in cr.fetchall()
    }
    env.flush_all()
    cr.execute(
        SQL(
            """INSERT INTO calendar_sync_link (
                   account_id, event_id, recurrence_id, remote_id, pending,
                   create_uid, write_uid, create_date, write_date
               )
               SELECT owner.account_id,
                      CASE upgrade.link_field WHEN 'event_id' THEN upgrade.res_id END,
                      CASE upgrade.link_field WHEN 'recurrence_id' THEN upgrade.res_id END,
                      upgrade.remote_id, false, %(uid)s, %(uid)s,
                      now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
                 FROM calendar_sync_upgrade upgrade
                 JOIN unnest(%(users)s::int[], %(accounts)s::int[])
                      AS owner(user_id, account_id)
                      ON owner.user_id = upgrade.user_id""",
            uid=SUPERUSER_ID,
            users=list(accounts),
            accounts=list(accounts.values()),
        )
    )
    linked = cr.rowcount
    cr.execute(SQL("SELECT count(*) FROM calendar_sync_upgrade"))
    (held,) = cr.fetchone()
    if linked != held:
        raise ValueError(f"{code} calendar ids: {held} held, {linked} linked")
    for source in present:
        schema.drop_columns(cr, source.table, [column])
    _logger.info(
        "%s calendar: %s remote ids linked in %s calendars", code, linked, len(accounts)
    )
