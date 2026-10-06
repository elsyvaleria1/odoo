from odoo import api, fields, models


class MixinHrPayrollDeclaration(models.AbstractModel):
    _inherit = "mixin.hr.payroll.declaration"

    documents_count = fields.Integer(compute="_compute_documents_count")

    def action_see_documents(self):
        self.check_singleton()
        return {
            "name": self.env._("Documents"),
            "domain": [("id", "in", self.line_ids.document_id.ids)],
            "res_model": "document.document",
            "type": "ir.actions.act_window",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
        }

    @api.depends("line_ids.document_id")
    def _compute_documents_count(self) -> None:
        for sheet in self:
            sheet.documents_count = len(sheet.line_ids.document_id)

    def _get_posted_mail_template(self):
        return self.env.ref(
            "document_hr_payroll.mail_template_new_declaration",
            raise_if_not_found=False,
        )

    def _get_posted_document_owner(self, employee):
        return employee.user_id
