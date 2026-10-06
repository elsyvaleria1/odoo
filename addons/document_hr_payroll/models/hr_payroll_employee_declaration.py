from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrPayrollEmployeeDeclaration(models.Model):
    _inherit = "hr.payroll.employee.declaration"

    pdf_to_post = fields.Boolean()
    state = fields.Selection(
        selection_add=[
            ("pdf_to_post", "Queued PDF posting"),
            ("pdf_posted", "Posted PDF"),
        ],
        ondelete={
            "pdf_to_post": "set pdf_generated",
            "pdf_posted": "set pdf_generated",
        },
    )
    document_id = fields.Many2one(comodel_name="document.document")

    @api.depends("pdf_to_post", "document_id")
    def _compute_state(self):
        super()._compute_state()
        for declaration in self:
            if declaration.pdf_to_generate:
                # Work the cron still owes outranks the terminal state: super()
                # already set 'pdf_to_generate' and it must survive.
                continue
            if declaration.pdf_to_post:
                declaration.state = "pdf_to_post"
            elif declaration.document_id:
                declaration.state = "pdf_posted"

    def _post_pdf(self):
        """Post the PDF of every line that has one and is not posted yet.

        Returns the lines that actually got a document, so the caller can tell
        what was done instead of assuming the whole batch succeeded.
        """
        create_vals = []
        templates = {}
        lines_to_post = self.env["hr.payroll.employee.declaration"]
        for line in self:
            if line.document_id or not line.pdf_file:
                _debug.logic("declaration_post_skipped", line=line)
                continue
            lines_to_post += line
            if line.res_model not in templates:
                templates[line.res_model] = self.env[
                    line.res_model
                ]._get_posted_mail_template()
            template = templates[line.res_model]
            partner_id = (
                self.env[line.res_model]
                ._get_posted_document_owner(line.employee_id)
                .partner_id.id
            )
            folder = (
                self.env["document.document"]
                if line.employee_id.user_id
                else line.company_id._get_or_create_worker_payroll_folder()
            )
            owner_id = (
                line.employee_id.user_id.id if line.employee_id.user_id else False
            )
            access_ids = {}
            if (
                not owner_id
                and partner_id
                and folder
                and partner_id
                not in (
                    source["partner"].id for source in folder._access_graph_sources()
                )
            ):
                access_ids = {
                    "access_ids": [
                        Command.create({"partner_id": partner_id, "role": "view"})
                    ]
                }
            create_vals.append(
                {
                    "owner_id": owner_id,
                    **access_ids,
                    "partner_id": partner_id or False,
                    "datas": line.pdf_file,
                    "name": line.pdf_filename,
                    "folder_id": folder.id,
                    "res_model": "hr.payslip",  # Security Restriction to payroll managers
                    # allow anyone with the link (to retrieve declaration documents after employee's departure)
                    "access_via_link": "view",
                    "access_internal": "none",
                    "is_access_via_link_hidden": True,
                }
            )
            if template:
                template.send_mail(
                    line.employee_id.id,
                    email_layout_xmlid="mail.mail_notification_light",
                )

        _debug.pipeline("declaration_post", lines=lines_to_post)
        posted_documents = self.env["document.document"].create(create_vals)
        for line_to_post, posted_document in zip(
            lines_to_post, posted_documents, strict=True
        ):
            line_to_post.document_id = posted_document
        return lines_to_post

    @api.model_create_multi
    def create(self, vals_list):
        declarations = super().create(vals_list)
        if any(declaration.pdf_to_post for declaration in declarations):
            self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")
        return declarations

    def write(self, vals):
        res = super().write(vals)
        if vals.get("pdf_to_post"):
            self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")
        return res

    def action_post_in_documents(self) -> dict:
        # Mirror hr_payroll's action_generate_pdf: an empty selection means
        # "every declaration that is ready", not "nothing".
        declarations = self or self.search([("state", "=", "pdf_generated")])
        if not declarations:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "message": self.env._("There is no generated PDF to post."),
                },
            }
        # write() already triggers the cron for pdf_to_post, so do not trigger
        # a second time: one click used to queue two cron runs.
        declarations.write({"pdf_to_post": True})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("PDFs are gonna be posted in Documents shortly"),
            },
        }
