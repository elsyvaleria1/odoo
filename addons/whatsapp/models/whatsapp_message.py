import logging
import re
from datetime import timedelta

from markupsafe import Markup

from odoo import Command, api, fields, models, modules
from odoo.exceptions import UserError, ValidationError
from odoo.libs.documents import canonical_mimetypes
from odoo.tools import frozendict, groupby, html2plaintext

from odoo.addons.phone_validation.tools import phone_validation
from odoo.addons.whatsapp.tools import phone_validation as wa_phone_validation
from odoo.addons.whatsapp.tools.bounced_codes import BOUNCED_ERROR_CODES
from odoo.addons.whatsapp.tools.retryable_codes import WHATSAPP_RETRYABLE_ERROR_CODES
from odoo.addons.whatsapp.tools.whatsapp_api import WhatsAppApi
from odoo.addons.whatsapp.tools.whatsapp_exception import WhatsAppError

_logger = logging.getLogger(__name__)


class WhatsappMessage(models.Model):
    _name = "whatsapp.message"
    _description = "WhatsApp Messages"
    _order = "id desc"
    _rec_name = "mobile_number"

    _SUPPORTED_ATTACHMENT_TYPE = {
        "audio": ("audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"),
        "document": (
            "text/plain",
            *canonical_mimetypes("pdf", "ppt", "doc", "xls", "docx", "pptx", "xlsx"),
        ),
        "image": ("image/jpeg", "image/png"),
        "video": ("video/mp4",),
    }
    _ACTIVE_THRESHOLD_DAYS = 15

    mobile_number = fields.Char(string="Sent To")
    mobile_number_formatted = fields.Char(
        compute="_compute_mobile_number_formatted",
        store=True,
        readonly=False,
    )
    message_type = fields.Selection(
        selection=[("outbound", "Outbound"), ("inbound", "Inbound")],
        default="outbound",
    )
    state = fields.Selection(
        selection=[
            ("outgoing", "In Queue"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
            ("replied", "Replied"),
            ("received", "Received"),
            ("error", "Failed"),
            (
                "bounced",
                "Bounced",
            ),
            ("cancel", "Cancelled"),
        ],
        default="outgoing",
    )
    failure_type = fields.Selection(
        selection=[
            ("account", "Account Error"),
            ("blacklisted", "Blacklisted Phone Number"),
            ("network", "Network Error"),
            ("outdated_channel", "The channel is no longer active"),
            ("phone_invalid", "Wrong Number Format"),
            ("template", "Template Quality Rating Too Low"),
            ("unknown", "Unknown Error"),
            ("whatsapp_recoverable", "Identified Error"),
            ("whatsapp_unrecoverable", "Other Technical Error"),
        ]
    )
    failure_reason = fields.Char(help="Usually an error message from Whatsapp")
    free_text_json = fields.Json(string="Free Text Template Parameters")
    wa_template_id = fields.Many2one(comodel_name="whatsapp.template")
    msg_uid = fields.Char(string="WhatsApp Message ID")
    wa_account_id = fields.Many2one(
        comodel_name="whatsapp.account",
        string="WhatsApp Business Account",
    )
    parent_id = fields.Many2one(
        comodel_name="whatsapp.message",
        string="Response To",
        index="btree_not_null",
        ondelete="set null",
    )

    mail_message_id = fields.Many2one(
        comodel_name="mail.message",
        index=True,
    )
    body = fields.Html(
        related="mail_message_id.body",
        string="Body",
        related_sudo=False,
    )

    _unique_msg_uid = models.Constraint(
        "unique(msg_uid)",
        "Each whatsapp message should correspond to a single message uuid.",
    )

    @api.depends("mobile_number")
    def _compute_mobile_number_formatted(self) -> None:
        for message in self:
            recipient_partner = (
                message.mail_message_id.partner_ids[0]
                if message.mail_message_id.partner_ids
                else self.env["res.partner"]
            )
            country = recipient_partner.country_id or self.env.company.country_id
            formatted = wa_phone_validation.wa_phone_format(
                country,
                number=message.mobile_number,
                country=country,
                force_format="WHATSAPP",
                raise_exception=False,
            )
            message.mobile_number_formatted = formatted or ""

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages:
            body = html2plaintext(message.body)
            if message.message_type == "inbound" and message.mobile_number_formatted:
                body_message = re.findall(r"([a-zA-Z]+)", body)
                message_string = "".join(i.lower() for i in body_message)
                try:
                    if message_string in self._get_opt_out_message():
                        self.env["phone.blacklist"].sudo().add(
                            number=wa_phone_validation.wa_phone_format_for_blacklist(
                                message.mobile_number_formatted
                            ),
                            message=self.env._(
                                "User has been opt out of receiving WhatsApp messages"
                            ),
                        )
                    else:
                        self.env["phone.blacklist"].sudo().remove(
                            number=wa_phone_validation.wa_phone_format_for_blacklist(
                                message.mobile_number_formatted
                            ),
                            message=self.env._(
                                "User has opted in to receiving WhatsApp messages"
                            ),
                        )
                except UserError:
                    _logger.warning(
                        "Whatsapp: impossible to change opt-in status of %s (formatted as %s) as it is not a valid number (whatsapp.message-%s)",
                        message.mobile_number,
                        message.mobile_number_formatted,
                        message.id,
                    )
        return messages

    @api.autovacuum
    def _gc_whatsapp_messages(self) -> None:

        domain = self._get_domain_whatsapp_gc()
        self.env["whatsapp.message"].search(domain).unlink()

    def _get_domain_whatsapp_gc(self):
        date_threshold = fields.Datetime.now() - timedelta(
            days=self.env["whatsapp.message"]._ACTIVE_THRESHOLD_DAYS
        )
        return [
            ("create_date", "<", date_threshold),
            ("state", "not in", ["outgoing", "error", "cancel"]),
        ]

    def _get_formatted_number(self, sanitized_number, country_code) -> str:
        mobile_number_parse = phone_validation.phone_parse(
            sanitized_number, country_code
        )
        return (
            f"{mobile_number_parse.country_code}{mobile_number_parse.national_number}"
        )

    @api.model
    def _get_opt_out_message(self) -> list:
        return ["stop", "unsubscribe", "stop promotions"]

    def button_resend(self) -> None:
        if self.filtered(lambda rec: rec.state != "error"):
            raise UserError(
                self.env._("You can not resend message which is not in failed state.")
            )
        self._resend_failed()

    def button_cancel_send(self) -> None:
        if self.filtered(lambda rec: rec.state != "outgoing"):
            raise UserError(self.env._("You can not cancel message which is in queue."))
        self.state = "cancel"

    def _resend_failed(self) -> None:
        retryable_messages = self.filtered(
            lambda msg: (
                msg.state == "error" and msg.failure_type != "whatsapp_unrecoverable"
            )
        )

        discuss_messages = retryable_messages.filtered(
            lambda msg: msg.mail_message_id.model == "discuss.channel"
        )
        discuss_channel_ids = discuss_messages.mail_message_id.mapped("res_id")
        valid_discuss_channels = (
            self.env["discuss.channel"]
            .browse(discuss_channel_ids)
            .exists()
            .filtered(
                lambda channel: (
                    channel.whatsapp_channel_valid_until
                    and channel.whatsapp_channel_valid_until >= fields.Datetime.now()
                )
            )
        )
        cancelled_discuss_messages = discuss_messages.filtered(
            lambda msg: msg.mail_message_id.res_id not in valid_discuss_channels.ids
        )
        retryable_messages -= cancelled_discuss_messages

        cancelled_discuss_messages.write(
            {"state": "cancel", "failure_type": "outdated_channel"}
        )
        retryable_messages.write(
            {"state": "outgoing", "failure_type": False, "failure_reason": False}
        )
        self.env["ir.cron"]._trigger_ref("whatsapp.ir_cron_send_whatsapp_queue")

    def _send_cron(self) -> None:
        records = self.search(
            [
                ("state", "=", "outgoing"),
            ],
            order="wa_template_id",
            limit=500,
        )
        records._send_message(with_commit=not modules.module.current_test)
        if len(records) == 500:
            self.env["ir.cron"]._trigger_ref("whatsapp.ir_cron_send_whatsapp_queue")

    def _send(self, force_send_by_cron=False):
        if len(self) <= 1 and not force_send_by_cron:
            self._send_message()
        else:
            self.env["ir.cron"]._trigger_ref("whatsapp.ir_cron_send_whatsapp_queue")

    def _send_message(self, with_commit=False):
        message_to_api = {}
        for account, messages in groupby(self, lambda msg: msg.wa_account_id):
            if not account:
                messages = self.env["whatsapp.message"].concat(*messages)
                messages.write(
                    {
                        "failure_type": "unknown",
                        "failure_reason": "Missing whatsapp account for message.",
                        "state": "error",
                    }
                )
                self -= messages
                continue
            wa_api = WhatsAppApi(account)
            for message in messages:
                message_to_api[message] = wa_api

        sent_message_vals = set()
        for whatsapp_message in self:
            wa_api = message_to_api[whatsapp_message]
            if whatsapp_message.create_uid._is_internal():
                whatsapp_message = whatsapp_message.with_user(
                    whatsapp_message.create_uid
                )
            if whatsapp_message.state != "outgoing":
                _logger.info(
                    "Message state in %s state so it will not sent.",
                    whatsapp_message.state,
                )
                continue
            is_duplicate = False
            msg_uid = False
            try:
                parent_message_id = False
                body = html2plaintext(whatsapp_message.body, include_references=False)
                number = whatsapp_message.mobile_number_formatted
                if not number:
                    raise WhatsAppError(failure_type="phone_invalid")
                blacklist_number = wa_phone_validation.wa_phone_format_for_blacklist(
                    number
                )
                if (
                    self.env["phone.blacklist"]
                    .sudo()
                    .search_count(
                        [("number", "ilike", blacklist_number), ("active", "=", True)],
                        limit=1,
                    )
                ):
                    raise WhatsAppError(failure_type="blacklisted")

                if template := whatsapp_message.wa_template_id:
                    message_type = "template"
                    if (
                        whatsapp_message.wa_template_id.status != "approved"
                        or whatsapp_message.wa_template_id.quality == "red"
                    ):
                        raise WhatsAppError(failure_type="template")
                    whatsapp_message.message_type = "outbound"
                    if (
                        whatsapp_message.mail_message_id.model
                        != whatsapp_message.wa_template_id.model
                    ):
                        raise WhatsAppError(failure_type="template")

                    RecordModel = self.env[
                        whatsapp_message.mail_message_id.model
                    ].with_user(whatsapp_message.env.user)
                    from_record = RecordModel.browse(
                        whatsapp_message.mail_message_id.res_id
                    )

                    if (
                        whatsapp_message.wa_template_id.report_id
                        and whatsapp_message.wa_template_id.header_type == "document"
                        and whatsapp_message.mail_message_id.attachment_ids
                    ):
                        whatsapp_message.mail_message_id.attachment_ids.unlink()

                    send_vals, attachment = (
                        whatsapp_message.wa_template_id._prepare_send_template_data(
                            record=from_record,
                            whatsapp_message=whatsapp_message,
                        )
                    )
                    if not template.report_id:
                        send_vals_without_attachments = dict(send_vals)
                        if template.header_type in ("image", "video", "document"):
                            components = [
                                component_vals
                                for component_vals in send_vals["components"]
                                if component_vals["type"] != "header"
                            ]
                            send_vals_without_attachments["components"] = components
                        unique_message_vals = (
                            number,
                            frozendict(send_vals_without_attachments),
                        )
                        if unique_message_vals not in sent_message_vals:
                            sent_message_vals.add(unique_message_vals)
                        else:
                            is_duplicate = True
                    if (
                        attachment
                        and attachment
                        not in whatsapp_message.mail_message_id.attachment_ids
                    ):
                        cloned_attachment = attachment.copy(
                            {
                                "res_model": whatsapp_message.mail_message_id.model,
                                "res_id": whatsapp_message.mail_message_id.res_id,
                            }
                        )
                        whatsapp_message.mail_message_id.attachment_ids = [
                            Command.link(cloned_attachment.id)
                        ]
                elif whatsapp_message.mail_message_id.attachment_ids:
                    attachment_vals = whatsapp_message._prepare_attachment_vals(
                        whatsapp_message.mail_message_id.attachment_ids[0],
                        wa_account_id=whatsapp_message.wa_account_id,
                    )
                    message_type = attachment_vals.get("type")
                    send_vals = attachment_vals.get(message_type)
                    if body:
                        send_vals["caption"] = body
                else:
                    message_type = "text"
                    send_vals = {
                        "preview_url": True,
                        "body": body,
                    }
                if (
                    whatsapp_message.mail_message_id
                    and whatsapp_message.mail_message_id.parent_id
                ):
                    parent_id = (
                        whatsapp_message.mail_message_id.parent_id.wa_message_ids
                    )
                    if parent_id:
                        parent_message_id = parent_id[0].msg_uid
                if not is_duplicate:
                    msg_uid = wa_api._send_whatsapp(
                        number=number,
                        message_type=message_type,
                        send_vals=send_vals,
                        parent_message_id=parent_message_id,
                    )
            except WhatsAppError as we:
                whatsapp_message._handle_error(
                    whatsapp_error_code=we.error_code,
                    error_message=we.error_message,
                    failure_type=we.failure_type,
                )
            except (UserError, ValidationError) as e:
                whatsapp_message._handle_error(
                    failure_type="unknown", error_message=str(e)
                )
            else:
                if is_duplicate:
                    whatsapp_message.state = "cancel"
                elif whatsapp_message.state == "outgoing":
                    if not msg_uid:
                        whatsapp_message._handle_error(failure_type="unknown")
                    else:
                        if (
                            message_type == "template"
                            and whatsapp_message.wa_template_id.model
                            != "discuss.channel"
                        ):
                            whatsapp_message._post_message_in_active_channel()
                        whatsapp_message.write({"state": "sent", "msg_uid": msg_uid})
                if with_commit:
                    self.env["ir.cron"]._commit_progress(processed=1)

    def _handle_error(
        self, failure_type=False, whatsapp_error_code=False, error_message=False
    ):
        self.check_singleton()
        state = "error"
        if whatsapp_error_code:
            if whatsapp_error_code in WHATSAPP_RETRYABLE_ERROR_CODES:
                failure_type = "whatsapp_recoverable"
            else:
                failure_type = "whatsapp_unrecoverable"
        if not failure_type:
            failure_type = "unknown"
        if whatsapp_error_code in BOUNCED_ERROR_CODES:
            state = "bounced"
        self.write(
            {
                "failure_type": failure_type,
                "failure_reason": error_message,
                "state": state,
            }
        )

    def _post_message_in_active_channel(self) -> None:
        self.check_singleton()
        if not self.wa_template_id:
            return
        channel = self.wa_account_id._find_active_channel(self.mobile_number_formatted)
        if not channel:
            return

        if channel.is_member:
            body = self.body
            message_type = "comment"
        else:
            if self.mail_message_id.model and self.mail_message_id.res_id:
                record_name = self.mail_message_id.record_name
                url = f"{self.get_base_url()}/odoo/{self.mail_message_id.model}/{self.mail_message_id.res_id}"
                record_link = Markup("<a target='_blank' href='%s'>%s</a>") % (
                    url,
                    record_name,
                )
            else:
                record_link = self.env._("another document")
            body = Markup(
                self.env._(
                    "A new template was sent on %(record_link)s.<br>"
                    "Future replies will be transferred to a new chat."
                )
            ) % {"record_link": record_link}
            message_type = "notification"
        channel.sudo().message_post(
            body=body,
            message_type=message_type,
            subtype_xmlid="mail.mt_comment",
        )

    @api.model
    def _prepare_attachment_vals(self, attachment, wa_account_id):
        whatsapp_media_type = next(
            (
                media_type
                for media_type, mimetypes in self._SUPPORTED_ATTACHMENT_TYPE.items()
                if attachment.mimetype in mimetypes
            ),
            False,
        )

        if not whatsapp_media_type:
            raise WhatsAppError(
                self.env._(
                    "Attachment mimetype is not supported by WhatsApp: %s.",
                    attachment.mimetype,
                )
            )
        wa_api = WhatsAppApi(wa_account_id)
        whatsapp_media_uid = wa_api._upload_whatsapp_document(attachment)

        vals = {
            "type": whatsapp_media_type,
            whatsapp_media_type: {"id": whatsapp_media_uid},
        }

        if whatsapp_media_type == "document":
            vals[whatsapp_media_type]["filename"] = attachment.name

        return vals

    def _process_statuses(self, value):
        mapping = {"failed": "error", "cancelled": "cancel"}
        processed_message_ids = set()

        for statuses in value.get("statuses", []):
            whatsapp_message = (
                self.env["whatsapp.message"]
                .sudo()
                .search([("msg_uid", "=", statuses["id"])])
            )
            if whatsapp_message:
                whatsapp_message.state = mapping.get(
                    statuses["status"], statuses["status"]
                )
                processed_message_ids.add(whatsapp_message.id)
                whatsapp_message._update_message_fetched_seen()
                if statuses["status"] == "failed":
                    error = statuses["errors"][0] if statuses.get("errors") else None
                    if error:
                        whatsapp_message._handle_error(
                            whatsapp_error_code=error["code"],
                            error_message=f"{error['code']} : {error['title']}",
                        )
        return (
            self.env["whatsapp.message"]
            .browse(sorted(processed_message_ids, reverse=True))
            .sudo()
        )

    def _update_message_fetched_seen(self) -> None:
        self.check_singleton()
        if self.mail_message_id.model != "discuss.channel":
            return
        channel = self.env["discuss.channel"].browse(self.mail_message_id.res_id)
        channel_member = channel.channel_member_ids.filtered(
            lambda cm: cm.partner_id == channel.whatsapp_partner_id
        )
        if not channel_member:
            return
        channel_member = channel_member[0]
        if self.state == "read":
            channel_member._mark_message_read(self.mail_message_id)
        elif self.state == "delivered":
            if channel_member.fetched_message_id.id >= self.mail_message_id.id:
                return
            channel_member.write({"fetched_message_id": self.mail_message_id.id})
            channel._bus_send(
                "discuss.channel.member/fetched",
                {
                    "channel_id": channel.id,
                    "id": channel_member.id,
                    "last_message_id": self.mail_message_id.id,
                    "partner_id": channel.whatsapp_partner_id.id,
                },
            )
