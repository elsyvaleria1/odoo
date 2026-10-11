import json

from odoo import SUPERUSER_ID, api
from odoo.db import schema
from odoo.libs.sql.utils import get_index_name
from odoo.tools import SQL

LEGACY_STATES = {
    "no_extract_requested": "none",
    "not_enough_credit": "failed",
    "error_status": "failed",
    "waiting_extraction": "waiting",
    "extract_not_ready": "waiting",
    "waiting_validation": "done",
    "to_validate": "done",
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model in env.registry.values():
        field = model._fields.get("extract_state")
        if not (
            model._auto
            and not model._abstract
            and field
            and field.store
            and not field.inherited
        ):
            continue
        table = model._table
        schema.drop_index(cr, get_index_name(table, "extract_state"), table)
        cr.execute(
            SQL(
                """
                UPDATE %(table)s
                   SET extract_state = (%(mapping)s::jsonb ->> extract_state)
                 WHERE extract_state = ANY(%(legacy)s)
                """,
                table=SQL.identifier(table),
                mapping=json.dumps(LEGACY_STATES),
                legacy=list(LEGACY_STATES),
            )
        )
