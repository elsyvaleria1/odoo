from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_CONTROLS = ("hr_presence_control_ip", "hr_presence_control_email")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    @api.model_create_multi
    def create(self, vals_list):
        companies = self.env["res.company"].browse(
            {vals.get("company_id") or self.env.company.id for vals in vals_list}
        )
        before = {
            company.id: tuple(company.hr_config_id[name] for name in _CONTROLS)
            for company in companies.sudo()
        }
        configs = super().create(vals_list)
        companies.sudo().hr_config_id.invalidate_recordset(_CONTROLS)
        turned_on = companies.sudo().filtered(
            lambda company: (
                tuple(company.hr_config_id[name] for name in _CONTROLS)
                != before[company.id]
                and any(company.hr_config_id[name] for name in _CONTROLS)
            )
        )
        if turned_on:
            _debug.lifecycle("presence_control_changed", companies=turned_on)
            self.env["hr.employee"]._check_presence()
        return configs
