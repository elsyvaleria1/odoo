from odoo import api, models

from odoo.addons.worksheet.models.worksheet_template import WorksheetModelHooks


class WorksheetTemplate(models.Model):
    _inherit = "worksheet.template"

    @api.model
    def _get_worksheet_model_hooks(self):
        return super()._get_worksheet_model_hooks() | {
            "maintenance.order": WorksheetModelHooks(
                module="maintenance_worksheet",
                user_group="base.group_user",
                manager_group="maintenance.group_equipment_manager",
                access_all_groups=("maintenance.group_equipment_manager",),
            ),
        }

    @api.model
    def _get_models_to_check_dict(self):
        res = super()._get_models_to_check_dict()
        res["maintenance.order"] = [("maintenance.order", "Maintenance Order")]
        return res
