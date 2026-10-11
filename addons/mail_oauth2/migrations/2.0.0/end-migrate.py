import logging

from odoo.db import schema
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

TABLES = ("ir_mail_server", "fetchmail_server")


def migrate(cr, version):
    if not version:
        return
    for table in TABLES:
        if not schema.column_exists(cr, table, "oauth2_credential_id"):
            continue
        cr.execute(
            SQL(
                "SELECT id FROM %s WHERE oauth2_credential_id IS NOT NULL",
                SQL.identifier(table),
            )
        )
        if left := [row[0] for row in cr.fetchall()]:
            _logger.warning(
                "%s %s kept OAuth tokens no vendor adopted; they are dropped",
                table,
                left,
            )
        schema.drop_columns(cr, table, ["oauth2_credential_id"])
