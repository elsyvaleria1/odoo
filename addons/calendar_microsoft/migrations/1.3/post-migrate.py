import logging

from odoo import SUPERUSER_ID, api
from odoo.db import schema
from odoo.tools import SQL

from odoo.addons.calendar_microsoft.utils.calendar_microsoft import CALENDAR_SCOPE

_logger = logging.getLogger(__name__)

LEGACY_COLUMNS = (
    "microsoft_calendar_credential_id",
    "microsoft_calendar_token_validity",
)


def migrate(cr, version):
    if not version or not schema.column_exists(
        cr, "res_users", "microsoft_calendar_credential_id"
    ):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        SQL(
            "SELECT id, microsoft_calendar_credential_id,"
            "       microsoft_calendar_token_validity"
            "  FROM res_users"
            " WHERE microsoft_calendar_credential_id IS NOT NULL"
        )
    )
    rows = cr.fetchall()
    service = env.ref("integration_microsoft.service_microsoft")
    Users = env["res.users"].with_context(active_test=False)
    Credential = env["credential.credential"].with_context(active_test=False)
    for user_id, credential_id, expires in rows:
        env["integration.connection"]._personal(
            service, Users.browse(user_id), scope=CALENDAR_SCOPE
        )._adopt_credential(Credential.browse(credential_id), expires=expires)
    _logger.info(
        "%s Microsoft calendars moved onto their users' connections", len(rows)
    )
    schema.drop_columns(cr, "res_users", LEGACY_COLUMNS)
