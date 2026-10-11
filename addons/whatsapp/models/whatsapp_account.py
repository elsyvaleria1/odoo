import hashlib
import hmac
import logging
import mimetypes
import secrets
import string

import psycopg
from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.modules.registry import Registry
from odoo.tools import consteq, frozendict, plaintext2html

from odoo.addons.integration.tools.admission import Resolution
from odoo.addons.whatsapp.tools.whatsapp_api import WhatsAppApi
from odoo.addons.whatsapp.tools.whatsapp_exception import WhatsAppError

_logger = logging.getLogger(__name__)


class WhatsappAccount(models.Model):
    _name = "whatsapp.account"
    _inherit = ["mixin.mail.thread"]
    _description = "WhatsApp Business Account"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("allowed_company_ids", shared=False),
        }
    )

    name = fields.Char(tracking=1)
    active = fields.Boolean(
        default=True,
        tracking=6,
    )

    app_uid = fields.Char(
        string="App ID",
        required=True,
        tracking=2,
    )
    account_uid = fields.Char(
        string="Account ID",
        required=True,
        tracking=3,
    )
    phone_uid = fields.Char(
        string="Phone Number ID",
        required=True,
        tracking=4,
    )
    phone_number = fields.Char(
        copy=False,
        readonly=True,
        help="The phone number used in the Whatsapp Business Account.",
    )

    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        copy=False,
        ondelete="restrict",
        groups="whatsapp.group_whatsapp_admin",
        help="Holds this account's App Secret, Access Token and Webhook Verify "
        "Token as one record: they are one Meta app registration.",
    )
    app_secret = fields.Char(
        compute="_compute_secrets",
        inverse="_inverse_app_secret",
        groups="whatsapp.group_whatsapp_admin",
    )
    token = fields.Char(
        string="Access Token",
        compute="_compute_secrets",
        inverse="_inverse_token",
        groups="whatsapp.group_whatsapp_admin",
    )
    webhook_verify_token = fields.Char(
        compute="_compute_secrets",
        inverse="_inverse_webhook_verify_token",
        groups="whatsapp.group_whatsapp_admin",
    )
    callback_url = fields.Char(
        string="Callback URL",
        compute="_compute_callback_url",
        copy=False,
        readonly=True,
    )
    debug_logging = fields.Boolean(
        string="Debug logging",
        help="Log requests in order to ease debugging",
    )

    allowed_company_ids = fields.Many2many(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        required=True,
        domain=[("share", "=", False)],
        tracking=5,
        help="Users to notify when a message is received and there is no template send in last 15 days",
    )

    templates_count = fields.Integer(
        string="Message Count",
        compute="_compute_templates_count",
    )

    _phone_uid_unique = models.Constraint(
        "unique(phone_uid)",
        "The same phone number ID already exists",
    )

    @api.constrains("notify_user_ids")
    def _check_notify_user_ids(self) -> None:
        for phone in self:
            if len(phone.notify_user_ids) < 1:
                raise ValidationError(self.env._("Users to notify is required"))

    def _compute_callback_url(self) -> None:
        for account in self:
            account.callback_url = self.get_base_url() + "/whatsapp/webhook"

    @api.depends("credential_id")
    def _compute_secrets(self) -> None:
        for rec in self:
            values = rec._wa_credential_values()
            rec.app_secret = values.get("app_secret") or False
            rec.token = values.get("token") or False
            rec.webhook_verify_token = values.get("webhook_verify_token") or False

    def _wa_mint_missing_webhook_verify_tokens(self) -> None:
        for rec in self.filtered("credential_id"):
            if rec._wa_credential_values().get("webhook_verify_token"):
                continue
            rec._wa_store_secret(
                "webhook_verify_token",
                "".join(
                    secrets.choice(string.ascii_letters + string.digits)
                    for _ in range(8)
                ),
            )
            rec.invalidate_recordset(["webhook_verify_token"])

    @api.model
    def _receiver_for_webhook(self, **path_args):
        try:
            data = json_loads(request.httprequest.get_data(cache=True) or b"{}")
            account_uid = data["entry"][0]["id"]
        except ValueError, KeyError, IndexError, TypeError:
            return Resolution(self.browse(), claimed="no business account in the body")
        accounts = self.sudo().search([("account_uid", "=", account_uid)])
        if not accounts:
            return Resolution(self.browse(), claimed=f"account {account_uid}"[:64])
        account = (
            accounts._webhook_signer(
                dict(request.httprequest.headers), request.httprequest.get_data()
            )
            or accounts[:1]
        )
        return Resolution(account, verify=account._is_webhook_signature_valid)

    @api.model
    def _receiver_for_webhook_verification(self, **path_args):
        params = request.get_http_params()
        token = params.get("hub.verify_token")
        mode = params.get("hub.mode")
        challenge = params.get("hub.challenge")
        if not (token and mode and challenge):
            return Resolution(self.browse(), claimed="incomplete handshake")
        account = (
            self.sudo()
            .search([])
            .filtered(
                lambda account: (
                    account.webhook_verify_token
                    and consteq(account.webhook_verify_token, token)
                )
            )[:1]
        )
        if not account or mode != "subscribe":
            return Resolution(self.browse(), claimed="verify token")
        return Resolution(
            account,
            {"challenge": challenge},
            verify=lambda headers, body: consteq(
                account.sudo().webhook_verify_token, token
            ),
        )

    def _webhook_signer(self, headers, body):
        return self.filtered(
            lambda account: account._is_webhook_signature_valid(headers, body)
        )[:1]

    def _is_webhook_signature_valid(self, headers, body) -> bool:
        self.check_singleton()
        signature = headers.get("X-Hub-Signature-256")
        if not signature or not signature.startswith("sha256=") or len(signature) != 71:
            _logger.warning("Invalid signature header %r", signature)
            return False
        app_secret = self.sudo().app_secret
        if not app_secret:
            _logger.warning("App-secret is missing, can not check signature")
            return False
        expected = hmac.new(
            app_secret.encode(), msg=body, digestmod=hashlib.sha256
        ).hexdigest()
        return consteq(signature[7:], expected)

    def _inverse_app_secret(self) -> None:
        for rec in self:
            rec._wa_store_secret("app_secret", rec.app_secret)

    def _inverse_token(self) -> None:
        for rec in self:
            rec._wa_store_secret("token", rec.token)

    def _inverse_webhook_verify_token(self) -> None:
        for rec in self:
            rec._wa_store_secret("webhook_verify_token", rec.webhook_verify_token)

    def _wa_credential_values(self) -> dict:
        self.check_singleton()
        credential = self.credential_id.sudo()
        if not credential:
            return {}
        try:
            return {
                key: value
                for key, value in credential._use_secret_payload(
                    "whatsapp:account"
                ).items()
                if key not in credential._JSON_ACCESSOR_FIELDS
            }
        except ValueError:
            _logger.warning(
                "Credential %s does not hold readable JSON", credential.display_name
            )
            return {}

    def _wa_store_secret(self, key, value) -> None:
        self.check_singleton()
        if value is False or value is None:
            return
        credential = self.credential_id.sudo()
        if not credential:
            credential = (
                self.env["credential.credential"]
                .sudo()
                .create(
                    {
                        "name": self.env._(
                            "WhatsApp: %s", self.name or self.account_uid or self.id
                        ),
                        "category_id": self.env.ref(
                            "credential.credential_category_custom"
                        ).id,
                        "company_id": (
                            self.allowed_company_ids[:1] or self.env.company
                        ).id,
                    }
                )
            )
            self.credential_id = credential.id
        values = self._wa_credential_values()
        if values.get(key) == value:
            return
        values[key] = value
        credential.credential_data = json_dumps(values)
        if key != "webhook_verify_token":
            self._wa_mint_missing_webhook_verify_tokens()

    def _compute_templates_count(self) -> None:
        counts = dict(
            self.env["whatsapp.template"]._read_group(
                [("wa_account_id", "in", self.ids)],
                ["wa_account_id"],
                ["__count"],
            )
        )
        for tmpl in self:
            tmpl.templates_count = counts.get(tmpl, 0)

    def button_sync_whatsapp_account_templates(self) -> dict:
        self.check_singleton()
        try:
            response = WhatsAppApi(self)._get_all_template(fetch_all=True)
            wa_phone_number = WhatsAppApi(self)._get_phone_number(self.phone_uid)
            if wa_phone_number:
                self.phone_number = wa_phone_number
        except WhatsAppError as err:
            raise ValidationError(str(err)) from err

        WhatsappTemplate = self.env["whatsapp.template"]
        existing_tmpls = WhatsappTemplate.with_context(active_test=False).search(
            [("wa_account_id", "=", self.id)]
        )
        existing_tmpl_by_id = {t.wa_template_uid: t for t in existing_tmpls}
        template_update_count = 0
        template_create_count = 0
        if response.get("data"):
            create_vals = []
            for template in response["data"]:
                existing_tmpl = existing_tmpl_by_id.get(template["id"])
                if existing_tmpl:
                    template_update_count += 1
                    existing_tmpl._update_template_from_response(template)
                else:
                    template_create_count += 1
                    create_vals.append(
                        WhatsappTemplate._create_template_from_response(template, self)
                    )
            WhatsappTemplate.create(create_vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Templates synchronized!"),
                "type": "success",
                "message": self.env._(
                    "%(create_count)s were created, %(update_count)s were updated",
                    create_count=template_create_count,
                    update_count=template_update_count,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def button_test_connection(self) -> dict:
        self.check_singleton()
        wa_api = WhatsAppApi(self)
        try:
            wa_api._test_connection()
            wa_phone_number = wa_api._get_phone_number(self.phone_uid)
            if wa_phone_number:
                self.phone_number = wa_phone_number
        except WhatsAppError as e:
            raise UserError(str(e)) from e
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Credentials look good!"),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_debug(self):
        self.check_singleton()
        previous_debug_state = self.debug_logging
        self.debug_logging = True
        return (
            {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Warning"),
                    "type": "warning",
                    "message": self.env._(
                        "Enabling WhatsApp debug stops medias (pictures, videos, pdf, ...) from being received."
                    ),
                },
            }
            if not previous_debug_state
            else None
        )

    def action_stop_debug(self) -> None:
        self.check_singleton()
        self.debug_logging = False

    def action_view_templates(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Templates Of %(account_name)s", account_name=self.name),
            "view_mode": "list,form",
            "res_model": "whatsapp.template",
            "domain": [("wa_account_id", "=", self.id)],
            "type": "ir.actions.act_window",
            "context": {"default_wa_account_id": self.id},
        }

    def _add_ir_log(self, name, message, func="") -> None:
        self.check_singleton()
        self.env.flush_all()
        db_name = self.env.cr.dbname
        try:
            db_registry = Registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env["ir.logging"].create(
                    {
                        "dbname": db_name,
                        "func": func,
                        "level": "DEBUG",
                        "line": "",
                        "message": message,
                        "name": name,
                        "path": f"whatsapp.account,id={self.id},name={self.name}",
                        "type": "server",
                    }
                )
        except psycopg.Error:
            pass

    def _find_active_channel(
        self, sender_mobile_formatted, sender_name=False, create_if_not_found=False
    ):
        self.check_singleton()
        whatsapp_message = (
            self.env["whatsapp.message"]
            .sudo()
            .search(
                [
                    ("mobile_number_formatted", "=", sender_mobile_formatted),
                    ("wa_account_id", "=", self.id),
                    ("wa_template_id", "!=", False),
                    ("state", "not in", ["outgoing", "error", "cancel"]),
                ],
                limit=1,
                order="id desc",
            )
        )
        return (
            self.env["discuss.channel"]
            .sudo()
            ._get_whatsapp_channel(
                whatsapp_number=sender_mobile_formatted or "",
                wa_account_id=self,
                sender_name=sender_name,
                create_if_not_found=create_if_not_found,
                related_message=whatsapp_message.mail_message_id,
            )
        )

    def _on_button_reply(self, parent_whatsapp_message, message) -> None:
        pass

    def _process_messages(self, value) -> None:
        if "messages" not in value and value.get("whatsapp_business_api_data", {}).get(
            "messages"
        ):
            value = value["whatsapp_business_api_data"]

        wa_api = WhatsAppApi(self)

        for messages in value.get("messages", []):
            parent_msg_id = False
            parent_id = False
            parent_whatsapp_message = self.env["whatsapp.message"]
            channel = False
            sender_name = value.get("contacts", [{}])[0].get("profile", {}).get("name")
            sender_mobile = messages["from"]
            message_type = messages["type"]
            if "context" in messages and messages["context"].get("id"):
                parent_whatsapp_message = (
                    self.env["whatsapp.message"]
                    .sudo()
                    .search([("msg_uid", "=", messages["context"]["id"])])
                )
                if parent_whatsapp_message:
                    parent_msg_id = parent_whatsapp_message.id
                    parent_id = parent_whatsapp_message.mail_message_id
                if parent_id:
                    channel = (
                        self.env["discuss.channel"]
                        .sudo()
                        .search([("message_ids", "in", parent_id.id)], limit=1)
                    )

            if not channel:
                channel = self._find_active_channel(
                    sender_mobile, sender_name=sender_name, create_if_not_found=True
                )
            kwargs = {
                "message_type": "whatsapp_message",
                "author_id": channel.whatsapp_partner_id.id,
                "parent_msg_id": parent_msg_id,
                "subtype_xmlid": "mail.mt_comment",
                "parent_id": parent_id.id if parent_id else None,
            }
            if message_type == "text":
                kwargs["body"] = plaintext2html(messages["text"]["body"])
            elif message_type == "button":
                kwargs["body"] = messages["button"]["text"]
                self._on_button_reply(parent_whatsapp_message, messages)
            elif message_type in ("document", "image", "audio", "video", "sticker"):
                filename = messages[message_type].get("filename")
                is_voice = messages[message_type].get("voice")
                mime_type = messages[message_type].get("mime_type")
                caption = messages[message_type].get("caption")
                datas = wa_api._get_whatsapp_document(messages[message_type]["id"])
                if not filename:
                    extension = mimetypes.guess_extension(mime_type) or ""
                    filename = message_type + extension
                kwargs["attachments"] = [(filename, datas, {"voice": is_voice})]
                if caption:
                    kwargs["body"] = plaintext2html(caption)
            elif message_type == "location":
                url = Markup(
                    "https://maps.google.com/maps?q={latitude},{longitude}"
                ).format(
                    latitude=messages["location"]["latitude"],
                    longitude=messages["location"]["longitude"],
                )
                body = Markup(
                    '<a target="_blank" href="{url}"> <i class="fa-solid fa-location-dot"/> {location_string} </a>'
                ).format(url=url, location_string=self.env._("Location"))
                if messages["location"].get("name"):
                    body += Markup("<br/>{location_name}").format(
                        location_name=messages["location"]["name"]
                    )
                if messages["location"].get("address"):
                    body += Markup("<br/>{location_address}").format(
                        location_address=messages["location"]["address"]
                    )
                kwargs["body"] = body
            elif message_type == "contacts":
                body = ""
                for contact in messages["contacts"]:
                    body += Markup(
                        "<i class='fa-solid fa-address-book'/> {contact_name} <br/>"
                    ).format(
                        contact_name=contact.get("name", {}).get("formatted_name", "")
                    )
                    for phone in contact.get("phones"):
                        body += Markup("{phone_type}: {phone_number}<br/>").format(
                            phone_type=phone.get("type"),
                            phone_number=phone.get("phone"),
                        )
                kwargs["body"] = body
            elif message_type == "reaction":
                msg_uid = messages["reaction"].get("message_id")
                whatsapp_message = (
                    self.env["whatsapp.message"]
                    .sudo()
                    .search([("msg_uid", "=", msg_uid)])
                )
                if whatsapp_message:
                    partner_id = channel.whatsapp_partner_id
                    emoji = messages["reaction"].get("emoji")
                    whatsapp_message.mail_message_id._post_whatsapp_reaction(
                        reaction_content=emoji, partner_id=partner_id
                    )
                    continue
            else:
                _logger.warning("Unsupported whatsapp message type: %s", messages)
                continue
            channel.message_post(whatsapp_inbound_msg_uid=messages["id"], **kwargs)
