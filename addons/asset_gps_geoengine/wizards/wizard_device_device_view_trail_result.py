from odoo import api, fields, models


class WizardDeviceDeviceViewTrailResult(models.TransientModel):
    _inherit = "wizard.device.device.view.trail.result"

    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Asset/Vehicle",
    )
    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Operator/Driver",
    )
    operator_name = fields.Char(compute="_compute_display_fields")
    asset_name = fields.Char(compute="_compute_display_fields")
    license_plate = fields.Char(compute="_compute_display_fields")

    @api.depends("operator_id", "asset_id")
    def _compute_display_fields(self) -> None:
        super()._compute_display_fields()
        for result in self:
            result.operator_name = result.operator_id.name if result.operator_id else ""
            result.asset_name = result.asset_id.name if result.asset_id else ""
            result.license_plate = (
                result.asset_id.license_plate
                if result.asset_id and result.asset_id.license_plate
                else ""
            )
