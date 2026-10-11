import logging
import time
from datetime import datetime
from datetime import time as day_time

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.web import urljoin as url_join
from odoo.tools import (
    SQL,
    format_date,
    format_datetime,
    frozendict,
    get_lang,
    is_html_empty,
)

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused
from odoo.addons.sign.utils.mail_link import get_mail_link

_logger = logging.getLogger(__name__)


class SignRequest(models.Model):
    _name = "sign.request"
    _description = "Signature Request"
    _rec_name = "reference"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity", "mixin.user.favorite"]
    _access_anchors = frozendict(
        {
            "partner": "request_item_ids.partner_id",
        }
    )

    def _compute_access_token(self) -> None:
        links = (
            self.env["access.link"]
            ._record_links(
                self.filtered("id"),
                Domain("cause", "=", "notification")
                & Domain("audience", "=", "anyone")
                & Domain("role", "=", "view"),
            )
            .sorted("id", reverse=True)
        )
        shown = links._tokens()
        tokens = {}
        for link in links:
            if link.res_id not in tokens and link.id in shown:
                tokens[link.res_id] = shown[link.id]
        for sign_request in self:
            sign_request.access_token = tokens.get(sign_request.id, False)

    def _request_link_end(self):
        return self.validity and datetime.combine(self.validity, day_time(23, 59, 59))

    def _issue_request_links(self) -> None:
        Link = self.env["access.link"]
        for sign_request in self:
            __, token = Link._issue(
                sign_request,
                partner=sign_request.create_uid.partner_id,
                role="view",
                cause="notification",
                date_to=sign_request._request_link_end() or None,
            )
            sign_request._update_cache({"access_token": token}, validate=False)

    def _signer_chatter_token(self, partner) -> str:
        self.check_singleton()
        __, token = self.env["access.link"]._issue(
            self,
            partner=partner,
            role="comment",
            audience="partners",
            cause="notification",
            date_to=self._request_link_end() or None,
        )
        return token

    @api.model
    def _from_request_token(self, token, request_id):
        try:
            return (
                self.env["access.link"]
                ._resolve(token, model=self._name, res_id=int(request_id), action=None)
                .record
            )
        except LinkRefused, LinkLoginRequired, TypeError, ValueError:
            return self.browse()

    def _get_mail_link(self, email, subject):
        return get_mail_link(email, subject)

    @api.model
    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env["ir.model"]
            .sudo()
            .search([("model", "!=", "sign.request"), ("is_mail_thread", "=", "True")])
        ]

    template_id = fields.Many2one(
        comodel_name="sign.template",
        index=True,
        required=True,
    )
    subject = fields.Char(string="Email Subject")
    reference = fields.Char(
        string="Document Name",
        required=True,
        help="This is how the document will be named in the mail",
    )
    reference_doc = fields.Reference(
        selection="_selection_target_model",
        string="Linked To",
        index="btree_not_null",
    )

    access_token = fields.Char(
        string="Security Token",
        compute="_compute_access_token",
        help="The token of the request's view link; the link is an access.link "
        "row holding its hash.",
    )
    share_link = fields.Char(
        compute="_compute_share_link",
        readonly=False,
    )
    is_shared = fields.Boolean(
        string="Share Request Button",
        compute="_compute_is_shared",
        inverse="_inverse_is_shared",
    )

    request_item_ids = fields.One2many(
        comodel_name="sign.request.item",
        inverse_name="sign_request_id",
        string="Signers",
        copy=True,
    )
    state = fields.Selection(
        selection=[
            ("shared", "Shared"),
            ("sent", "To Sign"),
            ("signed", "Signed"),
            ("canceled", "Cancelled"),
            ("expired", "Expired"),
        ],
        default="sent",
        index=True,
        copy=False,
        group_expand=True,
        tracking=True,
    )

    template_document_ids = fields.Many2many(
        comodel_name="sign.document",
        string="Documents",
        compute="_compute_template_document_ids",
    )
    completed_document_ids = fields.One2many(
        comodel_name="sign.completed.document",
        inverse_name="sign_request_id",
        string="Completed Documents Binaries",
        copy=False,
    )
    nb_wait = fields.Integer(
        string="Sent Requests",
        compute="_compute_stats",
        store=True,
    )
    nb_closed = fields.Integer(
        string="Completed Signatures",
        compute="_compute_stats",
        store=True,
    )
    nb_total = fields.Count(
        count_of="request_item_ids",
        string="Requested Signatures",
        store=True,
    )
    progress = fields.Char(
        compute="_compute_progress",
        compute_sudo=True,
    )
    start_sign = fields.Boolean(
        string="Signature Started",
        compute="_compute_progress",
        compute_sudo=True,
        help="At least one signer has signed the document.",
    )
    integrity = fields.Boolean(
        string="Integrity of the Sign request",
        compute="_compute_hashes",
        compute_sudo=True,
    )
    integrity_error = fields.Char(
        compute="_compute_hashes",
        compute_sudo=True,
    )

    active = fields.Boolean(
        default=True,
        copy=False,
    )
    favorite_user_ids = fields.Many2many(string="Favorite of")

    color = fields.Integer()
    request_item_infos = fields.Binary(compute="_compute_request_item_infos")
    last_action_date = fields.Datetime(
        related="message_ids.create_date",
        string="Last Action Date",
        readonly=True,
    )
    completion_date = fields.Date(
        compute="_compute_completion_date",
        compute_sudo=True,
        store=True,
    )
    communication_company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company used for communication",
        default=lambda self: self.env.company,
    )

    sign_log_ids = fields.One2many(
        comodel_name="sign.log",
        inverse_name="sign_request_id",
        string="Logs",
        help="Activity logs linked to this request",
    )
    template_tags = fields.Many2many(
        comodel_name="sign.template.tag",
        string="Tags",
    )
    cc_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Copy to",
        compute="_compute_cc_partners",
    )
    message = fields.Html(string="sign.message")
    message_cc = fields.Html(string="sign.message_cc")
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Attachments",
        copy=False,
        readonly=True,
        ondelete="restrict",
        bypass_search_access=True,
    )
    completed_document_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="sign_request_completed_document_rel",
        string="Completed Documents",
        copy=False,
        readonly=True,
        ondelete="restrict",
        bypass_search_access=True,
    )

    need_my_signature = fields.Boolean(
        compute="_compute_need_my_signature",
        search="_search_need_my_signature",
    )

    validity = fields.Date(string="Valid Until")
    reminder_enabled = fields.Boolean(default=False)
    reminder = fields.Integer(default=7)
    last_reminder = fields.Date(
        string="Last reminder",
        default=lambda self: fields.Date.today(),
    )
    certificate_reference = fields.Boolean(default=False)

    send_channel = fields.Selection(
        selection=[
            ("email", "Email"),
        ],
        string="Delivery Method",
        default="email",
        required=True,
    )

    @api.depends("template_id")
    def _compute_template_document_ids(self) -> None:
        for sign_request in self:
            sign_request.template_document_ids = (
                sign_request.template_id.sudo().document_ids
            )

    @api.constrains("reminder_enabled", "reminder")
    def _check_reminder(self) -> None:
        for request in self:
            if request.reminder_enabled and request.reminder <= 0:
                raise UserError(
                    self.env._(
                        "We can only send reminders in the future - as soon as we find a way to send reminders in the past we'll notify you.\nIn the mean time, please make sure to input a positive number of days for the reminder interval."
                    )
                )

    @api.depends("state")
    def _compute_is_shared(self) -> None:
        for sign_request in self:
            sign_request.is_shared = sign_request.state == "shared"

    def _inverse_is_shared(self) -> None:
        for sign_request in self:
            if sign_request.is_shared:
                sign_request.state = "shared"
            else:
                sign_request.state = "sent"

    @api.depends_context("uid")
    def _compute_need_my_signature(self) -> None:
        my_partner_id = self.env.user.partner_id
        for sign_request in self:
            sign_request.need_my_signature = any(
                sri.partner_id.id == my_partner_id.id
                and sri.state == "sent"
                and sri.is_mail_sent
                for sri in sign_request.request_item_ids
            )

    @api.model
    def _search_need_my_signature(self, operator, value):
        if operator != "in":
            return NotImplemented
        my_partner_id = self.env.user.partner_id
        documents_ids = (
            self.env["sign.request.item"]
            .search(
                [
                    ("partner_id", "=", my_partner_id.id),
                    ("state", "=", "sent"),
                    ("is_mail_sent", "=", True),
                ]
            )
            .mapped("sign_request_id")
            .ids
        )
        return [("id", "in", documents_ids)]

    @api.depends("request_item_ids.state")
    def _compute_stats(self) -> None:
        for rec in self:
            rec.nb_wait = len(
                rec.request_item_ids.filtered(lambda sri: sri.state == "sent")
            )
            rec.nb_closed = rec.nb_total - rec.nb_wait

    @api.depends("request_item_ids.state")
    def _compute_progress(self) -> None:
        for rec in self:
            rec.start_sign = bool(rec.nb_closed)
            rec.progress = f"{rec.nb_closed} / {rec.nb_total}"

    @api.depends("request_item_ids.state")
    def _compute_completion_date(self) -> None:
        for rec in self:
            rec.completion_date = (
                rec.request_item_ids.sorted(key="signing_date", reverse=True)[
                    :1
                ].signing_date
                if not rec.nb_wait
                else None
            )

    @api.depends("request_item_ids.state", "request_item_ids.partner_id.name")
    def _compute_request_item_infos(self) -> None:
        for request in self:
            request.request_item_infos = [
                {
                    "id": item.id,
                    "partner_name": item.display_name,
                    "state": item.state,
                    "signing_date": item.signing_date or "",
                }
                for item in request.request_item_ids
            ]

    @api.depends("message_follower_ids.partner_id")
    def _compute_cc_partners(self) -> None:
        for sign_request in self:
            sign_request.cc_partner_ids = (
                sign_request.message_follower_ids.partner_id
                - sign_request.request_item_ids.partner_id
            )

    @api.depends("request_item_ids.access_token", "state")
    def _compute_share_link(self) -> None:
        self.share_link = False
        for sign_request in self.filtered(lambda sr: sr.state == "shared"):
            sign_request.share_link = "%s/sign/document/mail/%s/%s" % (
                sign_request.get_base_url(),
                sign_request.id,
                sign_request.request_item_ids[0].sudo().access_token,
            )

    @api.model_create_multi
    def create(self, vals_list):
        sign_requests = super().create(vals_list)
        sign_requests._issue_request_links()
        sign_requests.template_id._check_send_ready()
        for sign_request in sign_requests:
            if not sign_request.request_item_ids:
                raise ValidationError(
                    self.env._(
                        "A valid sign request needs at least one sign request item"
                    )
                )
            sign_request.template_tags = [
                Command.set(sign_request.template_id.tag_ids.ids)
            ]
            sign_request.attachment_ids.write(
                {"res_model": sign_request._name, "res_id": sign_request.id}
            )
            sign_request.message_subscribe(
                partner_ids=sign_request.request_item_ids.partner_id.ids
            )
            sign_request._update_constant_items()
            self.env["sign.log"].sudo().create(
                {"sign_request_id": sign_request.id, "action": "create"}
            )

        if not self.env.context.get("no_sign_mail"):
            sign_requests.send_signature_accesses()
        return sign_requests

    def _update_constant_items(self) -> None:
        self.check_singleton()
        constant_items = self.template_id.sign_item_ids.filtered("constant")
        if not constant_items:
            return
        for request_item in self.request_item_ids:
            values = {
                str(item.id): request_item._get_constant_value(item)
                for item in constant_items
                if item.responsible_id == request_item.role_id
            }
            if values:
                request_item.sudo()._update_signature_values(values)

    def write(self, vals):
        if "state" in vals and not self._is_state_write_allowed():
            raise UserError(
                self.env._("Only the request's owner can change its status.")
            )
        res = super().write(vals)
        if (
            vals.get("validity")
            and fields.Date.from_string(vals["validity"]) < fields.Date.today()
        ):
            self.filtered(lambda sr: sr.state in ("sent", "shared")).state = "expired"
        if "validity" in vals:
            self._move_signer_links()
        return res

    def _move_signer_links(self) -> None:
        items = self.request_item_ids
        Link = self.env["access.link"]
        notification = Domain("cause", "=", "notification")
        links = (
            Link._record_links(items, notification)
            | Link._record_links(self, notification)
        ).with_privilege(
            "base.privilege_manage_links", reason="the request's validity moved"
        )
        ends = {
            ("sign.request.item", item.id): item._signer_link_end() for item in items
        }
        ends |= {
            (self._name, sign_request.id): sign_request._request_link_end()
            for sign_request in self
        }
        for link in links:
            link.date_to = ends.get((link.res_model, link.res_id)) or link.date_to

    def _is_state_write_allowed(self) -> bool:
        return bool(
            self.env.su
            or self.env.user.has_group("sign.group_sign_manager")
            or all(sr.create_uid == self.env.user for sr in self)
        )

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if "attachment_ids" not in default:
            for request, vals in zip(self, vals_list, strict=False):
                vals["attachment_ids"] = request.attachment_ids.copy().ids
        return vals_list

    def copy(self, default=None):
        sign_requests = super().copy(default)
        for old_request, new_request in zip(self, sign_requests, strict=False):
            new_request.message_subscribe(partner_ids=old_request.cc_partner_ids.ids)
        return sign_requests

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_signed(self) -> None:
        if any(r.state == "signed" for r in self):
            raise UserError(
                self.env._(
                    "Signed documents cannot be deleted for legal reasons. Please archive them instead."
                )
            )

    def action_archive(self):
        self.filtered(lambda sr: sr.active and sr.state == "sent").cancel()
        return super().action_archive()

    def _check_senders_validity(self) -> None:
        invalid_senders = self.create_uid.filtered(lambda u: not u.email_formatted)
        if invalid_senders:
            raise ValidationError(
                self.env._(
                    "Please configure senders'(%s) email addresses",
                    ", ".join(invalid_senders.mapped("name")),
                )
            )

    def _check_signers_roles_validity(self) -> None:
        for sign_request in self:
            template_roles = (
                sign_request.sudo().template_id.sign_item_ids.responsible_id
            )
            sign_request_items = sign_request.request_item_ids
            if len(sign_request_items) != max(len(template_roles), 1) or set(
                sign_request_items.role_id.ids
            ) != (
                set(template_roles.ids)
                if template_roles
                else {self.env.ref("sign.sign_item_role_default").id}
            ):
                raise ValidationError(
                    self.env._(
                        "You must specify one signer for each role of your sign template"
                    )
                )

    def _check_signers_partners_validity(self) -> None:
        for sign_request in self:
            sign_request_items = sign_request.request_item_ids
            if sign_request.state != "shared" and any(
                not sri.partner_id for sri in sign_request_items
            ):
                raise ValidationError(
                    self.env._(
                        "A non-shared sign request's should not have any signer with an empty partner"
                    )
                )

    def _get_final_recipients(self):
        return set(self.request_item_ids.mapped("signer_email")) | set(
            self.cc_partner_ids.filtered(lambda p: p.email_formatted).mapped("email")
        )

    def _get_next_sign_request_items(self):
        self.check_singleton()
        sign_request_items_sent = self.request_item_ids.filtered(
            lambda sri: sri.state == "sent"
        )
        if not sign_request_items_sent:
            return self.env["sign.request.item"]
        smallest_order = min(sign_request_items_sent.mapped("mail_sent_order"))
        return sign_request_items_sent.filtered(
            lambda sri: sri.mail_sent_order == smallest_order
        )

    def go_to_document(self):
        self.check_singleton()
        request_items = self.request_item_ids.filtered(
            lambda r: (
                not r.partner_id
                or (
                    r.state == "sent" and r.partner_id.id == self.env.user.partner_id.id
                )
            )
        )
        sequenced_signature_mail = any(
            req.mail_sent_order > 1 for req in self.request_item_ids
        )
        return {
            "name": self.reference,
            "type": "ir.actions.client",
            "tag": "sign.Document",
            "context": {
                "id": self.id,
                "token": self.access_token,
                "need_to_sign": bool(request_items),
                "create_uid": self.create_uid.id,
                "state": self.state,
                "request_item_states": {
                    str(item.id): item.is_mail_sent for item in self.request_item_ids
                },
                "sequenced_signature_mail": sequenced_signature_mail,
            },
        }

    def go_to_signable_document(self, request_items=None):
        self.check_singleton()
        if not request_items:
            request_items = self.request_item_ids.filtered(
                lambda r: (
                    not r.partner_id
                    or (
                        r.state == "sent"
                        and r.partner_id.id == self.env.user.partner_id.id
                    )
                )
            )
        if not request_items:
            return None
        return {
            "name": self.reference,
            "type": "ir.actions.client",
            "tag": "sign.SignableDocument",
            "context": {
                "id": self.id,
                "token": request_items[:1].sudo().access_token,
                "create_uid": self.create_uid.id,
                "state": self.state,
                "request_item_states": {
                    item.id: item.is_mail_sent for item in self.request_item_ids
                },
                "template_editable": self.nb_closed == 0,
                "token_list": request_items[1:].sudo().mapped("access_token"),
                "name_list": [item.partner_id.name for item in request_items[1:]],
            },
        }

    def get_sign_request_documents(self) -> dict:
        if not self:
            raise UserError(
                self.env._("You should select at least one document to download.")
            )

        if len(self) == 1:
            if self.state == "signed":
                return {
                    "name": "Signed Document",
                    "type": "ir.actions.act_url",
                    "url": "/sign/download/%(request_id)s/%(access_token)s/completed"
                    % {"request_id": self.id, "access_token": self.access_token},
                }
            else:
                return {
                    "name": "Template Document",
                    "type": "ir.actions.act_url",
                    "url": "/sign/download/%(request_id)s/%(access_token)s/origin"
                    % {"request_id": self.id, "access_token": self.access_token},
                }
        else:
            return {
                "name": "Sign Request Documents",
                "type": "ir.actions.act_url",
                "url": f"/sign/download/zip/{','.join(map(str, self.ids))}",
            }

    def _get_linked_record_action(self, default_action=None):
        self.check_singleton()
        if not default_action:
            default_action = {}
        action_rec_sudo = (
            self.env["ir.actions.act_window"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self.reference_doc._name),
                    ("context", "not ilike", "active_id"),
                ],
                limit=1,
            )
        )
        if action_rec_sudo:
            action = action_rec_sudo._get_action_dict()
            action.update(
                {
                    "views": [(False, "form")],
                    "view_mode": "form",
                    "res_id": self.reference_doc.id,
                    "target": "current",
                }
            )
        else:
            action = default_action
        return action

    def get_close_values(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "sign.sign_request_action"
        )
        result = {
            "action": action,
            "label": self.env._("Close"),
            "custom_action": False,
        }
        if (
            self.reference_doc
            and self.reference_doc.exists()
            and self.reference_doc.has_access("read")
        ):
            action = self._get_linked_record_action(action)
            result = {
                "action": action,
                "label": self.env._("Back to %s", self.reference_doc._description),
                "custom_action": True,
            }
        return result

    @api.depends("sign_log_ids.log_hash", "sign_log_ids.action")
    def _compute_hashes(self) -> None:
        for document in self:
            try:
                error = document.sign_log_ids._get_integrity_error()
            except Exception:
                _logger.warning(
                    "sign.request %s: integrity check failed",
                    document.id,
                    exc_info=True,
                )
                error = self.env._("The history could not be verified.")
            document.integrity_error = error
            document.integrity = not error

    def _refuse(self, refuser, refusal_reason):
        self.check_singleton()
        if self.state != "sent":
            raise UserError(self.env._("This sign request cannot be refused"))
        self._check_senders_validity()
        self.cancel()

        for user in self.request_item_ids.partner_id.user_ids.filtered(
            lambda u: u.has_group("sign.group_sign_user")
        ):
            self.activity_unlink(
                ["sign.mail_activity_data_signature_request"], user_id=user.id
            )

        for sign_request_item in self.request_item_ids:
            self._send_refused_message(
                refuser,
                refusal_reason,
                sign_request_item.partner_id,
                access_token=sign_request_item.sudo().access_token,
                force_send=True,
                sign_request_item=sign_request_item,
            )
        for partner in self.cc_partner_ids.filtered(lambda p: p.email_formatted):
            self._send_refused_message(refuser, refusal_reason, partner)

    def _send_refused_message(
        self,
        refuser,
        refusal_reason,
        partner,
        access_token=None,
        force_send=False,
        sign_request_item=None,
    ):
        self.check_singleton()
        if access_token is None:
            access_token = self.access_token
        subject = self.env._(
            "The document %(template_name)s has been rejected by %(refuser_name)s",
            template_name=self.template_id.name,
            refuser_name=refuser.name,
        )
        base_url = self.get_base_url()
        partner_lang = get_lang(self.env, lang_code=partner.lang).code
        body = self.env["ir.qweb"]._render(
            "sign.sign_template_mail_refused",
            {
                "record": self,
                "recipient": partner,
                "refuser": refuser,
                "link": url_join(
                    base_url, "sign/document/%s/%s" % (self.id, access_token)
                ),
                "subject": subject,
                "body": Markup('<p style="white-space: pre">{}</p>').format(
                    refusal_reason
                ),
            },
            lang=partner_lang,
            minimal_qcontext=True,
        )

        self.with_context(lang=partner.lang or self.env.lang)._message_send_mail(
            body,
            record_name=self.reference,
            notif_values={
                "model_description": self.env._("Signature"),
                "company": self.communication_company_id or self.create_uid.company_id,
                "partner": partner,
            },
            mail_values={
                "subject": subject,
            },
            force_send=force_send,
        )

    def send_signature_accesses(self) -> None:
        allowed_request_ids = self.filtered(lambda sr: sr.state == "sent")
        allowed_request_ids._check_senders_validity()
        for sign_request in allowed_request_ids:
            sign_request._get_next_sign_request_items().send_signature_accesses()
            sign_request.last_reminder = fields.Date.today()

    @api.model
    def _cron_reminder(self) -> None:
        today = fields.Date.today()
        self.search(
            [("state", "=", "sent"), ("validity", "<", today)]
        ).state = "expired"
        self.flush_model()
        self.env.cr.execute(
            SQL(
                """
                SELECT id
                  FROM sign_request
                 WHERE state = 'sent'
                   AND active
                   AND reminder_enabled
                   AND last_reminder + reminder * interval '1 day' <= %(today)s
                """,
                today=today,
            )
        )
        self.browse(row[0] for row in self.env.cr.fetchall()).with_context(
            force_send=False
        ).send_signature_accesses()

    def _sign(self):
        self.check_singleton()
        if self.state != "sent" or any(
            sri.state != "completed" for sri in self.request_item_ids
        ):
            raise UserError(self.env._("This sign request cannot be signed"))
        self.write({"state": "signed"})
        self._send_completed_documents()

        if self.reference_doc:
            model = self.env["ir.model"]._get(self.reference_doc._name)
            if model.is_mail_thread:
                self.reference_doc.message_post_with_source(
                    "sign.message_signature_link",
                    render_values={"request": self},
                    subtype_xmlid="mail.mt_note",
                )
                attachment_values = [
                    {
                        "name": doc.document_id.name,
                        "datas": doc.file,
                        "type": "binary",
                        "res_model": self.reference_doc._name,
                        "res_id": self.reference_doc.id,
                    }
                    for doc in self.completed_document_ids
                ]
                self.env["ir.attachment"].create(attachment_values)

    def cancel(self):
        self.env["access.link"].with_privilege(
            "base.privilege_manage_links", reason="cancel a signature request"
        )._revoke_record_links(self, "the signature request was cancelled")
        for sign_request in self:
            sign_request.write({"state": "canceled"})
        self._issue_request_links()
        self.request_item_ids._cancel()

        for user in self.request_item_ids.sudo().partner_id.user_ids.filtered(
            lambda u: u.has_group("sign.group_sign_user")
        ):
            self.activity_unlink(
                ["sign.mail_activity_data_signature_request"], user_id=user.id
            )

        self.env["sign.log"].sudo().create(
            [
                {"sign_request_id": sign_request.id, "action": "cancel"}
                for sign_request in self
            ]
        )

    def _send_completed_documents(self) -> None:
        self.check_singleton()
        if self.state != "signed":
            raise UserError(self.env._("The sign request has not been fully signed"))
        self._check_senders_validity()

        if not self.completed_document_ids:
            self._create_completed_documents()
        self._log_completion()

        signers = [
            {
                "name": signer.partner_id.name,
                "email": signer.signer_email,
                "id": signer.partner_id.id,
            }
            for signer in self.request_item_ids
        ]
        request_edited = any(log.action == "update" for log in self.sign_log_ids)
        for sign_request_item in self.request_item_ids:
            self._send_completed_documents_message(
                signers,
                request_edited,
                sign_request_item.partner_id,
                access_token=sign_request_item.sudo().access_token,
                with_message_cc=False,
                force_send=True,
                sign_request_item=sign_request_item,
            )

        cc_partners_valid = self.cc_partner_ids.filtered(lambda p: p.email_formatted)
        for cc_partner in cc_partners_valid:
            self._send_completed_documents_message(signers, request_edited, cc_partner)
        if cc_partners_valid:
            body = self.env._(
                "The mail has been sent to contacts in copy: %(contacts)s",
                contacts=cc_partners_valid.mapped("name"),
            )
            if not is_html_empty(self.message_cc):
                body += self.message_cc
            self.message_post(
                body=body,
                attachment_ids=self.attachment_ids.ids
                + self.completed_document_attachment_ids.ids,
            )

    def _send_completed_documents_message(
        self,
        signers,
        request_edited,
        partner,
        access_token=None,
        with_message_cc=True,
        force_send=False,
        sign_request_item=None,
    ):
        self.check_singleton()
        if access_token is None:
            access_token = self.access_token
        partner_lang = get_lang(self.env, lang_code=partner.lang).code
        base_url = self.get_base_url()
        body = self.env["ir.qweb"]._render(
            "sign.sign_template_mail_completed",
            {
                "record": self,
                "link": url_join(
                    base_url, "sign/document/%s/%s" % (self.id, access_token)
                ),
                "subject": "%s signed" % self.reference,
                "body": self.message_cc
                if with_message_cc and not is_html_empty(self.message_cc)
                else False,
                "recipient_name": partner.name,
                "recipient_id": partner.id,
                "signers": signers,
                "request_edited": request_edited,
            },
            lang=partner_lang,
            minimal_qcontext=True,
        )

        self.with_context(lang=partner.lang or self.env.lang)._message_send_mail(
            body,
            record_name=self.reference,
            notif_values={
                "model_description": self.env._("Signature"),
                "company": self.communication_company_id or self.create_uid.company_id,
                "partner": partner,
            },
            mail_values={
                "attachment_ids": self.attachment_ids.ids
                + self.completed_document_attachment_ids.ids,
                "subject": self.env._("%s has been edited and signed", self.reference)
                if request_edited
                else self.env._("%s has been signed", self.reference),
            },
            force_send=force_send,
        )

    @api.autovacuum
    def _gc_expired_sr(self) -> None:
        sign_request = self.env["sign.request"].search(
            [("state", "=", "shared"), ("validity", "<", fields.Date.today())]
        )
        sign_request.unlink()


    def _get_user_formatted_datetime(self, datetime_val):
        return format_datetime(
            self.env, datetime_val, tz="UTC", lang_code=self.create_uid.lang
        )

    def _get_final_signature_log_hash(self):
        self.check_singleton()
        if not self.certificate_reference:
            return False

        final_log = self.env["sign.log"].search(
            [
                ("sign_request_id", "=", self.id),
                ("action", "in", ["sign", "create"]),
            ],
            order="id DESC",
            limit=1,
        )

        return final_log.log_hash if final_log else False

    def _log_completion(self) -> None:
        self.check_singleton()
        if self.completed_document_ids and not self.sign_log_ids.filtered(
            lambda log: log.action == "complete"
        ):
            self.env["sign.log"].create(
                {"sign_request_id": self.id, "action": "complete"}
            )

    def _get_signed_values(self) -> dict[int, dict]:
        self.check_singleton()
        values = self.env["sign.request.item.value"].search(
            [("sign_request_item_id", "in", self.request_item_ids.ids)]
        )
        return {
            value.sign_item_id.id: {
                "value": value.value,
                "frame": value.frame_value,
                "frame_has_hash": value.frame_has_hash,
            }
            for value in values
        }

    def _create_completed_documents(self) -> None:
        if any(record.state != "signed" for record in self):
            raise UserError(
                self.env._(
                    "The completed document cannot be created because the sign request is not fully signed"
                )
            )

        for record in self:
            if not record.completed_document_ids:
                self.env["sign.completed.document"].create(
                    [
                        {
                            "sign_request_id": record.id,
                            "document_id": document.id,
                        }
                        for document in record.template_id.document_ids
                    ]
                )
                record.completed_document_ids._update_completed_document()
                record._log_completion()
                attachment_ids = self.env["ir.attachment"].create(
                    [
                        {
                            "name": document.document_id.name,
                            "datas": document.file,
                            "type": "binary",
                            "res_model": record._name,
                            "res_id": record.id,
                        }
                        for document in record.completed_document_ids
                    ]
                )

                public_user = self.env.ref("base.public_user", raise_if_not_found=False)
                if not public_user:
                    public_user = self.env.user
                pdf_content, __ = (
                    self.env["ir.actions.report"]
                    .with_user(public_user)
                    .sudo()
                    ._render_qweb_pdf(
                        "sign.action_sign_request_print_logs",
                        record.id,
                        data={
                            "format_date": format_date,
                            "company_id": record.communication_company_id,
                        },
                    )
                )
                attachment_log = self.env["ir.attachment"].create(
                    {
                        "name": self.env._(
                            "Certificate of completion - %s.pdf",
                            time.strftime("%Y-%m-%d - %H:%M:%S"),
                        ),
                        "raw": pdf_content,
                        "type": "binary",
                        "res_model": record._name,
                        "res_id": record.id,
                    }
                )
                record.completed_document_attachment_ids = [
                    Command.link(attachment_log.id)
                ] + [Command.link(att.id) for att in attachment_ids]

    def _get_signing_field_name(self) -> str:
        return self.env.company.name


    def _message_send_mail(
        self,
        body,
        notif_values=None,
        mail_values=None,
        record_name=False,
        force_send=False,
    ):
        notif_values = notif_values or {}
        company = notif_values.get("company")
        model_description = notif_values.get("model_description")
        partner = notif_values.get("partner")
        notification_layout_xmlid = notif_values.get(
            "notification_layout_xmlid", "sign.sign_mail_notification_light"
        )
        scheduled_date = self.env.context.get("scheduled_date", False)

        mail_values = mail_values or {}
        if "author_id" not in mail_values:
            mail_values["author_id"] = self.create_uid.partner_id.id
            mail_values["email_from"] = self.create_uid.email_formatted
        if "email_to" not in mail_values:
            mail_values["email_to"] = partner.email_formatted

        if (
            partner
            and len(partner.user_ids) == 1
            and partner.user_ids.notification_type == "inbox"
        ):
            return self.message_notify(
                attachment_ids=mail_values.get("attachment_ids"),
                author_id=self.create_uid.partner_id.id,
                body=body,
                email_from=mail_values.get("email_from"),
                force_record_name=record_name,
                force_send=force_send,
                mail_auto_delete=False,
                model_description=model_description,
                partner_ids=partner.ids,
                subject=mail_values.get("subject"),
            )

        mail_values["body_html"] = self.env["mixin.mail.render"]._render_encapsulate(
            notification_layout_xmlid,
            body,
            context_record=self,
            add_context={
                "company": company,
                "model_description": model_description,
                "record_name": record_name,
            },
        )
        mail_values["reply_to"] = mail_values.get("email_from")
        if scheduled_date:
            mail_values["scheduled_date"] = scheduled_date
        mail = self.env["mail.mail"].sudo().create(mail_values)
        if force_send and not scheduled_date:
            mail.send_after_commit()
        return mail

    def _schedule_activity(self, sign_users) -> None:
        for user in sign_users:
            self.with_context(mail_activity_quick_update=True).activity_schedule(
                "sign.mail_activity_data_signature_request", user_id=user.id
            )
