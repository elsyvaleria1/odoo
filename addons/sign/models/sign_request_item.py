import secrets
from datetime import datetime, time, timedelta
from hashlib import sha256
from urllib.parse import urlencode as url_encode

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.web import urljoin as url_join
from odoo.tools import (
    consteq,
    email_normalize,
    formataddr,
    frozendict,
    get_lang,
    groupby,
    html2plaintext,
    is_html_empty,
)
from odoo.tools.misc import hmac, register_signed_scope

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.portal.models.mixin_portal import _presented_link_tokens
from odoo.addons.sign.utils.mail_link import get_mail_link
from odoo.addons.sms.tools.sms_api import SmsApi

SMS_CODE_LIFETIME = timedelta(minutes=10)
SMS_CODE_MAX_FAILURES = 5
# a signer may have 3 codes sent at once, then one every 10 minutes
SMS_SEND_BURST = 3
SMS_SEND_REFILL_SECONDS = 1800
# a signer may have a new signing link mailed 3 times an hour; a shared document
# takes 10 refusals an hour
RESEND_LINK_BURST = 3
RESEND_LINK_REFILL_SECONDS = 3600
SHARED_REFUSAL_BURST = 10
SHARED_REFUSAL_REFILL_SECONDS = 3600

SMS_CODE_SCOPE = register_signed_scope(
    "sign_sms_code",
    purpose="the SMS code a signer must type back, kept only as this hash",
    lifetime=f"dated: {SMS_CODE_LIFETIME.seconds // 60} minutes after it is sent, "
    f"voided after {SMS_CODE_MAX_FAILURES} wrong attempts",
)

EXPIRY_SCOPE = register_signed_scope(
    "sign_expiration",
    purpose="the expiry date a signing link carries, so its holder cannot extend it",
    lifetime="dated: sign.link_expiry_duration hours, carried in the link",
)


