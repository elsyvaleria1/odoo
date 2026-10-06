import logging

from odoo import SUPERUSER_ID, api
from odoo.db import schema
from odoo.fields import Domain
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

# mixin.resource no longer stores these on its hosts
PROJECTED = {"resource_calendar_id": "resource_id.calendar_id"}


def _ledger_follows_its_hosts(cr, env):
    # The hosts of the ledger depend on resource and load after it, so only
    # now can their tables be named.
    cr.execute(
        "SELECT DISTINCT res_model FROM resource_reservation WHERE res_model IS NOT NULL"
    )
    for (model_name,) in cr.fetchall():
        Model = env.get(model_name)
        if Model is None or Model._abstract or Model._transient or not Model._auto:
            _logger.info(
                "resource: reservations of %s left alone, no table holds them",
                model_name,
            )
            continue
        table = SQL.identifier(Model._table)
        cr.execute(
            SQL(
                """
                DELETE FROM resource_reservation rr
                 WHERE rr.res_model = %s
                   AND NOT EXISTS (SELECT 1 FROM %s t WHERE t.id = rr.res_id)
                """,
                model_name,
                table,
            )
        )
        if cr.rowcount:
            _logger.info(
                "resource: %s orphaned reservation(s) of %s deleted",
                cr.rowcount,
                model_name,
            )
        active = Model._fields.get("active")
        if active is not None and active.store:
            cr.execute(
                SQL(
                    """
                    UPDATE resource_reservation rr
                       SET active = t.active
                      FROM %s t
                     WHERE rr.res_model = %s
                       AND rr.res_id = t.id
                       AND rr.active IS DISTINCT FROM t.active
                    """,
                    table,
                    model_name,
                )
            )
            if cr.rowcount:
                _logger.info(
                    "resource: %s reservation(s) of %s took their host's active state",
                    cr.rowcount,
                    model_name,
                )


def _drop_unstored_projections(cr, env):
    for model in env.values():
        if model._abstract or not model._auto:
            continue
        orphans = [
            name
            for name, related in PROJECTED.items()
            if (field := model._fields.get(name)) is not None
            and field.related == related
            and not field.store
        ]
        if orphans:
            schema.drop_columns(cr, model._table, orphans)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    if schema.table_exists(cr, "resource_reservation"):
        _ledger_follows_its_hosts(cr, env)
        # Every repair of shares, dates and hour accounting since 1.2 lands
        # here at once: the hours are recomputed from what each claim now
        # holds, and the hosts' derived hours follow.
        env["resource.reservation"]._recompute_allocated_hours(Domain.TRUE)
        env.flush_all()
    _drop_unstored_projections(cr, env)
    if schema.column_exists(cr, "res_company", "resource_calendar_id"):
        cr.execute("ALTER TABLE res_company DROP COLUMN resource_calendar_id CASCADE")
