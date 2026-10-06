from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    website_id = fields.Many2one(
        comodel_name="website",
        compute="_compute_website_id",
        store=True,
        readonly=False,
        domain="['|', ('company_id', '=', company_id), ('company_id', 'in', context.get('allowed_company_ids'))]",
        ondelete="set null",
    )

    @api.depends("website_id")
    def _compute_access_url(self):
        return super()._compute_access_url()

    @api.depends("company_id", "company_id.website_id")
    def _compute_website_id(self) -> None:
        for document in self.filtered(
            lambda d: not d.website_id or d.website_id.company_id != d.company_id
        ):
            _debug.logic(
                "website_assigned",
                document=document,
                by="company" if document.company_id.website_id else "env",
            )
            document.website_id = (
                document.company_id.website_id or self.env.company.website_id
            )

    def _check_website_id(self) -> None:
        invalid_docs = [
            doc.name
            for doc in self.filtered("website_id")
            if doc.company_id != doc.website_id.company_id
            and self.env.companies
            and doc.website_id.company_id not in self.env.companies
        ]
        if invalid_docs:
            _debug.logic(
                "website_refused", reason="company_mismatch", count=len(invalid_docs)
            )
            raise AccessError(
                self.env._(
                    "You can't set this website for the following documents:\n- "
                )
                + "\n- ".join(invalid_docs)
            )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        if not self.env.is_superuser():
            res._check_website_id()
        return res

    def write(self, vals):
        res = super().write(vals)
        if not self.env.is_superuser() and vals.keys() & {"website_id", "company_id"}:
            self._check_website_id()
        return res