class SignRequestItem(models.Model):
    _name = "sign.request.item"
    _description = "Signature Request Item"
    _inherit = ["mixin.portal"]
    _rec_name = "partner_id"
    _access_anchors = frozendict(
        {
            "owner": "sign_request_id.create_uid",
            "partner": "sign_request_id.request_item_ids.partner_id",
        }
    )

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items._issue_signer_links()
        return items

    def _signer_link_end(self):
        validity = self.sign_request_id.validity
        return validity and datetime.combine(validity, time(23, 59, 59))

    def _issue_signer_links(self) -> None:
        """A comment link per signer, in the signer's name (none for a shared
        request's anonymous signer), until the request's validity or for as long
        as a notification's link lives (decision B1): opening, signing, refusing
        the document."""
        signers = self
        tokens = self.env["access.link"]._issue_each(
            signers,
            partner_field="partner_id",
            role="comment",
            cause="notification",
            date_to=lambda item: item._signer_link_end(),
        )
        for item in signers:
            item._update_cache({"access_token": tokens[item.id]}, validate=False)

    def _renew_signer_links(self, reason) -> None:
        """The links sent before stop opening; the signers get new ones."""
        self.env["access.link"].with_privilege(
            "base.privilege_manage_links", reason=reason
        )._revoke_record_links(self, reason)
        self._issue_signer_links()

    @api.model
    def _from_signer_token(self, token, request_id=None):
        """The signer whose live link ``token`` is, in sudo, or an empty
        recordset; with ``request_id``, only a signer of that request."""
        try:
            item = (
                self.env["access.link"]
                ._resolve(token, model=self._name, role="comment", action=None)
                .record
            )
        except LinkRefused, LinkLoginRequired:
            return self.browse()
        if request_id is not None and item.sign_request_id.id != int(request_id):
            return self.browse()
        if request:
            _presented_link_tokens()[item._name, item.id] = token
            item.invalidate_recordset(["access_token"])
        return item

    def _get_mail_link(self, email, subject):
        return get_mail_link(email, subject)

    # this display_name (with sudo) is used for many2many_tags especially the partner_id is private
    display_name = fields.Char(compute_sudo=True)

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Signer",
        ondelete="restrict",
    )
    sign_request_id = fields.Many2one(
        comodel_name="sign.request",
        string="Signature Request",
        index=True,
        copy=False,
        required=True,
        ondelete="cascade",
    )
    sign_item_value_ids = fields.One2many(
        comodel_name="sign.request.item.value",
        inverse_name="sign_request_item_id",
        string="Value",
    )
    reference = fields.Char(
        related="sign_request_id.reference",
        string="Document Name",
    )
    mail_sent_order = fields.Integer(default=1)
    communication_company_id = fields.Many2one(
        related="sign_request_id.communication_company_id"
    )

    access_token = fields.Char(
        classification="secret.credential",
        groups="base.group_system",
    )
    access_via_link = fields.Boolean(
        string="Accessed Through Token",
        copy=False,
    )
    role_id = fields.Many2one(
        comodel_name="sign.item.role",
        readonly=True,
        required=True,
    )
    sms_number = fields.Char(
        compute="_compute_sms_number",
        store=True,
        copy=False,
        readonly=False,
    )
    sms_code_hash = fields.Char(
        copy=False,
        readonly=True,
        classification="secret.credential",
        groups="base.group_system",
        help="Keyed hash of the SMS code pending verification; the code itself is "
        "never stored.",
    )
    sms_code_expires_at = fields.Datetime(
        copy=False,
        readonly=True,
    )
    sms_code_failures = fields.Integer(
        copy=False,
        readonly=True,
    )
    sms_verified_date = fields.Datetime(
        string="Phone Verified On",
        copy=False,
        readonly=True,
        help="When the signer proved control of the phone number with an SMS code.",
    )
    sms_verified_number = fields.Char(
        string="Verified Phone",
        copy=False,
        readonly=True,
        help="The number the verified SMS code was sent to.",
    )
    signed_without_extra_auth = fields.Boolean(
        string="Signed Without Extra Authentication",
        default=False,
        copy=False,
        readonly=True,
    )

    signature = fields.Binary(
        attachment=True,
        copy=False,
    )
    frame_hash = fields.Char(
        size=256,
        compute="_compute_frame_hash",
    )
    signing_date = fields.Date(
        string="Signed on",
        copy=False,
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ("sent", "To Sign"),
            ("completed", "Signed"),
            ("canceled", "Cancelled"),
        ],
        default="sent",
        index=True,
        copy=False,
        readonly=True,
    )
    color = fields.Integer(compute="_compute_color")

    signer_email = fields.Char(
        string="Email",
        compute="_compute_email",
        store=True,
    )
    is_mail_sent = fields.Boolean(
        copy=False,
        readonly=True,
        help="The signature mail has been sent.",
    )
    change_authorized = fields.Boolean(related="role_id.change_authorized")

    latitude = fields.Float(
        digits=(10, 7),
        copy=False,
    )
    longitude = fields.Float(
        digits=(10, 7),
        copy=False,
    )

    @api.constrains("signer_email")
    def _check_signer_email_validity(self) -> None:
        if any(sri.partner_id and not sri.signer_email for sri in self):
            raise ValidationError(
                self.env._("All signers must have valid email addresses")
            )

    @api.constrains("sign_request_id", "partner_id", "role_id")
    def _check_signers_validity(self) -> None:
        # this check allows one signer to be False, which is used to "share" a sign template
        self.sign_request_id._check_signers_roles_validity()
        self.sign_request_id._check_signers_partners_validity()

    @api.depends("signer_email")
    def _compute_frame_hash(self) -> None:
        db_uuid = self.env.registry.settings.get(self.env, "database.uuid", False)
        for sri in self:
            if sri.partner_id:
                sri.frame_hash = sha256(
                    (sri.signer_email + db_uuid).encode()
                ).hexdigest()
            else:
                sri.frame_hash = ""

    @api.depends("partner_id.name")
    def _compute_display_name(self):
        for sri in self:
            sri.display_name = (
                sri.partner_id.display_name
                if sri.partner_id
                else self.env._("Public User")
            )

    def write(self, vals):
        if "state" in vals and not (
            self.env.su
            or self.env.user.has_group("sign.group_sign_manager")
            or all(sri.sign_request_id.create_uid == self.env.user for sri in self)
        ):
            raise UserError(
                self.env._("Only the request's owner can change a signer's status.")
            )
        if vals.get("partner_id") is False:
            raise UserError(self.env._("You need to define a signatory"))
        request_items_reassigned = self.env["sign.request.item"]
        if vals.get("partner_id"):
            request_items_reassigned |= self.filtered(
                lambda sri: sri.partner_id and sri.partner_id.id != vals["partner_id"]
            )
            if any(
                sri.state != "sent"
                or sri.sign_request_id.state != "sent"
                or (sri.partner_id and not sri.role_id.change_authorized)
                or sri.sign_request_id.state == "shared"
                for sri in request_items_reassigned
            ):
                raise UserError(self.env._("You cannot reassign this signatory"))
            new_sign_partner = self.env["res.partner"].browse(vals.get("partner_id"))
            for request_item in request_items_reassigned:
                sign_request = request_item.sign_request_id
                old_sign_user = request_item.partner_id.user_ids[:1]
                # remove old activities for internal users if they are no longer one of the unsigned signers of their sign requests
                if (
                    old_sign_user
                    and old_sign_user.has_group("sign.group_sign_user")
                    and not (
                        sign_request.request_item_ids - request_items_reassigned
                    ).filtered_domain(
                        [
                            ("partner_id", "=", request_item.partner_id.id),
                            ("state", "=", "sent"),
                        ]
                    )
                ):
                    sign_request.activity_unlink(
                        ["sign.mail_activity_data_signature_request"],
                        user_id=old_sign_user.id,
                    )
                # create logs
                sign_request.message_post(
                    body=self.env._(
                        "The contact of %(role)s has been changed from %(old_partner)s to %(new_partner)s.",
                        role=request_item.role_id.name,
                        old_partner=request_item.partner_id.name,
                        new_partner=new_sign_partner.name,
                    )
                )

            # add new followers
            request_items_reassigned.sign_request_id.message_subscribe(
                partner_ids=[vals.get("partner_id")]
            )
            # add new activities for internal users
            new_sign_user = self.env["res.users"].search(
                [
                    ("partner_id", "=", vals.get("partner_id")),
                    ("all_group_ids", "in", [self.env.ref("sign.group_sign_user").id]),
                ],
                limit=1,
            )
            if new_sign_user:
                activity_ids = set(
                    request_items_reassigned.sign_request_id.activity_search(
                        ["sign.mail_activity_data_signature_request"],
                        user_id=new_sign_user.id,
                    ).mapped("res_id")
                )
                request_items_reassigned.sign_request_id.filtered(
                    lambda sr: sr.id not in activity_ids
                )._schedule_activity(new_sign_user)

        res = super().write(vals)

        # change access token
        reassigned_sent = request_items_reassigned.filtered(
            lambda sri: sri.is_mail_sent
        )
        reassigned_sent.sudo()._renew_signer_links("the signer was replaced")
        reassigned_sent.is_mail_sent = False
        return res

    def _cancel(self) -> None:
        """Cancel a SignRequestItem. It can only be used in the SignRequest.cancel or SignRequest._refuse"""
        for request_item in self:
            request_item.write(
                {
                    "state": "canceled"
                    if request_item.state == "sent"
                    else request_item.state,
                    "signing_date": fields.Date.context_today(self)
                    if request_item.state == "sent"
                    else request_item.signing_date,
                    "is_mail_sent": False,
                }
            )
            self.env["access.link"].with_privilege(
                "base.privilege_manage_links", reason="cancel a signature request"
            )._revoke_record_links(request_item, "the signature request was cancelled")
            request_item.invalidate_recordset(["access_token"])

    def _refuse(self, request_state, refusal_reason, refusal_name="", refusal_email=""):
        """Refuse a sign request item with 'sent' or 'shared' states."""
        self.check_singleton()
        if not self.env.su:
            raise UserError(self.env._("This function can only be called with sudo."))

        # The refuser is the signer's user, else whoever is logged in; a
        # public visitor of a shared request identifies by name and email.
        refuse_user = self.partner_id.user_ids[:1]
        if not refuse_user and not self.env.user._is_public():
            refuse_user = self.env.user
        refuser = self.partner_id or refuse_user.partner_id
        if refuser:
            message_post = self.env._(
                "The signature has been refused by %(partner)s (%(role)s), refusal reason:",
                partner=refuser.name,
                role=self.role_id.name,
            )
        else:
            message_post = self.env._(
                "The signature has been refused by %(name)s with email (%(email)s), refusal reason:",
                name=refusal_name,
                email=refusal_email,
            )
        refusal_reason = (
            self.env._("No specified reason")
            if not refusal_reason or refusal_reason.isspace()
            else refusal_reason
        )
        message_post = Markup('{}<p style="white-space: pre">{}</p>').format(
            message_post, refusal_reason
        )

        if self.state == "sent" and request_state == "sent":
            self._refuse_sent(refuse_user, message_post, refusal_reason)
        elif self.state == "sent" and request_state == "shared":
            self._refuse_shared(refuse_user, message_post, refusal_name, refusal_email)
        else:
            raise UserError(self.env._("This sign request item cannot be refused"))

    def _refuse_sent(self, refuse_user, message_post, refusal_reason) -> None:
        """Refuse requests that were sent directly to the signers ('sent' state).
        The cancelling flow happens directly in the refused sign request."""
        self.env["sign.log"].create(
            {"sign_request_item_id": self.id, "action": "refuse"}
        )
        self.write(
            {"signing_date": fields.Date.context_today(self), "state": "canceled"}
        )

        # Mark the signature activity as done for the refuser.
        if refuse_user and refuse_user.has_group("sign.group_sign_user"):
            self.sign_request_id.activity_feedback(
                ["sign.mail_activity_data_signature_request"], user_id=refuse_user.id
            )

        self.sign_request_id.message_post(body=message_post)
        self.sign_request_id._refuse(self.partner_id, refusal_reason)

    def _refuse_shared(
        self, refuse_user, message_post, refusal_name="", refusal_email=""
    ) -> None:
        """Record a refusal of a request shared by link ('shared' state), which
        stays open to everyone else. A logged-in refuser is recorded as their
        contact; a visitor without an account declares a name and an email,
        recorded as declared and matched to no contact."""
        if not refuse_user and not (refusal_name and refusal_email):
            raise UserError(
                self.env._("The public user must identify itself for the refusal.")
            )
        # every refusal notifies the owner: a shared link must not flood them
        if not self._consume_send_budget(
            "shared_refusal", SHARED_REFUSAL_BURST, SHARED_REFUSAL_REFILL_SECONDS
        ):
            raise UserError(
                self.env._(
                    "Too many refusals were sent for this document; try again later."
                )
            )
        self.env["sign.log"].create(
            {"sign_request_item_id": self.id, "action": "refuse"}
            | (
                {"partner_id": refuse_user.partner_id.id}
                if refuse_user
                else {"declared_name": refusal_name, "declared_email": refusal_email}
            )
        )
        self.sign_request_id.message_post(body=message_post)

    def _get_url_parameters(self, signer, expiry_link_timestamp):
        return url_encode(
            {
                "timestamp": expiry_link_timestamp,
                "exp": signer._generate_expiry_signature(
                    signer.id, expiry_link_timestamp
                ),
            }
        )

    def _get_access_token(self, signer):
        return signer.sudo().access_token

    def _get_sign_and_cancel_links(self, signer) -> tuple:
        expiry_link_timestamp = signer._generate_expiry_link_timestamp()
        url_params = self._get_url_parameters(signer, expiry_link_timestamp)
        partial_url = (
            "sign/document/mail/%(request_id)s/%(access_token)s?%(url_params)s"
            % {
                "request_id": signer.sign_request_id.id,
                "access_token": self._get_access_token(signer),
                "url_params": url_params,
            }
        )
        link_sign = url_join(signer.get_base_url(), partial_url)
        company = signer.communication_company_id
        if "website_id" in company and company.website_id.domain:
            link_sign = url_join(company.website_id.domain, partial_url)
        link_cancel = link_sign + "&refuseDocument=1"

        return link_sign, link_cancel

    def _send_signature_access_message(self):
        for signer in self:
            signer_email_normalized = email_normalize(signer.signer_email or "")
            signer_lang = get_lang(self.env, lang_code=signer.partner_id.lang).code
            # We hide the validity information if it is the default (6 month from the create_date)
            has_default_validity = (
                signer.sign_request_id.validity
                and signer.sign_request_id.validity - relativedelta(months=6)
                == signer.sign_request_id.create_date.date()
            )
            link_sign, link_cancel = self._get_sign_and_cancel_links(signer)
            body = self.env["ir.qweb"]._render(
                "sign.sign_template_mail_request",
                {
                    "record": signer,
                    "link": link_sign,
                    "link_cancel": link_cancel,
                    "subject": signer.sign_request_id.subject,
                    "body": signer.sign_request_id.message
                    if not is_html_empty(signer.sign_request_id.message)
                    else False,
                    "use_sign_terms": self.env.registry.settings.get(
                        self.env, "sign.use_sign_terms", False
                    ),
                    "user_signature": signer.create_uid.signature,
                    "show_validity": signer.sign_request_id.validity
                    and not has_default_validity,
                },
                lang=signer_lang,
                minimal_qcontext=True,
            )

            attachment_ids = signer.sign_request_id.attachment_ids.ids
            self.env["sign.request"].with_context(
                lang=signer.partner_id.lang or self.env.lang
            )._message_send_mail(
                body,
                record_name=signer.sign_request_id.reference,
                notif_values={
                    "model_description": self.env._("Signature"),
                    "company": signer.communication_company_id
                    or signer.sign_request_id.create_uid.company_id,
                    "partner": signer.partner_id,
                },
                mail_values={
                    "author_id": signer.create_uid.partner_id.id,
                    "email_from": signer.create_uid.email_formatted,
                    "email_to": formataddr(
                        (signer.partner_id.name, signer_email_normalized)
                    ),
                    "subject": signer.sign_request_id.subject,
                    "attachment_ids": attachment_ids,
                },
                force_send=self.env.context.get(
                    "force_send", True
                ),  # only force_send if not from cron
            )
            signer.is_mail_sent = True

    def sign(self, signature, **kwargs):
        """Sign sign request items at once.
        :param signature: dictionary containing signature values and corresponding ids
        """
        return self._sign(signature, **kwargs)

    def _sign(self, signature, **kwargs):
        """Stores the sign request item values.
        :param signature: dictionary containing signature values and corresponding ids / signature image
        :param validation_required: boolean (via kwargs) indicating whether the sign request item requires a further validation process
        """
        self.check_singleton()
        if not self.env.su:
            raise UserError(self.env._("This function can only be called with sudo."))
        if self.state != "sent" or self.sign_request_id.state != "sent":
            raise UserError(self.env._("This sign request item cannot be signed"))
        if (
            self.sign_request_id.validity
            and self.sign_request_id.validity < fields.Date.today()
        ):
            raise UserError(self.env._("This sign request is not valid anymore"))

        required_ids = set(
            self.sign_request_id.template_id.sign_item_ids.filtered(
                lambda r: r.responsible_id.id == self.role_id.id and r.required
            ).ids
        )
        signature_ids = (
            {int(k) for k in signature} if isinstance(signature, dict) else set()
        )
        if not (required_ids <= signature_ids):  # Security check
            raise UserError(self.env._("Some required items are not filled"))

        self._update_signature_values(signature, **kwargs)
        if not kwargs.get("validation_required"):
            self._post_fill_request_item()

    def _send_no_credits_email(self) -> None:
        partner_lang = get_lang(
            self.env, lang_code=self.create_uid.partner_id.lang
        ).code
        body = self.env["ir.qweb"]._render(
            "sign.sign_template_mail_not_enough_credits",
            {
                "record": self,
                "recipient_name": self.create_uid.name,
                "subject": "%s signed" % self.reference,
                "signer": self.partner_id,
                "auth_method": dict(
                    self.role_id._fields["auth_method"]._description_selection(self.env)
                )[self.role_id.auth_method],
            },
            lang=partner_lang,
            minimal_qcontext=True,
        )

        self.env["sign.request"].with_context(
            lang=self.create_uid.lang or self.env.lang
        )._message_send_mail(
            body,
            record_name=self.reference,
            notif_values={
                "model_description": "signature",
                "company": self.communication_company_id or self.create_uid.company_id,
                "partner": self.create_uid.partner_id,
            },
            mail_values={
                "author_id": self.create_uid.partner_id.id,
                "email_from": self.create_uid.email_formatted,
                "email_to": self.create_uid.email_formatted,
                "subject": self.env._(
                    "%s: missing credits for extra-authentication", self.reference
                ),
            },
            force_send=True,
        )

    def _post_fill_request_item(self):
        self.env["sign.log"].create({"sign_request_item_id": self.id, "action": "sign"})
        self.write(
            {"signing_date": fields.Date.context_today(self), "state": "completed"}
        )
        if self.signed_without_extra_auth:
            self._send_no_credits_email()

        # mark signature as done in next activity
        if not self.sign_request_id.request_item_ids.filtered(
            lambda sri: sri.partner_id == self.partner_id and sri.state == "sent"
        ):
            sign_user = self.partner_id.user_ids[:1]
            if sign_user and sign_user.has_group("sign.group_sign_user"):
                self.sign_request_id.activity_feedback(
                    ["sign.mail_activity_data_signature_request"], user_id=sign_user.id
                )
        sign_request = self.sign_request_id
        if all(sri.state == "completed" for sri in sign_request.request_item_ids):
            sign_request._sign()
        elif all(
            sri.state == "completed"
            for sri in sign_request.request_item_ids.filtered(
                lambda sri: sri.mail_sent_order == self.mail_sent_order
            )
        ):
            sign_request.send_signature_accesses()

    def _update_signature_values(self, signature, **kwargs) -> None:
        """Stores the sign request item values.
        :param signature: dictionary containing signature values and corresponding ids / signature image
        """
        self.check_singleton()
        if not self.env.su:
            raise UserError(self.env._("This function can only be called with sudo."))
        if self.state != "sent" or self.sign_request_id.state != "sent":
            raise UserError(self.env._("This sign request item cannot be filled"))

        authorised_ids = set(
            self.sign_request_id.template_id.sign_item_ids.filtered(
                lambda r: r.responsible_id.id == self.role_id.id
            ).ids
        )
        signature_ids = (
            {int(k) for k in signature} if isinstance(signature, dict) else set()
        )
        if not (signature_ids <= authorised_ids):
            raise UserError(self.env._("Some unauthorised items are filled"))

        if not isinstance(signature, dict):
            self.signature = signature
        else:
            SignItemValue = self.env["sign.request.item.value"]
            sign_request = self.sign_request_id
            new_item_values_list = []
            item_values_dict = {
                str(sign_item_value.sign_item_id.id): sign_item_value
                for sign_item_value in self.sign_item_value_ids
            }
            items_by_id = {
                str(item.id): item for item in sign_request.template_id.sign_item_ids
            }
            signature_item_ids = set(
                sign_request.template_id.sign_item_ids.filtered(
                    lambda r: r.type_id.item_type == "signature"
                ).ids
            )
            for itemId in signature:
                item = items_by_id.get(itemId)
                value = signature[itemId]
                if (
                    item
                    and item.type_id.item_type == "selection"
                    and value not in (False, "")
                    and not (str(value).isdigit() and int(value) in item.option_ids.ids)
                ):
                    # Reject a bad selection value at submission, so the offending
                    # signer is told, instead of crashing the LAST signer's render.
                    raise UserError(
                        self.env._(
                            "The value of a selection field must be one of its options."
                        )
                    )
                frame = kwargs.get("frame", False)
                if frame and itemId in frame:
                    frame_value = frame[itemId].get("frameValue", False)
                    frame_has_hash = bool(frame[itemId].get("frameHash", False))
                else:
                    frame_value = False
                    frame_has_hash = False
                if itemId not in item_values_dict:
                    new_item_values_list.append(
                        {
                            "sign_item_id": int(itemId),
                            "value": signature[itemId],
                            "frame_value": frame_value,
                            "frame_has_hash": frame_has_hash,
                            "sign_request_item_id": self.id,
                        }
                    )
                else:
                    item_values_dict[itemId].write(
                        {
                            "value": signature[itemId],
                            "frame_value": frame_value,
                            "frame_has_hash": frame_has_hash,
                        }
                    )
                if int(itemId) in signature_item_ids:
                    self.signature = signature[itemId][
                        signature[itemId].find(",") + 1 :
                    ]
            SignItemValue.create(new_item_values_list)

    def send_signature_accesses(self) -> None:
        self.sign_request_id._check_senders_validity()
        users = self.partner_id.user_ids
        user_ids = set(
            users.sudo()
            .search(
                [
                    ("all_group_ids", "in", self.env.ref("sign.group_sign_user").id),
                    ("id", "in", users.ids),
                ]
            )
            .ids
        )
        for sign_request, sign_request_items_list in groupby(
            self, lambda sri: sri.sign_request_id
        ):
            notified_users = [
                sri.partner_id.user_ids[:1]
                for sri in sign_request_items_list
                if not sri.is_mail_sent
                and sri.state == "sent"
                and sri.partner_id.user_ids[:1].id in user_ids
            ]
            sign_request._schedule_activity(notified_users)
            body = self.env._("The signature mail has been sent to: ")
            receiver_names = [
                "%s(%s)" % (sri.partner_id.name, sri.role_id.name)
                for sri in sign_request_items_list
            ]
            body += ", ".join(receiver_names)
            if not is_html_empty(sign_request.message):
                body += sign_request.message
            if not sign_request.communication_company_id:
                sign_request.communication_company_id = self.env.company
            sign_request.message_post(body=body)
        self._send_signature_access_message()

    def _get_user_signature(self, signature_type="sign_signature"):
        """Gets the user's stored sign_signature/sign_initials (needs sudo permission)
        :param str signature_type: 'sign_signature' or 'sign_initials'
        :returns bytes or False
        """
        self.check_singleton()
        sign_user = self.partner_id.user_ids[:1]
        current_user_sign = False
        if self.env.user._is_public() or (sign_user and sign_user == self.env.user):
            current_user_sign = True
        if current_user_sign and signature_type in ["sign_signature", "sign_initials"]:
            return sign_user[signature_type]
        return False

    def _get_user_signature_frame(self, signature_type="sign_signature_frame"):
        """Gets the user's stored signature/initials frame (needs sudo permission)
        :param str signature_type: 'sign_signature_frame' or 'sign_initials_frame'
        :returns: bytes or False
        """
        self.check_singleton()
        sign_user = self.partner_id.user_ids[:1]
        if sign_user and signature_type in [
            "sign_signature_frame",
            "sign_initials_frame",
        ]:
            return sign_user[signature_type]
        return False

    def _send_sms_code(self) -> bool:
        """Text the signer a new one-time code, voiding the previous one; False
        when the signer has had codes sent too often lately. Called in sudo, on
        the signer a link resolved to."""
        self.check_singleton()
        if not self._consume_send_budget(
            "sms_code", SMS_SEND_BURST, SMS_SEND_REFILL_SECONDS
        ):
            return False
        code = self._generate_sms_code()
        self.write(
            {
                "sms_code_hash": self._hash_sms_code(code, self.sms_number),
                "sms_code_expires_at": fields.Datetime.now() + SMS_CODE_LIFETIME,
                "sms_code_failures": 0,
            }
        )
        self.env["sms.sms"].sudo().create(
            {
                "body": self.env._("Your confirmation code is %s", code),
                "number": self.sms_number,
            }
        ).send()
        return True

    def _consume_send_budget(self, purpose, capacity, refill_seconds) -> bool:
        """Whether this signer may trigger one more message of ``purpose`` from a
        public route: ``capacity`` at once, refilled over ``refill_seconds``."""
        self.check_singleton()
        return self.env["rate.limit.bucket"].consume_for_key(
            f"sign.{purpose}:{self.id}",
            subject_model=self._name,
            subject_id=self.id,
            capacity=capacity,
            window_seconds=refill_seconds,
            strict=True,
        )

    @api.model
    def _generate_sms_code(self) -> str:
        return f"{secrets.randbelow(10**6):06d}"

    def _hash_sms_code(self, code, number) -> str:
        return hmac(
            self.env(su=True), SMS_CODE_SCOPE, (self.id, number or "", str(code))
        )

    def _verify_sms_code(self, code) -> bool:
        """Whether ``code`` is the live code last sent; a right code is used up
        and the phone recorded as verified, a wrong one counts towards voiding.
        Called in sudo, on the signer a link resolved to."""
        self.check_singleton()
        item = self
        # serialise attempts on one signer, so parallel guesses all count
        item.lock_for_update(allow_referencing=True, wait=True)
        item.invalidate_recordset(
            ["sms_code_hash", "sms_code_expires_at", "sms_code_failures"]
        )
        if (
            not item.sms_code_hash
            or not item.sms_code_expires_at
            or item.sms_code_expires_at < fields.Datetime.now()
        ):
            return False
        # a code verifies only for the number it was sent to
        if consteq(item._hash_sms_code(code, item.sms_number), item.sms_code_hash):
            item.write(
                {
                    "sms_code_hash": False,
                    "sms_code_expires_at": False,
                    "sms_verified_date": fields.Datetime.now(),
                    "sms_verified_number": item.sms_number,
                }
            )
            return True
        failures = item.sms_code_failures + 1
        item.write(
            {"sms_code_failures": failures}
            | (
                {"sms_code_hash": False, "sms_code_expires_at": False}
                if failures >= SMS_CODE_MAX_FAILURES
                else {}
            )
        )
        return False

    @api.model
    def _has_sms_credits(self) -> bool:
        """Whether an SMS can be sent: the client asks before offering the code,
        the server before refusing to sign without one. Credits matter only when
        the company sends through IAP; a balance IAP cannot tell (-1, an outage)
        does not block, sending says whether it went through."""
        if self.env.company._get_sms_api_class() is not SmsApi:
            return True
        return self.env["iap.account"].sudo().get_credits("sms") != 0

    def _notify_missing_sms_credits(self) -> None:
        """Tell the request's owner, once, that its signers wait for SMS credits
        to be able to sign."""
        self.check_singleton()
        sign_request = self.sign_request_id
        owner = sign_request.create_uid
        activity_type = "sign.mail_activity_data_sms_credits"
        if sign_request.activity_search([activity_type], user_id=owner.id):
            return
        sign_request.activity_schedule(
            activity_type,
            note=sign_request.with_context(lang=owner.lang).env._(
                "A signer cannot sign this document until SMS credits are added."
            ),
            user_id=owner.id,
        )

    def _compute_access_url(self):
        super()._compute_access_url()
        for signature_request in self:
            signature_request.access_url = "/my/signature/%s" % signature_request.id

    @api.model
    def _generate_expiry_link_timestamp(self) -> int:
        duration = int(
            self.env.registry.settings.get(self.env, "sign.link_expiry_duration", 360)
        )
        expiry_date = fields.Datetime.now() + timedelta(hours=duration)
        return int(expiry_date.timestamp())

    @api.model
    def _generate_expiry_signature(self, sign_request_item_id, timestamp):
        return hmac(self.env(su=True), EXPIRY_SCOPE, (timestamp, sign_request_item_id))

    def _is_expiry_valid(self, exp_timestamp, exp_hash) -> bool:
        """Validates if the expiry code is still valid
        :param float exp_timestamp: a timestamp provided by the user in the URL params
        :param str exp_hash: code provided in the URL to be checked
        """
        self.check_singleton()
        if not (exp_timestamp and exp_hash):
            return False
        try:
            exp_timestamp = int(exp_timestamp)
        except ValueError:
            return False
        now = fields.Datetime.now().timestamp()
        if now > exp_timestamp:
            return False
        return bool(
            consteq(exp_hash, self._generate_expiry_signature(self.id, exp_timestamp))
        )

    @api.depends("state")
    def _compute_color(self) -> None:
        color_map = {"canceled": 0, "sent": 0, "completed": 10}
        for sign_request_item in self:
            sign_request_item.color = color_map[sign_request_item.state]

    @api.depends("partner_id.email")
    def _compute_email(self) -> None:
        for sign_request_item in self.filtered(
            lambda sri: sri.state == "sent" or not sri.signer_email
        ):
            sign_request_item.signer_email = (
                sign_request_item.partner_id.email_normalized
            )

    @api.depends("partner_id.phone_ids")
    def _compute_sms_number(self) -> None:
        for item in self:
            item.sms_number = item.partner_id.phone_ids._primary().number

    def _get_constant_value(self, sign_item) -> str:
        """The value a read-only item holds for this signer: the field its type
        is linked to, a struck line, or what the template's author typed."""
        item_type = sign_item.type_id.sudo()
        if item_type.auto_field:
            return self._get_auto_field_value(
                {"id": item_type.id, "auto_field": item_type.auto_field}
            )
        if item_type.item_type == "strikethrough":
            return "striked"
        return sign_item.name

    def _get_auto_field_value(self, item_type):
        """Return the automatic value of a sign item based on the linked model and partner access
        :return: str: auto_value
        """
        self.check_singleton()
        item_type_sudo = self.env["sign.item.type"].sudo().browse(item_type["id"])
        record = None
        field_record_sudo = None
        if item_type_sudo.model_id.model == "res.partner":
            record = self.partner_id
        else:
            if item_type_sudo.item_type == "stamp":
                return self._get_stamp_value()

            linked_record = self.sign_request_id.reference_doc
            model = linked_record and self.env["ir.model"]._get(linked_record._name)
            if (
                not model
                or not model.is_mail_thread
                or linked_record._name != item_type_sudo.model_id.model
            ):
                return ""
            record = linked_record
        try:
            if record:
                field_record_sudo = (
                    self.env["ir.model.fields"]
                    .sudo()
                    ._get(record._name, item_type_sudo.auto_field)
                )
            auto_field = record.mapped(item_type["auto_field"])
            auto_value = (
                auto_field[0]
                if auto_field and not isinstance(auto_field, models.BaseModel)
                else ""
            )
            if field_record_sudo and field_record_sudo.ttype == "html":
                auto_value = html2plaintext(auto_value)
        except KeyError, TypeError:
            auto_value = ""
        return auto_value

    def _get_stamp_value(self) -> str:
        """
        Return the formatted stamp value (company name, address, phone) for the partner.

        :returns: str Company name and phone separated by a newline, or an empty string if not found.
        """
        partner = self.with_context(show_address=1).partner_id
        company_address = None

        if partner:
            if partner.parent_id:
                # Partner has a parent → use parent company
                company_address = partner.parent_id
            elif partner.is_company:
                # Partner is a standalone company → use itself (commercial partner)
                company_address = partner.commercial_partner_id
            elif partner.user_ids and partner.user_ids[0].company_id:
                # Partner is an individual user → use their company partner
                company_address = partner.user_ids[0].company_id.partner_id

        if not company_address:
            return ""

        return self.env._(
            "%(company_address)s\n%(phone)s",
            company_address=company_address.display_name,
            phone=company_address.phone_ids._primary().number or "",
        )
