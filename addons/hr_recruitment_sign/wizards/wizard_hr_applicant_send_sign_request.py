from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrApplicantSendSignRequest(models.TransientModel):
    _name = "wizard.hr.applicant.send.sign.request"
    _description = "Sign document in recruitment"

    def _group_hr_contract_domain(self):
        group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
        return [("all_group_ids", "in", group.ids)] if group else []

    def _get_sign_template_ids(self):
        return (
            self.env["sign.template"]
            .search([])
            .filtered(lambda t: 1 <= t.responsible_count <= 2)
        )

    def _default_get_template_warning(self):
        return not bool(self._get_sign_template_ids()) and self.env._(
            "No appropriate template could be found, please make sure you configured them properly."
        )

    applicant_ids = fields.Many2many(
        comodel_name="hr.applicant",
        string="Applicants",
        default=lambda self: self.env.context.get("active_ids", []),
    )
    applicant_role_id = fields.Many2one(
        comodel_name="sign.item.role",
        compute="_compute_applicant_role_id",
        store=True,
        readonly=False,
        required=True,
        domain="[('id', 'in', sign_template_responsible_ids)]",
        help="Applicant's role on the templates to sign. The same role must be present in all the templates",
    )
    responsible_id = fields.Many2one(
        comodel_name="res.users",
        domain=_group_hr_contract_domain,
    )
    sign_template_responsible_ids = fields.Many2many(
        comodel_name="sign.item.role",
        compute="_compute_responsible_ids",
    )
    possible_template_ids = fields.Many2many(
        comodel_name="sign.template",
        compute="_compute_possible_template_ids",
    )
    sign_template_ids = fields.Many2many(
        comodel_name="sign.template",
        string="Documents to sign",
        required=True,
        domain="[('id', 'in', possible_template_ids)]",
        help="""Documents to sign. Only documents with 1 or 2 different responsible are selectable.
        Documents with 1 responsible will only have to be signed by the applicant while documents with 2 different responsible will have to be signed by both the applicant and the responsible.
        """,
    )
    has_both_template = fields.Boolean(compute="_compute_has_both_template")
    template_warning = fields.Char(
        default=lambda self: self._default_get_template_warning(),
        store=False,
    )

    subject = fields.Char(
        default="Signature Request",
        required=True,
    )
    message = fields.Html()
    cc_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Copy to",
    )
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        bypass_search_access=True,
    )

    @api.depends("sign_template_responsible_ids")
    def _compute_applicant_role_id(self) -> None:
        for wizard in self:
            if wizard.applicant_role_id not in wizard.sign_template_responsible_ids:
                _debug.logic(
                    "recruitment_sign_role_cleared",
                    reason="role_not_in_template_responsibles",
                    wizard=wizard,
                    responsibles=wizard.sign_template_responsible_ids,
                )
                wizard.applicant_role_id = False
            if len(wizard.sign_template_responsible_ids) == 1:
                _debug.logic(
                    "recruitment_sign_role_forced",
                    reason="single_responsible",
                    wizard=wizard,
                    role=wizard.sign_template_responsible_ids,
                )
                wizard.applicant_role_id = wizard.sign_template_responsible_ids._origin

    @api.depends("sign_template_ids.sign_item_ids.responsible_id")
    def _compute_responsible_ids(self) -> None:
        for r in self:
            responsible_ids = self.env["sign.item.role"]
            for sign_template_id in r.sign_template_ids:
                if responsible_ids:
                    responsible_ids &= sign_template_id.sign_item_ids.responsible_id
                else:
                    responsible_ids |= sign_template_id.sign_item_ids.responsible_id
            _debug.logic(
                "recruitment_sign_responsibles_intersected",
                wizard=r,
                templates=r.sign_template_ids,
                responsibles=responsible_ids,
            )
            r.sign_template_responsible_ids = responsible_ids

    @api.depends("sign_template_ids")
    def _compute_possible_template_ids(self) -> None:
        possible_sign_templates = self._get_sign_template_ids()
        for wizard in self:
            if not wizard.sign_template_ids:
                wizard.possible_template_ids = possible_sign_templates
            else:
                roles = wizard.sign_template_ids.sign_item_ids.responsible_id
                wizard.possible_template_ids = possible_sign_templates.filtered_domain(
                    [("sign_item_ids.responsible_id", "in", roles.ids)]
                )

    @api.depends("sign_template_ids")
    def _compute_has_both_template(self) -> None:
        for wizard in self:
            wizard.has_both_template = bool(
                wizard.sign_template_ids.filtered(
                    lambda t: len(t.sign_item_ids.mapped("responsible_id")) == 2
                )
            )

    def action_confirm_signature(self):
        self.check_singleton()

        sign_request = self.env["sign.request"]
        if not self.browse().has_access("create"):
            sign_request = sign_request.sudo()

        sign_values = []
        sign_templates_applicant_ids = self.sign_template_ids.filtered(
            lambda t: len(t.sign_item_ids.mapped("responsible_id")) == 1
        )
        sign_templates_both_ids = self.sign_template_ids - sign_templates_applicant_ids
        _debug.pipeline(
            "recruitment_sign_confirm_start",
            wizard=self,
            applicants=self.applicant_ids,
            applicant_only_templates=sign_templates_applicant_ids,
            two_signer_templates=sign_templates_both_ids,
            sudo_create=not self.browse().has_access("create"),
        )

        for applicant in self.applicant_ids:
            for sign_template_id in sign_templates_applicant_ids:
                sign_values.append(
                    (
                        sign_template_id,
                        applicant,
                        [
                            {
                                "role_id": self.applicant_role_id.id,
                                "partner_id": applicant.partner_id.id,
                            }
                        ],
                    )
                )
            for sign_template_id in sign_templates_both_ids:
                second_role = (
                    sign_template_id.sign_item_ids.responsible_id
                    - self.applicant_role_id
                )
                sign_values.append(
                    (
                        sign_template_id,
                        applicant,
                        [
                            {
                                "role_id": self.applicant_role_id.id,
                                "partner_id": applicant.partner_id.id,
                            },
                            {
                                "role_id": second_role.id,
                                "partner_id": self.responsible_id.partner_id.id,
                            },
                        ],
                    )
                )

        sign_requests = (
            self.sudo()
            .env["sign.request"]
            .create(
                [
                    {
                        "template_id": sign_request_values[0].id,
                        "request_item_ids": [
                            Command.create(
                                {
                                    "partner_id": signer["partner_id"],
                                    "role_id": signer["role_id"],
                                }
                            )
                            for signer in sign_request_values[2]
                        ],
                        "reference": self.env._(
                            "Signature Request - %s", sign_request_values[0].name
                        ),
                        "subject": self.subject,
                        "message": self.message,
                        "attachment_ids": [
                            Command.link(attachment.copy().id)
                            for attachment in self.attachment_ids
                        ],
                    }
                    for sign_request_values in sign_values
                ]
            )
        )
        _debug.pipeline(
            "recruitment_sign_requests_created",
            wizard=self,
            requested=len(sign_values),
            created=sign_requests,
            signers_intended=sum(len(values[2]) for values in sign_values),
            request_items=len(sign_requests.request_item_ids),
        )
        sign_requests.message_subscribe(partner_ids=self.cc_partner_ids.ids)

        if not self.browse().has_access("write"):
            sign_requests = sign_requests.sudo()

        for sign_request in sign_requests:
            sign_request.action_toggle_user_favorite()

        for applicant in self.applicant_ids:
            if self.responsible_id and sign_templates_both_ids:
                signatories_text = self.env._(
                    "%(partner)s and %(responsible)s are the signatories.",
                    partner=applicant.display_name,
                    responsible=self.responsible_id.display_name,
                )
            else:
                signatories_text = self.env._(
                    "Only %s has to sign.", applicant.display_name
                )
            _debug.logic(
                "recruitment_sign_signatories_announced",
                applicant=applicant,
                responsible=self.responsible_id,
                two_signer_templates=sign_templates_both_ids,
            )
            record_to_post = applicant
            record_to_post.message_post_with_source(
                "hr_recruitment_sign.message_signature_request",
                render_values={
                    "user_name": self.env.user.display_name,
                    "document_names": self.sign_template_ids.mapped("name"),
                    "signatories_text": signatories_text,
                },
                subtype_xmlid="mail.mt_comment",
            )

        _debug.lifecycle(
            "recruitment_sign_confirm_done",
            wizard=self,
            requests=sign_requests,
            opening_document=len(sign_requests) == 1
            and self.env.user.id == self.responsible_id.id,
        )
        if len(sign_requests) == 1 and self.env.user.id == self.responsible_id.id:
            return sign_requests.go_to_document()
        return None
