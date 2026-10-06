from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrEmployeeSendSignRequest(models.TransientModel):
    _name = "wizard.hr.employee.send.sign.request"
    _description = "Sign document in contract"

    def _group_hr_contract_domain(self):
        group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
        return [("all_group_ids", "in", group.ids)] if group else []

    def _get_sign_template_ids(self):
        list_template = self.env["sign.template"].sudo()
        for template in self.env["sign.template"].sudo().search([]):
            distinct_responsible_count = len(
                template.sign_item_ids.mapped("responsible_id")
            )
            if distinct_responsible_count in {2, 1}:
                list_template |= template
        # Enumeration runs as sudo so the template_warning default never
        # crashes, but only templates the caller may actually link on the
        # sign_template_ids m2m (relation ACL checks read) are offered back.
        return list_template.with_env(self.env)._filtered_access("read")

    def _default_get_template_warning(self):
        return not bool(self._get_sign_template_ids()) and self.env._(
            "No documents templates on the database."
        )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        active_model = self.env.context.get("active_model", "")
        if active_model == "hr.version":
            defaults["version_id"] = self.env.context.get("active_id")
        elif active_model == "hr.employee":
            defaults["employee_ids"] = [Command.set(self.env.context.get("active_ids"))]
        if "responsible_id" in fields and not defaults.get("responsible_id"):
            version_id = defaults.get("version_id")
            contract = self.env["hr.version"].browse(version_id) if version_id else None
            defaults["responsible_id"] = (
                contract and contract.hr_responsible_id.id
            ) or self.env.user.id
        return defaults

    version_id = fields.Many2one(
        comodel_name="hr.version",
        string="Contract",
        compute="_compute_contract_id",
        store=True,
        readonly=False,
    )
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Employees",
        compute="_compute_employee_ids",
        store=True,
        readonly=False,
    )
    responsible_id = fields.Many2one(
        comodel_name="res.users",
        domain=_group_hr_contract_domain,
    )
    employee_role_id = fields.Many2one(
        comodel_name="sign.item.role",
        compute="_compute_employee_role_id",
        store=True,
        readonly=False,
        required=True,
        domain="[('id', 'in', sign_template_responsible_ids)]",
        help="Employee's role on the templates to sign. The same role must be present in all the templates",
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
        help="""Select only documents with either 1 or 2 different signatories.
        Documents with 1 signatory require only the employee's signature, while those with 2 signatories require signatures from both the employee and the HR responsible.
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
    mail_to = fields.Selection(
        selection=[
            ("work", "Work"),
            ("private", "Private"),
        ],
        string="Email",
        default="work",
        help="""Email used to send the signature request.
                - Work takes the email defined in "work email"
                - Private takes the email defined in Private Information
                - If the selected email is not set, the request is blocked with a warning.""",
    )
    mail_displayed = fields.Char(compute="_compute_mail_displayed")

    @api.depends("sign_template_responsible_ids")
    def _compute_employee_role_id(self) -> None:
        for wizard in self:
            if wizard.employee_role_id not in wizard.sign_template_responsible_ids:
                wizard.employee_role_id = False
            if len(wizard.sign_template_responsible_ids) == 1:
                wizard.employee_role_id = wizard.sign_template_responsible_ids._origin

    @api.depends("sign_template_ids.sign_item_ids.responsible_id")
    def _compute_responsible_ids(self) -> None:
        for r in self:
            responsible_ids = self.env["sign.item.role"]
            for sign_template_id in r.sign_template_ids:
                if responsible_ids:
                    responsible_ids &= sign_template_id.sign_item_ids.responsible_id
                else:
                    responsible_ids |= sign_template_id.sign_item_ids.responsible_id
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

    @api.depends("version_id")
    def _compute_employee_ids(self) -> None:
        for wizard in self:
            if wizard.version_id:
                wizard.employee_ids |= wizard.version_id.employee_id

    @api.depends("employee_ids")
    def _compute_contract_id(self) -> None:
        for wizard in self:
            if wizard.version_id.employee_id not in wizard.employee_ids:
                wizard.version_id = False

    @api.depends("sign_template_ids")
    def _compute_has_both_template(self) -> None:
        for wizard in self:
            wizard.has_both_template = bool(
                wizard.sign_template_ids.filtered(
                    lambda t: len(t.sign_item_ids.mapped("responsible_id")) == 2
                )
            )

    @api.depends("employee_ids", "mail_to")
    def _compute_mail_displayed(self) -> None:
        for wizard in self:
            if len(wizard.employee_ids) == 1:
                wizard.mail_displayed = (
                    wizard.employee_ids.private_email
                    if wizard.mail_to == "private"
                    else wizard.employee_ids.work_email
                )
            else:
                wizard.mail_displayed = False

    def action_confirm_signature(self):
        self.check_singleton()
        partner_by_employee = {}
        for employee in self.employee_ids:
            email_choice = (
                employee.private_email
                if self.mail_to == "private"
                else employee.work_email
            )
            if email_choice:
                email_used = email_choice
            else:
                message_display = (
                    self.env._("%s does not have a private email set.", employee.name)
                    if self.mail_to == "private"
                    else self.env._("%s does not have a work email set.", employee.name)
                )
                _debug.logic(
                    "signature_refused",
                    reason="employee_without_email",
                    employee=employee,
                    mail_to=self.mail_to,
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "message": message_display,
                        "sticky": False,
                        "type": "danger",
                    },
                }
            partner_by_employee[employee] = (
                employee._partner_get_or_create_from_emails_single([email_used])
            )

        sign_request = self.env["sign.request"]
        if not sign_request.has_access("create"):
            _debug.logic(
                "sign_request_sudo", reason="no_create_access", user=self.env.user
            )
            sign_request = sign_request.sudo()

        sign_values = []
        # The wizard mediates on behalf of callers that may not read the
        # templates themselves (the permission limits sign.template to
        # authored/authorized ones): its own bookkeeping reads run as sudo.
        sign_templates = self.sudo().sign_template_ids
        sign_templates_employee_ids = sign_templates.filtered(
            lambda t: len(t.sign_item_ids.mapped("responsible_id")) == 1
        )
        sign_templates_both_ids = sign_templates - sign_templates_employee_ids
        _debug.pipeline(
            "sign_requests",
            employees=self.employee_ids,
            employee_only_templates=sign_templates_employee_ids,
            countersigned_templates=sign_templates_both_ids,
        )
        for employee in self.employee_ids:
            sign_values.extend(
                (
                    sign_template_id,
                    employee,
                    [
                        {
                            "role_id": self.employee_role_id.id,
                            "partner_id": partner_by_employee[employee].id,
                        }
                    ],
                )
                for sign_template_id in sign_templates_employee_ids
            )
            for sign_template_id in sign_templates_both_ids:
                second_role = (
                    sign_template_id.sign_item_ids.responsible_id
                    - self.employee_role_id
                )
                sign_values.append(
                    (
                        sign_template_id,
                        employee,
                        [
                            {
                                "role_id": self.employee_role_id.id,
                                "partner_id": partner_by_employee[employee].id,
                            },
                            {
                                "role_id": second_role.id,
                                "partner_id": self.responsible_id.partner_id.id,
                            },
                        ],
                    )
                )

        sign_requests = sign_request.create(
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
                    "reference": sign_request_values[0].name,
                    "subject": self.subject,
                    "message": self.message,
                    "attachment_ids": [
                        Command.link(attachment.copy().id)
                        for attachment in self.attachment_ids
                    ],  # Attachments may not be bound to multiple sign requests
                }
                for sign_request_values in sign_values
            ]
        )
        sign_requests.message_subscribe(partner_ids=self.cc_partner_ids.ids)

        if not self.env["sign.request"].has_access("write"):
            sign_requests = sign_requests.sudo()

        for sign_request, sign_value in zip(sign_requests, sign_values, strict=True):
            sign_request.action_toggle_user_favorite()
            employee = sign_value[1]
            if self.version_id.employee_id == employee:
                self.version_id.sudo().sign_request_ids += sign_request
            else:
                # sign_request_ids carries groups="hr.group_hr_user"; the
                # field descriptor rejects even the read behind += without it.
                employee.sudo().sign_request_ids += sign_request

        for employee in self.employee_ids:
            if self.responsible_id and sign_templates_both_ids:
                signatories_text = self.env._(
                    "%(employee)s and %(responsible)s are the signatories.",
                    employee=employee.display_name,
                    responsible=self.responsible_id.display_name,
                )
            else:
                signatories_text = self.env._(
                    "Only %s has to sign.", employee.display_name
                )
            employee.message_post(
                body=(
                    self.env._(
                        "%(user_name)s requested a new signature on the following documents:"
                    )
                    + Markup("<br/><ul>%(documents)s</ul>%(signatories_text)s")
                )
                % {
                    "user_name": self.env.user.display_name,
                    "documents": Markup("\n").join(
                        Markup("<li>%s</li>") % name
                        for name in sign_templates.mapped("name")
                    ),
                    "signatories_text": signatories_text,
                }
            )

        if len(sign_requests) == 1 and (
            (self.env.user.id in self.employee_ids.user_id.ids)
            or (self.env.user.id == self.responsible_id.id and sign_templates_both_ids)
        ):
            return sign_requests.go_to_document()
        return None
