from typing import TYPE_CHECKING, Literal

from odoo import Command, fields, models

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_category import ApprovalCategory
    from odoo.addons.base.models.res_partner import ResPartner


class ApprovalTestAccessDocument(models.Model):
    _name = "approval.test.access.document"
    _description = "Test Record Whose Access Is Asked For Through Approval"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity", "mixin.approval.access"]

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    test_category_id = fields.Many2one(comodel_name="approval.category")
    viewer_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="approval_test_access_document_viewer_rel",
        column1="document_id",
        column2="partner_id",
    )
    editor_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="approval_test_access_document_editor_rel",
        column1="document_id",
        column2="partner_id",
    )

    def _get_approval_subject_category(self, subject_key: str) -> ApprovalCategory:
        return self.test_category_id

    def _has_access(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> bool:
        if role == "edit":
            return partner in self.editor_partner_ids
        return partner in self.viewer_partner_ids | self.editor_partner_ids

    def _grant_access(
        self, partner: ResPartner, role: str | Literal[False] = False
    ) -> None:
        field = "editor_partner_ids" if role == "edit" else "viewer_partner_ids"
        self.sudo().write({field: [Command.link(partner.id)]})
