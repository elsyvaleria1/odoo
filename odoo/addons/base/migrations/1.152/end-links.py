import logging
from datetime import datetime

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Link = env["access.link"]
    cause = "notification"
    dated_models = [
        name
        for name, model in env.registry.items()
        if not model._abstract and Link._is_dated_by_record(env[name], cause)
    ]
    cr.execute(
        SQL(
            "UPDATE access_link SET dated_by_record = TRUE "
            "WHERE cause = %s AND res_model = ANY(%s)",
            cause,
            dated_models,
        )
    )
    _logger.info("access links following their record's date: %s", cr.rowcount)
    cr.execute(
        SQL(
            """
            SELECT id, date_to >= date_trunc('second', write_date) + %s
              FROM access_link
             WHERE dated_by_record
               AND revoked_at IS NULL
               AND expiry_waived IS NOT TRUE
               AND date_to > (now() AT TIME ZONE 'UTC')
            """,
            Link._get_cause_lifetimes()[cause],
        )
    )
    clamped = dict(cr.fetchall())
    moved: dict[int, datetime] = {}
    for model_name, links in Link.browse(clamped).grouped("res_model").items():
        records = env[model_name].browse(links.mapped("res_id")).exists()
        expiries = {record.id: record._get_link_expiry() for record in records}
        for link in links:
            expiry = expiries.get(link.res_id)
            if expiry and (
                expiry < link.date_to or (clamped[link.id] and expiry > link.date_to)
            ):
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
