import logging

from markupsafe import Markup
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class Webhook(http.Controller):
    @http.route(
        "/whatsapp/webhook/",
        methods=["POST"],
        type="http",
        auth="receiver",
        receiver="whatsapp.account:_receiver_for_webhook",
        receiver_event="whatsapp_webhook",
        csrf=False,
        save_session=False,
        typed=True,
    )
    def webhookpost(self, **kwargs):
        admission = request.admission
        data = admission.json()
        for entry in data["entry"]:
            account_id = entry["id"]
            accounts = (
                request.env["whatsapp.account"]
                .sudo()
                .search([("account_uid", "=", account_id)])
            )
            if account_id != admission.subject.account_uid and not (
                accounts._webhook_signer(
                    dict(request.httprequest.headers), admission.body
                )
            ):
                raise Forbidden

            for changes in entry.get("changes", []):
                value = changes["value"]
                phone_number_id = value.get("metadata", {}).get("phone_number_id", {})
                if not phone_number_id:
                    phone_number_id = value.get("whatsapp_business_api_data", {}).get(
                        "phone_number_id", {}
                    )
                if phone_number_id:
                    wa_account_id = (
                        request.env["whatsapp.account"]
                        .sudo()
                        .search(
                            [
                                ("phone_uid", "=", phone_number_id),
                                ("account_uid", "=", account_id),
                            ]
                        )
                    )
                    if wa_account_id:
                        if changes["field"] == "messages":
                            request.env["whatsapp.message"]._process_statuses(value)
                            wa_account_id._process_messages(value)
                    else:
                        _logger.warning(
                            "There is no phone configured for this whatsapp webhook : %s ",
                            data,
                        )

                if value.get("message_template_id"):
                    template = (
                        request.env["whatsapp.template"]
                        .sudo()
                        .with_context(active_test=False)
                        .search(
                            [("wa_template_uid", "=", value["message_template_id"])]
                        )
                    )
                    if template:
                        if changes["field"] == "message_template_status_update":
                            template.write({"status": value["event"].lower()})
                            if value["event"].lower() == "rejected":
                                body = request.env._("Your Template has been rejected.")
                                description = value.get("other_info", {}).get(
                                    "description"
                                ) or value.get("reason")
                                if description:
                                    body += Markup("<br/>") + request.env._(
                                        "Reason : %s", description
                                    )
                                template.message_post(body=body)
                            continue
                        if changes["field"] == "message_template_quality_update":
                            new_quality_score = value["new_quality_score"].lower()
                            new_quality_score = {"unknown": "none"}.get(
                                new_quality_score, new_quality_score
                            )
                            template.write({"quality": new_quality_score})
                            continue
                        if changes["field"] == "template_category_update":
                            template.write(
                                {"template_type": value["new_category"].lower()}
                            )
                            continue
                        _logger.warning("Unknown Template webhook : %s ", value)
                    else:
                        _logger.warning(
                            "No Template found for this webhook : %s ", value
                        )

    @http.route(
        "/whatsapp/webhook/",
        methods=["GET"],
        type="http",
        auth="receiver",
        receiver="whatsapp.account:_receiver_for_webhook_verification",
        receiver_event="whatsapp_verification",
        csrf=False,
        save_session=False,
        typed=True,
    )
    def webhookget(self, **kwargs):
        return request.prepare_response(request.admission.extra["challenge"])
