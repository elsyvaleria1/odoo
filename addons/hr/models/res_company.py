from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    hr_config_id = fields.Many2one(
        comodel_name="hr.config",
        compute="_compute_hr_config_id",
        search="_search_hr_config_id",
    )

    employee_properties_definition = fields.PropertiesDefinition(
        related="hr_config_id.employee_properties_definition",
        readonly=False,
    )

    def _search_hr_config_id(self, operator, value):
        return self._search_config_link("hr.config", operator, value)

    def _compute_hr_config_id(self) -> None:
        self._compute_config_link("hr_config_id")
