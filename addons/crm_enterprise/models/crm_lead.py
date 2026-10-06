import json
import logging

from odoo import api, fields, models
from odoo.libs.json import loads as json_loads
from odoo.libs.web import urljoin as url_join

from odoo.addons.crm_enterprise.tools.business_card_scanner import (
    PROMPT,
    BusinessCardScanner,
)
from odoo.addons.iap.tools import iap_tools

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    days_to_convert = fields.Float(
        compute="_compute_days_to_convert",
        store=True,
    )
    days_exceeding_closing = fields.Float(
        string="Exceeded Closing Days",
        compute="_compute_days_exceeding_closing",
        store=True,
    )

    @api.depends("date_conversion", "create_date")
    def _compute_days_to_convert(self) -> None:
        for lead in self:
            if lead.date_conversion:
                lead.days_to_convert = (
                    fields.Datetime.from_string(lead.date_conversion)
                    - fields.Datetime.from_string(lead.create_date)
                ).days
            else:
                lead.days_to_convert = 0

    @api.depends("date_deadline", "date_closed")
    def _compute_days_exceeding_closing(self) -> None:
        for lead in self:
            if lead.date_closed and lead.date_deadline:
                lead.days_exceeding_closing = (
                    fields.Datetime.from_string(lead.date_deadline)
                    - fields.Datetime.from_string(lead.date_closed)
                ).days
            else:
                lead.days_exceeding_closing = 0

    @api.model
    def _read_business_card(self, attachment):
        return self._read_business_card_by_olg(attachment)

    @api.model
    def _read_business_card_by_olg(self, attachment):
        image_url = (
            f"{attachment.get_base_url()}/web/image/{attachment.id}"
            f"?access_token={attachment.access_token}"
        )
        IrConfigParameter = self.env["ir.config_parameter"].sudo()
        olg_api_endpoint = IrConfigParameter.get_param(
            "html_editor.olg_api_endpoint", "https://olg.api.odoo.com"
        )
        response = iap_tools.iap_jsonrpc(
            url_join(olg_api_endpoint, "/api/olg/1/chat"),
            params={
                "prompt": PROMPT,
                "conversation_history": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ],
                    }
                ],
                "database_id": IrConfigParameter.get_param("database.uuid"),
            },
            timeout=20,
            env=self.env,
            purpose="iap.olg.business_card",
        )
        if response["status"] != "success":
            return {}
        try:
            return json_loads(response["content"])
        except json.JSONDecodeError:
            _logger.warning(
                "IAP returned non-parsable response: %s", response["content"]
            )
            return {}

    def action_ocr_business_cards(self, attachment_ids):
        attachments = self.env["ir.attachment"].browse(attachment_ids)
        card_scanner = BusinessCardScanner(self.env)
        leads = card_scanner.business_cards_to_leads(attachments)

        if not leads:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "sticky": False,
                    "message": self.env._(
                        "The AI agent was not able to generate a lead from the provided image. *sad robot noises* 🤖"
                    ),
                },
            }

        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "crm.crm_lead_opportunities"
        )
        if len(leads) == 1:
            action.update(
                {
                    "views": [[False, "form"]],
                    "view_mode": "form",
                    "res_id": leads[0].id,
                }
            )
        else:
            action.update(
                {
                    "domain": [("id", "in", leads.ids)],
                    "views": [[False, "list"], [False, "kanban"], [False, "form"]],
                    "view_mode": "list,kanban,form",
                }
            )

        return action
