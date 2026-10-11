from odoo import api, fields, models


class WizardDocumentDocumentShareLine(models.TransientModel):

    _name = "wizard.document.document.share.line"
    _description = "Documents share access"

    documents_sharing_id = fields.Many2one(
        comodel_name="wizard.document.document.share",
        string="Documents share",
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        ondelete="cascade",
    )

    role = fields.Selection(
        selection="_selection_access_roles",
        required=True,
    )
    is_inherited = fields.Boolean(
        string="From a folder above",
        help="The role reaches this document from a folder above it. Lowering it "
        "here stops what the folders above grant.",
    )
    expiration_date = fields.Datetime(string="Expiration")
    original_expiration_date = fields.Datetime(string="Original Expiration")
    is_deleted = fields.Boolean()

    partner_is_me = fields.Boolean(
        string="Is me",
        compute="_compute_partner_is_me",
    )

    has_user = fields.Boolean(compute="_compute_has_user")
    has_warning_no_access = fields.Boolean(compute="_compute_has_warning_no_access")
    is_on_single_document = fields.Boolean(related="documents_sharing_id.is_single")
    is_readonly = fields.Boolean(related="documents_sharing_id.is_readonly")

    @api.model
    def _selection_access_roles(self) -> list:
        return self.env["wizard.document.document.share"]._selection_member_roles()

    @api.depends_context("uid")
    @api.depends("partner_id")
    def _compute_partner_is_me(self) -> None:
        me = self.env.user.partner_id
        for record in self:
            record.partner_is_me = record.partner_id == me

    @api.depends("partner_id.user_ids")
    def _compute_has_user(self) -> None:
        for record in self:
            record.has_user = bool(record.partner_id.user_ids)

    @api.depends(
        "documents_sharing_id.access_via_link",
        "documents_sharing_id.invite_partner_ids",
        "partner_id.user_ids",
        "is_deleted",
    )
    def _compute_has_warning_no_access(self) -> None:
        for record in self:
            record.has_warning_no_access = (
                not record.documents_sharing_id.invite_partner_ids
                and record.documents_sharing_id.access_via_link.endswith("none")
                and not record.has_user
                and not record.is_deleted
            )
