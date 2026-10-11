import logging
from datetime import datetime

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    dated_models = [
        name
        for name, model in env.registry.items()
        if not model._abstract and hasattr(model, "_get_link_expiry")
    ]
    cr.execute(
        SQL(
            "UPDATE access_link SET dated_by_record = TRUE "
            "WHERE cause = 'notification' AND res_model = ANY(%s)",
            dated_models,
        )
    )
    _logger.info("access links following their record's date: %s", cr.rowcount)
    cr.execute(
        SQL(
            """
            SELECT id FROM access_link
             WHERE dated_by_record
               AND revoked_at IS NULL
               AND expiry_waived IS NOT TRUE
               AND date_to > (now() AT TIME ZONE 'UTC')
               AND date_to >= date_trunc('second', write_date) + %s
            """,
            env["access.link"]._get_cause_lifetimes()["notification"],
        )
    )
    clamped = env["access.link"].browse(row[0] for row in cr.fetchall())
    moved: dict[int, datetime] = {}
    for model_name, links in clamped.grouped("res_model").items():
        records = env[model_name].browse(links.mapped("res_id")).exists()
        expiries = {record.id: record._get_link_expiry() for record in records}
        for link in links:
            expiry = expiries.get(link.res_id)
            if expiry and expiry > link.date_to:
                moved[link.id] = expiry
    if moved:
        cr.execute(
            SQL(
                """
                UPDATE access_link AS link
                   SET date_to = moved.date_to
                  FROM unnest(%s::int[], %s::timestamp[]) AS moved(id, date_to)
                 WHERE link.id = moved.id
                """,
                list(moved),
                list(moved.values()),
            )
        )
    _logger.info("access links moved to their record's date: %s", len(moved))
