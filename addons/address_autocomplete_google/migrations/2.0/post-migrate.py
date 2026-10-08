import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

OLD_KEY = "google_address_autocomplete.google_places_api_key"
NEW_KEY = "address_autocomplete_google.api_key"


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Credential = env["credential.credential"]
    if key := Credential._get_system_secret(OLD_KEY):
        Credential._set_system_secret(NEW_KEY, key)
        Credential._set_system_secret(OLD_KEY, False)

    # Google was the only provider there was: a database that installed it
    # chose it
    icp = env["ir.config_parameter"]
    if not icp.get_param("address_autocomplete.provider"):
        icp.set_param("address_autocomplete.provider", "google")

    # the widget is the generic module's, under the generic key; a word match,
    # so a CSS class naming the widget (o_field_google_address_autocomplete)
    # is left as written
    cr.execute(
        SQL(
            r"""
            UPDATE ir_ui_view
               SET arch_db = regexp_replace(
                       arch_db::text,
                       '\mgoogle_address_autocomplete\M',
                       'address_autocomplete',
                       'g'
                   )::jsonb
             WHERE arch_db::text ~ '\mgoogle_address_autocomplete\M'
            """
        )
    )
    if cr.rowcount:
        _logger.info("%d views now use the address_autocomplete widget", cr.rowcount)
