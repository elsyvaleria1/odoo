from markupsafe import Markup

from odoo import Command, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrPayslipUpdateLine(models.TransientModel):
    _name = "wizard.hr.payslip.update.line"
    _description = "Edit payslip lines wizard"

    payslip_id = fields.Many2one(
        comodel_name="hr.payslip",
        readonly=True,
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name="wizard.hr.payslip.update.line.payslip.line",
        inverse_name="edit_payslip_lines_wizard_id",
        string="Payslip Lines",
    )
    worked_days_line_ids = fields.One2many(
        comodel_name="wizard.hr.payslip.update.line.worked_days",
        inverse_name="edit_payslip_lines_wizard_id",
        string="Worked Days Lines",
    )

    ytd_computation = fields.Boolean(related="payslip_id.ytd_computation")

    def recompute_following_lines(self, line_id):
        self.check_singleton()
        wizard_line = self.env["wizard.hr.payslip.update.line.payslip.line"].browse(
            line_id
        )
        # `line_id` llega del cliente: sin esto, cualquiera puede recomputar
        # una linea de OTRO asistente pasando su id.
        if wizard_line not in self.line_ids:
            raise UserError(
                self.env._("This payslip line does not belong to this wizard.")
            )
        reload_wizard = {
            "type": "ir.actions.act_window",
            "res_model": "wizard.hr.payslip.update.line",
            "view_mode": "form",
            "res_id": self.id,
            "views": [(False, "form")],
            "target": "new",
        }
        if not wizard_line.salary_rule_id:
            _debug.logic("recompute_skipped", reason="no_rule", line=wizard_line)
            return reload_wizard
        localdict = self.payslip_id._prepare_salary_rule_context()
        result_rules_dict = localdict["result_rules"]
        remove_lines = False
        lines_to_remove = []
        blacklisted_rule_ids = []
        for line in sorted(self.line_ids, key=lambda x: x.sequence):
            if remove_lines and line.code in self.payslip_id.line_ids.mapped("code"):
                lines_to_remove.append((2, line.id, 0))
            else:
                if line == wizard_line:
                    line._compute_total()
                    remove_lines = True
                blacklisted_rule_ids.append(line.salary_rule_id.id)
                localdict[line.code] = line.total
                result_rules_dict[line.code] = {
                    "total": line.total,
                    "amount": line.amount,
                    "quantity": line.quantity,
                    "rate": line.rate,
                    "ytd": line.ytd,
                }
                if line.salary_rule_id.category_id:
                    localdict = (
                        line.salary_rule_id.category_id._get_salary_rule_category_sum(
                            localdict, line.total
                        )
                    )

        self.line_ids = lines_to_remove + [
            Command.create(line)
            for line in self.payslip_id._get_payslip_lines(
                forced_localdict=localdict, blacklisted_rule_ids=blacklisted_rule_ids
            )
        ]
        return reload_wizard

    def recompute_worked_days_lines(self):
        self.check_singleton()
        total_amount = sum(l.amount for l in self.worked_days_line_ids)
        lines = sorted(self.line_ids, key=lambda x: x.sequence)
        if not lines:
            return False
        lines[0].update(
            {
                "amount": total_amount,
                "rate": 100,
                "quantity": 1,
            }
        )
        return self.recompute_following_lines(lines[0].id)

    def action_validate_edition(self) -> None:
        wrong_state_payslips = self.payslip_id.filtered(lambda p: p.state != "draft")
        if wrong_state_payslips:
            raise UserError(
                self.env._(
                    "This action is only allowed on draft payslips: %s is no"
                    " longer a draft.",
                    wrong_state_payslips[0].name,
                )
            )
        today = fields.Date.today()
        old_lines_data = {
            line.salary_rule_id.id: {
                "name": line.name,
                "quantity": line.quantity,
                "rate": line.rate,
                "amount": line.amount,
                "total": line.total,
                "ytd": line.ytd,
            }
            for line in self.payslip_id.line_ids
        }
        old_worked_days_data = {
            wd.work_entry_type_id.id: {
                "name": wd.name,
                "number_of_days": wd.number_of_days,
                "number_of_hours": wd.number_of_hours,
                "amount": wd.amount,
                "ytd": wd.ytd,
            }
            for wd in self.payslip_id.worked_days_line_ids
        }
        _debug.pipeline(
            "validate_edition",
            wizards=self,
            payslips=self.payslip_id,
            old_lines=len(old_lines_data),
            old_worked_days=len(old_worked_days_data),
        )
        self.mapped("payslip_id.line_ids").unlink()
        self.mapped("payslip_id.worked_days_line_ids").unlink()
        for wizard in self:
            lines = [
                Command.create(line)
                for line in wizard.line_ids._export_to_payslip_line()
            ]
            worked_days_lines = [
                Command.create(line)
                for line in wizard.worked_days_line_ids._export_to_worked_days_line()
            ]
            wizard.payslip_id.with_context(payslip_no_recompute=True).write(
                {
                    "edited": True,
                    "line_ids": lines,
                    "worked_days_line_ids": worked_days_lines,
                    "compute_date": today,
                }
            )
            _debug.lifecycle(
                "payslip_lines_replaced",
                payslip=wizard.payslip_id,
                lines=len(lines),
                worked_days=len(worked_days_lines),
                now_lines=wizard.payslip_id.line_ids,
            )

            line_fields = {
                "name": self.env._("Name"),
                "quantity": self.env._("Quantity"),
                "rate": self.env._("Rate"),
                "amount": self.env._("Amount"),
                "total": self.env._("Total"),
                "ytd": self.env._("YTD"),
            }
            worked_days_fields = {
                "name": self.env._("Name"),
                "number_of_hours": self.env._("Number of Hours"),
                "number_of_days": self.env._("Number of Days"),
                "amount": self.env._("Amount"),
                "ytd": self.env._("YTD"),
            }
            worked_days_changes = self._generate_changed_values(
                worked_days_lines,
                old_worked_days_data,
                worked_days_fields,
                "work_entry_type_id",
            )
            line_changes = self._generate_changed_values(
                lines, old_lines_data, line_fields, "salary_rule_id"
            )

            _debug.logic(
                "edition_changes",
                payslip=wizard.payslip_id,
                line_changes=bool(line_changes),
                worked_days_changes=bool(worked_days_changes),
            )
            if line_changes or worked_days_changes:
                message_body = Markup("%s<br/>") % self.env._(
                    "This payslip has been manually edited by %(user)s.",
                    user=self.env.user.name,
                )
                message_body += worked_days_changes + line_changes
                wizard.payslip_id.message_post(body=message_body)

    def _generate_changed_values(self, new_items, old_data, fields, item):
        changes_list = []
        for new_item in new_items:
            new_item_data = new_item[2]
            old_item_data = old_data.get(new_item_data[item], {})
            changes = []
            line_name = new_item_data["name"]

            for field, field_name in fields.items():
                if field == "ytd" and not self.ytd_computation:
                    continue
                old_value = old_item_data.get(field, None)
                new_value = new_item_data.get(field, None)
                if old_value != new_value:
                    changes.append(
                        Markup(
                            '<li><strong>%s: %s → <span class="text-info">%s</span></strong></li>'
                        )
                        % (field_name, old_value, new_value)
                    )
            if changes:
                changes_list.append(
                    Markup("<li>%s</li><ul>") % (line_name)
                    + Markup("").join(changes)
                    + Markup("</ul>")
                )
        if not changes_list:
            return ""
        if item == "salary_rule_id":
            message_body = Markup("%s<ul>") % self.env._("Payslip Lines Changes:")
        else:
            message_body = Markup("%s<ul>") % self.env._("Worked Days lines Changes:")
        message_body += Markup("").join(changes_list)
        message_body += Markup("</ul>")
        return message_body
