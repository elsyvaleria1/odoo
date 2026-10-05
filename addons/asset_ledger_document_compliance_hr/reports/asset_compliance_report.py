from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.resource_asset_hr.models.resource_resource import live_custody_subquery

LIVE_MANAGER = live_custody_subquery("manager", "asset", "mgr")


class AssetComplianceReport(models.Model):
    _inherit = "asset.compliance.report"

    asset_manager_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
        help="Employee responsible for managing this asset",
    )

    def _get_from_tables(self) -> list:
        return [
            *super()._get_from_tables(),
            ("resource_resource", "asset", "LEFT JOIN", "asset.id = adt.asset_id"),
            (SQL(f"LATERAL {LIVE_MANAGER}"), "mgr", "LEFT JOIN", "TRUE"),
        ]

    def _get_fields_select(self) -> dict:
        res = super()._get_fields_select()
        res["asset_manager_id"] = "mgr.employee_id"
        return res

    def _get_fields_group_by(self) -> list:
        res = super()._get_fields_group_by()
        res.append("mgr.employee_id")
        return res
