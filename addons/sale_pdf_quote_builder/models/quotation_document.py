from typing import Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict, ormcache

from odoo.addons.sale_pdf_quote_builder import utils

_debug = DebugLog(__name__)


class QuotationDocument(models.Model):
    _name = "quotation.document"
    _description = "Quotation's Headers & Footers"
    _inherits = {
        "ir.attachment": "ir_attachment_id",
    }
    _order = "document_type desc, sequence, name"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", hierarchy="parent_of"),
        }
    )

    ir_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Related attachment",
        index=True,
        required=True,
        ondelete="cascade",
    )
    document_type = fields.Selection(
        selection=[("header", "Header"), ("footer", "Footer")],
        default="header",
        required=True,
    )
    active = fields.Boolean(
        default=True,
        help="If unchecked, it will allow you to hide the header or footer without removing it.",
    )
    sequence = fields.Integer(default=10)
    quotation_template_ids = fields.Many2many(
        comodel_name="sale.order.template",
        relation="header_footer_quotation_template_rel",
        string="Quotation Templates",
        check_company=True,
        groups="sale.group_sale_salesman",
    )
    form_field_ids = fields.Many2many(
        comodel_name="sale.pdf.form.field",
        string="Form Fields Included",
        compute="_compute_form_field_ids",
        store=True,
        domain=[("document_type", "=", "quotation_document")],
    )
    add_by_default = fields.Boolean(
        default=False,
        help="If checked, this header or footer will be added by default on new quotes.",
    )

    @api.constrains("datas")
    def _check_pdf_validity(self) -> None:
        for doc in self:
            if doc.datas and not doc.mimetype.endswith("pdf"):
                _debug.logic(
                    "quotation_document_rejected", document=doc, reason="not_a_pdf"
                )
                raise ValidationError(
                    self.env._("Only PDF documents can be used as header or footer.")
                )
            utils._check_document_not_encrypted(
                doc.ir_attachment_id._get_content_prefix()
            )

    @api.depends("datas")
    def _compute_form_field_ids(self) -> None:
        self.form_field_ids = [Command.clear()]
        document_to_parse = self.filtered(lambda doc: doc.datas)
        _debug.pipeline(
            "form_fields_parsed",
            documents=self,
            with_data=document_to_parse,
            kind="quotation_document",
        )
        if document_to_parse:
            doc_type = "quotation_document"
            self.env[
                "sale.pdf.form.field"
            ]._create_or_update_form_fields_on_pdf_records(document_to_parse, doc_type)

    def _filtered_available_for_order(self, order) -> Self:
        return self.filtered(
            lambda doc: (
                not (templates := doc.sudo().quotation_template_ids)
                or order.template_id in templates
            )
        )

    def action_view_pdf_form_fields(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Form Fields"),
            "type": "ir.actions.act_window",
            "res_model": "sale.pdf.form.field",
            "view_mode": "list",
            "context": {
                "default_document_type": "quotation_document",
                "default_product_document_ids": False,
                "default_quotation_document_ids": self.id,
                "search_default_context_document": True,
            },
            "target": "current",
        }

    @api.model
    @ormcache("self.env.access_signature")
    def _is_any_defined(self) -> bool:
        return bool(self.search_count([], limit=1))

    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        _debug.lifecycle("create", documents=docs, rows=len(vals_list))
        for doc in docs:
            doc.write({"res_model": "quotation.document", "res_id": doc.id})
        self.env.registry.clear_cache()
        return docs

    def write(self, vals):
        result = super().write(vals)
        if vals.get("active") or "company_id" in vals:
            self.env.registry.clear_cache()
        return result
