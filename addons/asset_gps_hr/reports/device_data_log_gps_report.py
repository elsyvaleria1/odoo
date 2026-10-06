from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.resource_asset_hr.models.resource_asset import live_custody_subquery


class DeviceGpsLogReport(models.Model):
    _inherit = "device.data.log.gps.report"

    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    operator_name = fields.Char(readonly=True)

    def _get_fields_select(self) -> dict:
        res = super()._get_fields_select()
        res.update(
            {
                "operator_id": "op.employee_id",
                "operator_name": "emp.name",
            },
        )
        return res

    def _get_from_tables(self) -> list:
        res = super()._get_from_tables()
        res.extend(
            [
                (
                    SQL(
                        live_custody_subquery(
                            "operator", "asset", "op", at="log.timestamp"
                        )
                    ),
                    "op",
                    "LEFT JOIN LATERAL",
                    "TRUE",
                ),
                ("hr_employee", "emp", "LEFT JOIN", "op.employee_id = emp.id"),
            ]
        )
        return res

    def _get_fields_group_by(self) -> list:
        res = super()._get_fields_group_by()
        res.extend(
            [
                "op.employee_id",
                "emp.name",
            ],
        )
        return res
