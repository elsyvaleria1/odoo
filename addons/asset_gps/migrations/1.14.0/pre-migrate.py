from odoo import SUPERUSER_ID, api

from odoo.addons.asset_gps.tools.compatibility import register_legacy_gps_privileges


def migrate(cr, version):
    if version:
        register_legacy_gps_privileges(api.Environment(cr, SUPERUSER_ID, {}))
