from odoo import models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    def document_hr_expense_create_hr_expense(self):
        if self.filtered(
            lambda doc: (
                doc.type != "binary"
                or doc.shortcut_document_id
                or doc.res_model == "hr.expense"
                or (
                    doc.mimetype
                    and "image" not in doc.mimetype.lower()
                    and "pdf" not in doc.mimetype.lower()
                )
            )
        ):
            _debug.logic("expense_refused", reason="bad_document", documents=self)
            raise UserError(
                self.env._(
                    "This action can only be applied on image and pdf not yet linked to an expense."
                )
            )

        if not self.env.user.employee_ids:
            _debug.logic("expense_refused", reason="no_employee", user=self.env.user)
            raise UserError(
                self.env._("You must be linked to an employee to create an expense.")
            )
        category_id = self.env.ref("hr_expense.product_product_no_cost").id
        expenses = self.env["hr.expense"].create(
            [
                {
                    "name": document.attachment_id.name,
                    "product_id": category_id,
                }
                for document in self
            ]
        )
        _debug.lifecycle("expenses_created", documents=self, expenses=expenses)
        for document, expense in zip(self, expenses, strict=False):
            if document.res_model or document.res_id:
                attachment = document.attachment_id.with_context(no_document=True).copy(
                    {
                        "res_model": expense._name,
                        "res_id": expense.id,
                    }
                )
                expense._message_set_main_attachment_id(attachment, force=True)
                document = document.copy({"attachment_id": attachment.id})
            else:
                document.attachment_id.with_context(no_document=True).write(
                    {"res_model": expense._name, "res_id": expense.id}
                )
                expense._message_set_main_attachment_id(
                    document.attachment_id, force=True
                )
            document.message_post(
                body=self.env._(
                    "Expense %s created from document", expense._get_html_link()
                )
            )

        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_expense.hr_expense_actions_my_all"
        )
        action["domain"] = [("id", "in", expenses.ids)]
        if len(expenses) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "views": [[False, "form"]],
                    "res_id": expenses[0].id,
                }
            )
        return action

    def _get_details_panel_res_models(self) -> list[str]:
        return [*super()._get_details_panel_res_models(), "hr.expense"]
