from odoo import api, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.onchange("wage_with_holidays")
    def _onchange_wage_with_holidays(self) -> None:
        self.version_id._onchange_wage_with_holidays()

    @api.onchange("final_yearly_costs")
    def _onchange_final_yearly_costs(self) -> None:
        self.version_id._onchange_final_yearly_costs()

    def action_show_contract_reviews(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.version",
            "views": [[False, "list"], [False, "form"]],
            "domain": [["origin_version_id", "=", self.version_id.id]],
            "context": {"active_test": False},
            "name": "Contracts Reviews",
        }

    def action_show_offers(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "hr_contract_salary.hr_contract_salary_offer_action"
        )
        action["domain"] = [("employee_id", "in", self.id)]
        action["context"] = {
            "default_employee_id": self.id,
            "default_employee_version_id": self.version_id.id,
        }
        return action

    def action_generate_offer(self):

        offer_validity_period = int(
            self.env.registry.settings.get(
                self.env,
                "hr_contract_salary.employee_salary_simulator_link_validity",
                30,
            )
        )
        offer_values = self._prepare_offer_context()
        offer_values["default_validity_days_count"] = offer_validity_period

        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "hr_contract_salary.action_hr_offer_new"
        )
        action["domain"] = [("employee_id", "in", self.id)]
        action["context"] = {
            "active_model": "hr.version",
            "default_employee_id": self.id,
            "is_simulation_offer": True,
            **offer_values,
        }
        return action

    def _prepare_offer_context(self):
        self.check_singleton()
        return {
            "default_company_id": self.company_id.id,
            "default_contract_template_id": self.version_id.id,
            "default_employee_version_id": self.version_id.id,
            "default_final_yearly_costs": self.final_yearly_costs,
            "default_job_title": self.job_id.name,
            "default_employee_job_id": self.job_id.id,
            "default_department_id": self.department_id.id,
            "default_display_name": self.env._(
                "Offer for %(recipient)s", recipient=self.name
            ),
        }
