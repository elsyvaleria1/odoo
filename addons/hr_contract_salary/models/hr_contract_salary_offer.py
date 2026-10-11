from datetime import datetime, time
from typing import TYPE_CHECKING
from urllib.parse import urlencode as url_encode

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.hr_contract_salary.utils.hr_version import requires_hr_version_context

if TYPE_CHECKING:
    from odoo.addons.hr.models.hr_version import HrVersion

_debug = DebugLog(__name__)


class HrContractSalaryOffer(models.Model):
    _name = "hr.contract.salary.offer"
    _description = "Salary Package Offer"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        contract_id = result.get("employee_contract_id")
        if contract_id:
            contract = self.env["hr.contract"].browse(contract_id)
            result["employee_id"] = contract.employee_id.id
        for field in fields:
            if field.startswith("x_") and "active_id" in self.env.context:
                model = self.env.context.get("active_model")
                if model == "hr.version" and field in self.env[model]:
                    version = self.env[model].browse(self.env.context["active_id"])
                    result[field] = version[field]
                elif (
                    model == "hr.applicant"
                    and field in self.env["hr.version"]
                    and "default_contract_template_id" in self.env.context
                ):
                    version = self.env["hr.version"].browse(
                        self.env.context["default_contract_template_id"]
                    )
                    result[field] = version[field]
        return result

    display_name = fields.Char(
        string="Title",
        compute="_compute_display_name",
        store=True,
        readonly=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        default=lambda self: self.env.company.id,
        store=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    contract_template_id = fields.Many2one(
        comodel_name="hr.version",
        compute="_compute_contract_template_id",
        store=True,
        domain="['|', ('employee_id', '=', False), ('id', '=', employee_version_id)]",
        tracking=True,
    )
    sign_template_id = fields.Many2one(
        comodel_name="sign.template",
        string="PDF Sign Template",
        compute="_compute_sign_template_id",
        store=True,
        readonly=False,
        help="Default document that the applicant will have to sign to accept a contract offer.",
    )
    sign_template_signatories_ids = fields.One2many(
        comodel_name="hr.contract.signatory",
        inverse_name="offer_id",
        compute="_compute_sign_template_signatories_ids",
        store=True,
        readonly=False,
    )
    state = fields.Selection(
        selection=[
            ("open", "In Progress"),
            ("half_signed", "Partially Signed"),
            ("full_signed", "Fully Signed"),
            ("expired", "Expired"),
            ("refused", "Refused"),
            ("cancelled", "Cancelled"),
        ],
        default="open",
        tracking=True,
    )
    refusal_reason = fields.Many2one(
        comodel_name="hr.contract.salary.offer.refusal.reason",
        tracking=True,
    )
    offer_create_date = fields.Date(
        compute="_compute_offer_create_date",
        readonly=True,
    )
    refusal_date = fields.Date()
    sign_request_ids = fields.Many2many(
        comodel_name="sign.request",
        string="Requested Signatures",
    )
    employee_version_id = fields.Many2one(
        comodel_name="hr.version",
        compute="_compute_employee_version_id",
        inverse="_inverse_employee_version_id",
        store=True,
        index="btree_not_null",
        tracking=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        domain=[("version_ids", "!=", False)],
        tracking=True,
    )
    applicant_id = fields.Many2one(
        comodel_name="hr.applicant",
        index=True,
        tracking=True,
    )
    applicant_name = fields.Char(related="applicant_id.partner_name")
    final_yearly_costs = fields.Monetary(
        string="Employer Budget",
        compute="_compute_offer_values_from_template",
        store=True,
        aggregator="avg",
        tracking=True,
    )
    job_title = fields.Char(
        compute="_compute_offer_values_from_template",
        store=True,
        readonly=False,
        tracking=True,
    )
    employee_job_id = fields.Many2one(
        comodel_name="hr.job",
        compute="_compute_offer_values_from_template",
        store=True,
        readonly=False,
        tracking=True,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        compute="_compute_offer_values_from_template",
        store=True,
        readonly=False,
        tracking=True,
    )
    contract_start_date = fields.Date(
        default=fields.Date.context_today,
        tracking=True,
    )
    contract_end_date = fields.Date(tracking=True)
    access_token = fields.Char(
        string="Security Token",
        compute="_compute_access_token",
        help="The token of the link the offer is opened with by whoever does not "
        "sign in to it; the link is an access.link row holding its hash.",
    )
    validity_days_count = fields.Integer(
        compute="_compute_validity_days_count",
        inverse="_inverse_validity_days_count",
        store=True,
        readonly=False,
    )
    offer_end_date = fields.Date(
        string="Offer Expiration",
        copy=False,
        readonly=False,
        tracking=True,
    )
    url = fields.Char(
        string="Link",
        compute="_compute_url",
    )
    is_half_sign_state_required = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_half_sign_state_required",
        compute_sudo=True,
    )

    @requires_hr_version_context()
    def _acquire_version(self) -> HrVersion:
        self.check_singleton()

        if self.employee_id:
            contract_template = self.contract_template_id
            if contract_template:
                _debug.logic(
                    "offer_version",
                    by="contract_template",
                    offer=self,
                    template=contract_template,
                )
                if not contract_template.employee_id:
                    contract_template.write(
                        {
                            "employee_id": self.employee_id,
                            "date_version": fields.Date.today()
                            + relativedelta(months=1),
                            "contract_date_start": False,
                        }
                    )
                return contract_template
            else:
                _debug.logic(
                    "offer_version",
                    by="employee_version",
                    offer=self,
                    version=self.employee_version_id,
                )
                return self.employee_version_id

        employee = (
            self.env["hr.employee"]
            .with_user(SUPERUSER_ID)
            .sudo()
            .create(
                {
                    "name": self.applicant_id.partner_name
                    if self.applicant_id
                    else "Simulation Employee",
                    "private_phone_ids": [Command.set(self.applicant_id.phone_ids.ids)]
                    if self.applicant_id
                    else False,
                    "private_email": self.applicant_id.email_from
                    if self.applicant_id
                    else False,
                    "active": False,
                    "nationality_country_id": self.company_id.country_id.id,
                    "private_country_id": self.company_id.country_id.id,
                    "certificate": False,
                    "company_id": self.company_id.id,
                }
            )
        )
        _debug.lifecycle(
            "simulation_employee_created",
            offer=self,
            employee=employee,
            applicant=self.applicant_id,
        )
        if self.contract_template_id:
            employee.version_id.write(
                self.env["hr.version"]._prepare_vals_from_contract_template(
                    self.contract_template_id
                )
            )
        return employee.current_version_id

    @api.depends(
        "contract_template_id.sign_template_id",
        "contract_template_id.contract_update_template_id",
    )
    def _compute_sign_template_id(self) -> None:
        for offer in self:
            if offer.contract_template_id:
                if offer.employee_id and offer.employee_id.active:
                    offer.sign_template_id = (
                        offer.contract_template_id.contract_update_template_id
                    )
                else:
                    offer.sign_template_id = offer.contract_template_id.sign_template_id

    def _copy_contract_template_signatories(self):
        self.check_singleton()
        if self.employee_id and self.employee_id.active:
            contract_template_signatories_copy = (
                self.contract_template_id.contract_update_signatories_ids.copy()
            )
        else:
            contract_template_signatories_copy = (
                self.contract_template_id.sign_template_signatories_ids.copy()
            )
        contract_template_signatories_copy.contract_template_id = False
        contract_template_signatories_copy.update_contract_template_id = False
        return [Command.clear()] + [Command.set(contract_template_signatories_copy.ids)]

    @api.depends("sign_template_id", "contract_template_id")
    def _compute_sign_template_signatories_ids(self) -> None:
        for offer in self:
            if offer.contract_template_id:
                offer.sign_template_signatories_ids = (
                    offer._copy_contract_template_signatories()
                )
            else:
                offer.sign_template_signatories_ids = self.env[
                    "hr.contract.signatory"
                ].create_empty_signatories(offer.sign_template_id)

    @api.depends("contract_template_id.sign_template_signatories_ids")
    def _compute_is_half_sign_state_required(self) -> None:
        for offer in self:
            offer.is_half_sign_state_required = (
                len(offer.sign_template_signatories_ids) != 1
            )

    @api.depends("access_token")
    def _compute_url(self) -> None:
        base_url = self.env["hr.contract.salary.offer"].get_base_url()
        for offer in self:
            offer.url = (
                base_url
                + f"/salary_package/simulation/offer/{offer._origin.id}"
                + (
                    f"?{url_encode({'token': offer.access_token})}"
                    if offer.access_token
                    else ""
                )
            )

    def _compute_access_token(self) -> None:
        links = (
            self.env["access.link"]
            ._record_links(
                self.filtered("id"),
                Domain("cause", "=", "notification")
                & Domain("audience", "=", "anyone")
                & Domain("role", "=", "comment"),
            )
            .sorted("id", reverse=True)
        )
        shown = links._tokens()
        tokens = {}
        for link in links:
            if link.res_id not in tokens and link.id in shown:
                tokens[link.res_id] = shown[link.id]
        for offer in self:
            offer.access_token = tokens.get(offer.id, False)

    def _get_link_expiry(self) -> datetime | None:
        return (
            datetime.combine(self.offer_end_date, time(23, 59, 59))
            if self.offer_end_date
            else None
        )

    def _issue_offer_links(self) -> None:
        Link = self.env["access.link"]
        for offer in self.filtered(lambda offer: not offer.employee_id.user_id):
            __, token = Link._issue(
                offer,
                partner=offer.applicant_id.partner_id or offer.employee_id.partner_id,
                role="comment",
                cause="notification",
            )
            offer._update_cache({"access_token": token}, validate=False)

    def _offer_token_opens(self, token: str | None) -> bool:
        self.check_singleton()
        try:
            self.env["access.link"]._resolve(
                token, model=self._name, res_id=self.id, role="comment", action=None
            )
        except LinkRefused, LinkLoginRequired:
            return False
        return True

    @api.depends(
        "applicant_id",
        "applicant_id.employee_id.name",
        "applicant_id.partner_id.name",
        "applicant_id.partner_name",
        "employee_id",
    )
    def _compute_display_name(self):
        for offer in self:
            if offer.applicant_id:
                name = (
                    offer.applicant_id.employee_id.name
                    or offer.applicant_id.partner_id.name
                    or offer.applicant_id.partner_name
                )
            else:
                name = offer.employee_id.name
            offer.display_name = (
                self.env._("Offer for %(recipient)s", recipient=name) if name else ""
            )

    @api.depends("create_date")
    def _compute_offer_create_date(self) -> None:
        for offer in self:
            offer.offer_create_date = (
                offer.create_date and offer.create_date.date()
            ) or fields.Date.today()

    @api.depends("offer_create_date", "offer_end_date")
    def _compute_validity_days_count(self) -> None:
        for offer in self:
            offer.validity_days_count = (
                (offer.offer_end_date - offer.offer_create_date).days
                if offer.offer_end_date
                else False
            )

    @api.depends("employee_id", "applicant_id")
    def _compute_company_id(self):
        for offer in self:
            if offer.employee_id:
                offer.company_id = offer.employee_id.company_id
            elif offer.applicant_id:
                offer.company_id = offer.applicant_id.company_id
            else:
                offer.company_id = self.env.company.id

    @api.depends("employee_id")
    def _compute_employee_version_id(self) -> None:
        for offer in self:
            if offer.employee_id:
                versions = offer.employee_id.version_ids.sorted("create_date")

                if len(versions) == 1:
                    offer.employee_version_id = versions[0]
                    continue

                active_versions = versions.filtered_domain(
                    [
                        ("date_start", "<=", offer.offer_create_date),
                        "|",
                        ("date_end", "=", False),
                        ("date_end", ">=", offer.offer_create_date),
                    ]
                )

                if active_versions:
                    offer.employee_version_id = active_versions[0]
                else:
                    offer.employee_version_id = versions[0]

    @api.depends("employee_version_id")
    def _compute_contract_template_id(self) -> None:
        for offer in self:
            if not offer.contract_template_id:
                offer.contract_template_id = offer.employee_version_id

    @api.depends("contract_template_id")
    def _compute_offer_values_from_template(self) -> None:
        for offer in self:
            if offer.contract_template_id:
                offer.final_yearly_costs = offer.contract_template_id.final_yearly_costs
                offer.job_title = offer.contract_template_id.job_id.name
                offer.employee_job_id = offer.contract_template_id.job_id
                offer.department_id = offer.contract_template_id.department_id
                offer.company_id = offer.contract_template_id.company_id
            else:
                offer.company_id = offer.env.company.id

    def _inverse_validity_days_count(self) -> None:
        for offer in self:
            offer.offer_end_date = offer.validity_days_count and (
                offer.offer_create_date + relativedelta(days=offer.validity_days_count)
            )

    def _inverse_employee_version_id(self) -> None:
        for offer in self:
            offer.employee_id = offer.employee_version_id.employee_id

    @api.onchange("employee_job_id")
    def _onchange_employee_job_id(self) -> None:
        self.job_title = self.employee_job_id.name
        if self.employee_job_id.department_id:
            self.department_id = self.employee_job_id.department_id

    def action_view_refuse_wizard(self) -> dict:
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_contract_salary.open_refuse_wizard"
        )
        return {
            **action,
            "context": {
                "dialog_size": "medium",
            },
        }

    def action_refuse_offer(self, message=None, refusal_reason=None) -> None:
        self.applicant_id.unlink_archived_versions()
        if not message:
            message = self.env._(
                "%s manually set the Offer to Refused", self.env.user.name
            )
        _debug.lifecycle("offer_refused", offers=self, reason=refusal_reason)
        self.write(
            {
                "state": "refused",
                "refusal_reason": refusal_reason,
                "refusal_date": fields.Date.today(),
            }
        )
        for offer in self:
            offer.message_post(body=message)

    def action_jump_to_offer(self) -> dict:
        self.check_singleton()
        url = f"/salary_package/simulation/offer/{self.id}"
        if self.access_token:
            url += "?" + url_encode({"token": self.access_token})
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    @api.model_create_multi
    def create(self, vals_list):
        offers = super().create(vals_list)
        offers._issue_offer_links()
        return offers

    def write(self, vals):
        result = super().write(vals)
        if {"applicant_id", "employee_id"} & vals.keys():
            self.env["access.link"].with_privilege(
                "base.privilege_manage_links",
                reason="the offer now goes to someone else",
            )._revoke_record_links(
                self,
                "the offer now goes to someone else",
                Domain("cause", "=", "notification"),
            )
            self._issue_offer_links()
        elif {"offer_end_date", "validity_days_count"} & vals.keys():
            self.env["access.link"]._sync_record_expiries(self)
        return result

    def unlink(self):
        self.applicant_id.unlink_archived_versions()
        return super().unlink()

    def _cron_update_state(self) -> None:
        expired_domain = [
            ("state", "in", ["open", "half_signed"]),
            ("offer_end_date", "<", fields.Date.today()),
        ]
        if _debug.lifecycle.enabled:
            _debug.lifecycle("offers_expired", offers=self.search(expired_domain))
        self.search(expired_domain).write({"state": "expired"})

    def action_send_by_email(self) -> dict:
        self.check_singleton()
        try:
            template_id = self.env.ref("hr_contract_salary.mail_template_send_offer").id
        except ValueError:
            template_id = False
        try:
            template_applicant_id = self.env.ref(
                "hr_contract_salary.mail_template_send_offer_applicant"
            ).id
        except ValueError:
            template_applicant_id = False
        if self.applicant_id:
            default_template_id = template_applicant_id
        else:
            default_template_id = template_id

        ctx = {
            "default_composition_mode": "comment",
            "default_email_layout_xmlid": "mail.mail_notification_light",
            "default_model": "hr.contract.salary.offer",
            "default_res_ids": self.ids,
            "default_template_id": default_template_id,
            "offer_id": self.id,
            "access_token": self.access_token,
            "validity_end": self.offer_end_date,
        }
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.mail.message.send",
            "views": [[False, "form"]],
            "target": "new",
            "context": ctx,
        }

    def action_view_signature_request(self):
        self.check_singleton()
        pending_sign_requests = self.sign_request_ids.filtered(
            lambda r: r.state != "signed"
        )
        if len(pending_sign_requests) == 1:
            return pending_sign_requests.go_to_document()
        return {
            "type": "ir.actions.act_window",
            "name": "Signature Requests",
            "view_mode": "kanban,list",
            "res_model": "sign.request",
            "domain": [("id", "in", pending_sign_requests.ids)],
        }

    def action_edit_offer_signatories(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Edit PDF Template Signatories"),
            "type": "ir.actions.act_window",
            "view_mode": "list",
            "res_model": "hr.contract.signatory",
            "target": "new",
            "domain": [("id", "in", self.sign_template_signatories_ids.ids)],
        }

    def action_view_version(self):
        self.check_singleton()
        version = (
            self.env["hr.version"]
            .with_context(active_test=False)
            .search([("originated_offer_id", "=", self.id)], limit=1)
            or self.employee_version_id
            or self.env["hr.version"]
            .with_context(active_test=False)
            .search([("applicant_id", "=", self.applicant_id.id)], limit=1)
        )
        if self.state == "half_signed":
            action = self.env.ref(
                "hr_contract_salary.action_view_partially_signed_contract_statbutton"
            )._get_action_dict()
        else:
            action = self.env.ref(
                "hr_contract_salary.action_view_contract_statbutton"
            )._get_action_dict()

        action["res_id"] = (
            self.employee_id.id
            or self.applicant_id.employee_id.id
            or version.employee_id.id
        )
        action["context"] = {"version_id": version.id}
        return action

    def _mail_get_partners(self, introspect_fields=False):
        return {
            offer.id: (offer.applicant_id.partner_id + offer.employee_id.partner_id)
            for offer in self
        }

    def _mail_get_primary_email(self):
        return {
            record.id: record.applicant_id.email_from or record.employee_id.work_email
            for record in self
        }

    @api.constrains("applicant_id", "employee_id")
    def _check_applicant_id_or_employee_id(self) -> None:
        for offer in self:
            if not (offer.applicant_id or offer.employee_id):
                raise ValidationError(
                    self.env._(
                        "An offer must be linked to either an applicant or an employee."
                    )
                )
