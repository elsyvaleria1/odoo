from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import ConcurrencyError
from odoo.http import Controller, request, route

from odoo.addons.automation_webhook.models.automation_rule import (
    get_webhook_request_payload,
)
from odoo.addons.integration.tools.admission import Refused


class AutomationRuleController(Controller):
    @route(
        ["/web/hook/<string:webhook_uuid>"],
        type="http",
        auth="receiver",
        receiver="automation.rule:_receiver_for_webhook",
        receiver_event="webhook",
        methods=["GET", "POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def call_webhook_http(self, webhook_uuid: str, **kwargs):
        admission = request.admission
        rule = admission.subject
        data = get_webhook_request_payload()
        try:
            rule._execute_webhook(data, admission)
        except (*PG_RETRY_EXCEPTIONS, ConcurrencyError):
            raise
        except Exception as error:
            raise Refused(
                500, "the webhook's actions failed", "webhook_failed"
            ) from error
        return request.prepare_json_response({"status": "ok"}, status=200)
