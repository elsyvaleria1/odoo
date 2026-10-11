"""What an adapter's upgrade does with the synchronization state it kept
before accounts and links existed; its migrations call this."""

import dataclasses
import logging

from odoo import SUPERUSER_ID
from odoo.db import schema
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def adopt_settings_columns(env, code, columns, dropped=()) -> None:
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
    owner: SQL


def link_remote_ids(env, code, sources, column) -> None:
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


def pend_links(env, code, column) -> None:
    cr = env.cr
    for table, field in (
        ("calendar_event", "event_id"),
        ("calendar_recurrence", "recurrence_id"),
    ):
        if not schema.column_exists(cr, table, column):
            continue
        cr.execute(
            SQL(
                """UPDATE calendar_sync_link link
                      SET pending = true
                     FROM %(table)s rec, calendar_sync_account account
                    WHERE link.%(field)s = rec.id
                      AND rec.%(column)s
                      AND account.id = link.account_id
                      AND account.provider = %(code)s""",
                table=SQL.identifier(table),
                field=SQL.identifier(field),
                column=SQL.identifier(column),
                code=code,
            )
        )
        _logger.info("%s calendar: %s links of %s pending", code, cr.rowcount, table)
        schema.drop_columns(cr, table, [column])


def settle_duplicate_links(cr) -> None:
    if not schema.table_exists(cr, "calendar_sync_link"):
        return
    for field, table in (
        ("event_id", "calendar_event"),
        ("recurrence_id", "calendar_recurrence"),
    ):
        cr.execute(
            SQL(
                """WITH ranked AS (
                       SELECT link.id, link.%(field)s AS record_id,
                              first_value(link.%(field)s) OVER same AS kept,
                              row_number() OVER same AS rank
                         FROM calendar_sync_link link
                         JOIN %(table)s rec ON rec.id = link.%(field)s
                       WINDOW same AS (
                           PARTITION BY link.account_id, link.remote_id
                           ORDER BY rec.active DESC,
                                    rec.write_date DESC NULLS LAST, rec.id
                       )
                   )
                   UPDATE calendar_sync_link link
                      SET remote_id = NULL,
                          pending = false,
                          error = 'duplicate of ' || %(table_name)s || ' ' || ranked.kept
                     FROM ranked
                    WHERE ranked.id = link.id AND ranked.rank > 1
                RETURNING link.id, ranked.record_id""",
                field=SQL.identifier(field),
                table=SQL.identifier(table),
                table_name=table,
            )
        )
        if settled := cr.fetchall():
            _logger.warning(
                "calendar sync: %s links of %s duplicating another record's "
                "remote id set aside: %s",
                len(settled),
                table,
                settled,
            )


@dataclasses.dataclass(frozen=True)
class CalendarCopySource:
    table: str
    link_field: str
    organizer: SQL
    columns: dict


