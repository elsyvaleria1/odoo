from odoo import SUPERUSER_ID, api

from odoo.addons.mrp_maintenance.migration import migrate_equipment_resources


def migrate(cr, version):
    if version:
        migrate_equipment_resources(
            api.Environment(
                cr, SUPERUSER_ID, {"tracking_disable": True, "active_test": False}
            )
        )
