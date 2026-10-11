import copy
import logging as logger
import re

from odoo import api, models, tools

from odoo.addons.iap.tools.iap_tools import iap_jsonrpc

_logger = logger.getLogger(__name__)


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        scheduled_date = self._get_notification_scheduled_date(
            kwargs.get("scheduled_date")
        )
        recipients_data = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)

        if not scheduled_date:
            self._notify_thread_by_ocn(message, recipients_data, msg_vals, **kwargs)
        return recipients_data

    def _notify_thread_by_ocn(self, message, recipients_data, msg_vals=False, **kwargs):
        icp_sudo = self.env["ir.config_parameter"].sudo()
        if not icp_sudo.get_param("odoo_ocn.project_id") or not icp_sudo.get_param_bool(
            "mail_mobile.enable_ocn"
        ):
            return

        pids = self._notify_get_recipients_for_extra_notifications(
            message, recipients_data, msg_vals=msg_vals
        )
        if not pids:
            return

        self._notify_by_ocn_send(message, pids, msg_vals=msg_vals, **kwargs)

    def _notify_by_ocn_send(
        self, message, partner_ids, msg_vals=False, **kwargs
    ) -> None:
        if not partner_ids:
            return
        receiver_ids = (
            self.env["res.partner"]
            .sudo()
            .search([("id", "in", partner_ids), ("ocn_token", "!=", False)])
        )
        if receiver_ids:
            endpoint = self.env["res.config.settings"]._get_endpoint()
            payload = self._notify_by_ocn_prepare_payload(
                message,
                receiver_ids,
                msg_vals=msg_vals,
                force_record_name=kwargs.get("force_record_name", False),
            )

            chunks = []
            at_mention_ocn_token_list = []
            identities_ocn_token_list = []
            at_mention_analyser_id_list = self._at_mention_analyser(
                msg_vals["body"] if msg_vals and "body" in msg_vals else message.body
            )
            for receiver_id in receiver_ids:
                if receiver_id.id in at_mention_analyser_id_list:
                    at_mention_ocn_token_list.append(receiver_id.ocn_token)
                else:
                    identities_ocn_token_list.append(receiver_id.ocn_token)

            if identities_ocn_token_list:
                chunks.append(
                    {
                        "ocn_tokens": identities_ocn_token_list,
                        "data": payload,
                    }
                )

            if at_mention_ocn_token_list:
                new_payload = copy.copy(payload)
                new_payload["android_channel_id"] = "AtMention"
                chunks.append(
                    {
                        "ocn_tokens": at_mention_ocn_token_list,
                        "data": new_payload,
                    }
                )

            for chunk in chunks:
                try:
                    iap_jsonrpc(endpoint + "/iap/ocn/send", params=chunk, env=self.env)
                except Exception:
                    _logger.exception(
                        "An error occurred while contacting the ocn server"
                    )

    def _notify_by_ocn_prepare_payload(
        self, message, receiver_ids, msg_vals=False, force_record_name=False
    ):
        msg_vals = msg_vals or {}
        author_id = msg_vals.get("author_id", message.author_id.ids)
        author_name = self.env["res.partner"].browse(author_id).name
        body = msg_vals.get("body", message.body)
        model = msg_vals.get("model", message.model)
        res_id = msg_vals.get("res_id", message.res_id)
        record_name = force_record_name or message.record_name
        subject = msg_vals.get("subject", message.subject)

        payload = {
            "android_channel_id": "Following",
            "author_name": author_name,
            "model": model,
            "res_id": res_id,
            "db_id": self.env["res.config.settings"]._get_ocn_uuid(),
            "subject": record_name or subject,
        }

        payload_length = len(str(payload).encode("utf-8"))
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        if payload_length < 4000:
            payload_body = tools.html2plaintext(body)
            payload_body += self._generate_tracking_message(message)
            payload["body"] = payload_body[: 4000 - payload_length]

        return payload

    @api.model
    def _at_mention_analyser(self, body):
        if isinstance(body, bytes):
            body = body.decode("utf-8")

        at_mention_ids = []
        regex = r"<a[^>]+data-oe-id=[\'\"](?P<id>\d+)[\'\"][^>]+data-oe-model=[\'\"](?P<model>[\w.]+)['\"][^>]?>@[^<]+<\/a>"
        matches = re.finditer(regex, body)

        for match in matches:
            if match.group("model") == "res.partner":
                match_id = match.group("id")
                try:
                    at_mention_ids.append(int(match_id))
                except ValueError, TypeError:
                    _logger.error("Invalid conversion to int: %s", match_id)
        return at_mention_ids