def link_calendar_copies(env, code, sources) -> None:
    cr = env.cr
    present = [
        source
        for source in sources
        if schema.column_exists(cr, source.table, source.columns["remote_id"])
    ]
    if not present:
        return
    link_fields = ("remote_id", "universal_id", "remote_master_id")
    cr.execute(
        SQL(
            "CREATE TEMP TABLE calendar_sync_upgrade ON COMMIT DROP AS %s",
            SQL(" UNION ALL ").join(
                SQL(
                    """SELECT %(link_field)s AS link_field, rec.id AS res_id,
                              rec.active, rec.write_date,
                              %(organizer)s AS organizer,
                              COALESCE(rec.create_uid, %(root)s) AS user_id,
                              %(ids)s, NULL::varchar AS error
                         FROM %(table)s rec
                        WHERE %(remote_id)s IS NOT NULL
                           OR %(universal_id)s IS NOT NULL""",
                    link_field=source.link_field,
                    organizer=source.organizer,
                    root=SUPERUSER_ID,
                    ids=SQL(", ").join(
                        SQL(
                            "%s::varchar AS %s",
                            SQL.identifier("rec", source.columns[field])
                            if field in source.columns
                            else SQL("NULL"),
                            SQL.identifier(field),
                        )
                        for field in link_fields
                    ),
                    table=SQL.identifier(source.table),
                    remote_id=SQL.identifier("rec", source.columns["remote_id"]),
                    universal_id=SQL.identifier("rec", source.columns["universal_id"]),
                )
                for source in present
            ),
        )
    )
    cr.execute(SQL("SELECT count(*) FROM calendar_sync_upgrade"))
    (held,) = cr.fetchone()
    cr.execute(
        SQL(
            """DELETE FROM calendar_sync_upgrade original
                WHERE original.universal_id IS NULL
                  AND original.link_field = 'event_id'
                  AND EXISTS (
                      SELECT 1 FROM calendar_sync_upgrade copy
                       WHERE copy.link_field = original.link_field
                         AND copy.remote_id = original.remote_id
                         AND copy.universal_id IS NOT NULL
                  )
            RETURNING original.res_id"""
        )
    )
    if originals := [res_id for (res_id,) in cr.fetchall()]:
        _logger.info(
            "%s calendar: %s events left behind by their deletion copy, not linked: %s",
            code,
            len(originals),
            originals,
        )
    cr.execute(
        SQL(
            "SELECT DISTINCT organizer FROM calendar_sync_upgrade"
            " WHERE organizer IS NOT NULL"
        )
    )
    Users = env["res.users"].with_context(active_test=False)
    connected = [
        user_id
        for (user_id,) in cr.fetchall()
        if Users.browse(user_id)._calendar_sync_connection(code)
    ]
    cr.execute(
        SQL(
            "UPDATE calendar_sync_upgrade SET user_id = organizer"
            " WHERE organizer = ANY(%s)",
            connected,
        )
    )
    cr.execute(
        SQL(
            """WITH ranked AS (
                   SELECT link_field, res_id,
                          first_value(res_id) OVER same AS kept,
                          row_number() OVER same AS rank
                     FROM calendar_sync_upgrade
                    WHERE remote_id IS NOT NULL
                   WINDOW same AS (
                       PARTITION BY user_id, link_field, remote_id
                       ORDER BY active DESC, write_date DESC NULLS LAST, res_id
                   )
               )
               UPDATE calendar_sync_upgrade upgrade
                  SET remote_id = NULL,
                      error = 'duplicate of ' || ranked.link_field || ' '
                              || ranked.kept || ' at upgrade'
                 FROM ranked
                WHERE ranked.rank > 1
                  AND ranked.link_field = upgrade.link_field
                  AND ranked.res_id = upgrade.res_id
            RETURNING upgrade.link_field, upgrade.res_id"""
        )
    )
    if duplicates := cr.fetchall():
        _logger.warning(
            "%s calendar: %s records holding a remote id another record of the "
            "calendar holds linked without it: %s",
            code,
            len(duplicates),
            duplicates,
        )
    cr.execute(SQL("SELECT DISTINCT user_id FROM calendar_sync_upgrade"))
    Account = env["calendar.sync.account"]
    accounts = {
        user_id: Account._for(Users.browse(user_id), code).id
        for (user_id,) in cr.fetchall()
    }
    env.flush_all()
    cr.execute(
        SQL(
            """INSERT INTO calendar_sync_link (
                   account_id, event_id, recurrence_id, remote_id, universal_id,
                   remote_master_id, pending, error,
                   create_uid, write_uid, create_date, write_date
               )
               SELECT owner.account_id,
                      CASE upgrade.link_field WHEN 'event_id' THEN upgrade.res_id END,
                      CASE upgrade.link_field WHEN 'recurrence_id' THEN upgrade.res_id END,
                      upgrade.remote_id, upgrade.universal_id,
                      upgrade.remote_master_id, false, upgrade.error,
                      %(uid)s, %(uid)s,
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
    if linked != held - len(originals):
        raise ValueError(
            f"{code} calendar ids: {held} held, {len(originals)} left behind,"
            f" {linked} linked"
        )
    cr.execute(
        SQL(
            """SELECT count(*) FILTER (WHERE remote_id IS NOT NULL
                                         AND universal_id IS NOT NULL),
                      count(*) FILTER (WHERE remote_id IS NULL AND error IS NULL),
                      count(*) FILTER (WHERE universal_id IS NULL
                                         AND error IS NULL),
                      count(*) FILTER (WHERE universal_id IS NOT NULL AND EXISTS (
                          SELECT 1 FROM calendar_sync_upgrade other
                           WHERE other.user_id = upgrade.user_id
                             AND other.link_field = upgrade.link_field
                             AND other.universal_id = upgrade.universal_id
                             AND other.res_id != upgrade.res_id
                      ))
                 FROM calendar_sync_upgrade upgrade"""
        )
    )
    both, universal_only, remote_only, shared_universal = cr.fetchone()
    for source in present:
        schema.drop_columns(cr, source.table, list(source.columns.values()))
    _logger.info(
        "%s calendar: %s records linked in %s calendars: %s by both ids, %s by "
        "their universal id alone, %s by their remote id alone, %s without the "
        "remote id another holds, %s sharing a universal id in one calendar; "
        "%s left behind",
        code,
        linked,
        len(accounts),
        both,
        universal_only,
        remote_only,
        len(duplicates),
        shared_universal,
        len(originals),
    )
