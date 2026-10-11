import logging
from typing import TYPE_CHECKING

from urllib3.exceptions import LocationParseError

from odoo import models
from odoo.tools.mail import TEXT_URL_REGEX

if TYPE_CHECKING:
    from odoo.addons.whatsapp.models.whatsapp_template_button import (
        WhatsappTemplateButton,
    )

_logger = logging.getLogger(__name__)


class WhatsappTemplate(models.Model):
    _inherit = "whatsapp.template"

    def _prepare_additional_button_vals(self, button):
        button_url_data = super()._prepare_additional_button_vals(button)
        if "sequence" not in button or button["button_type"] != "url":
            return {}
        btn_before_sync = self.button_ids.filtered(
            lambda x: x.sequence == button.get("sequence")
        )
        if not btn_before_sync:
            return button_url_data

        if btn_before_sync.url_type == "tracked":
            button_url_data["url_type"] = "tracked"
            button_url_data["website_url"] = btn_before_sync.website_url
        return button_url_data

    def _prepare_send_template_data(self, record, whatsapp_message) -> tuple:

        template_vals, attachment = super()._prepare_send_template_data(
            record, whatsapp_message
        )
        campaign_id = (
            whatsapp_message.sudo().marketing_trace_ids.activity_id.campaign_id
        )

        mail_mixin = self.env["mixin.mail.render"]
        if not template_vals.get("components") or not campaign_id:
            return template_vals, attachment

        tracker_values = {
            "campaign_id": campaign_id.utm_campaign_id.id,
        }

        buttons_by_sequence = self.button_ids.grouped("sequence")
        for component in template_vals["components"]:
            if component["type"] == "button" and component["sub_type"] == "url":
                button = buttons_by_sequence.get(
                    component["index"], self.button_ids.browse()
                )
                if button.url_type == "tracked":
                    website_url = button.website_url
                    shortened_link = mail_mixin.sudo()._shorten_links_text(
                        website_url, tracker_values
                    )
                    shortened_link += f"/w/{whatsapp_message.id}"
                    component["parameters"][0]["text"] = shortened_link.replace(
                        self.env["link.tracker"].get_base_url(), ""
                    ).lstrip("/")

        url_template_parameters = [
            parameter
            for component in template_vals["components"]
            if component["type"] == "body"
            for parameter in component["parameters"]
            if parameter["type"] == "text"
            and TEXT_URL_REGEX.match(parameter["text"]) is not None
        ]

        for tmpl_param in url_template_parameters:
            try:
                shortened_link = mail_mixin.sudo()._shorten_links_text(
                    tmpl_param["text"], tracker_values
                )
                shortened_link += f"/w/{whatsapp_message.id}"
            except LocationParseError as e:
                _logger.warning(
                    "Could not shorten link: %s, the error was risen: %s",
                    tmpl_param["text"],
                    e,
                )
                shortened_link = tmpl_param["text"]
            tmpl_param["text"] = shortened_link
        return template_vals, attachment

    def _acquire_url_button_data(
        self, button: WhatsappTemplateButton
    ) -> dict[str, str]:
        button_data = super()._acquire_url_button_data(button)
        if button.url_type == "tracked":
            base_url = self.env["link.tracker"].get_base_url().strip("/")
            button_data.update(
                {"url": base_url + "/{{1}}", "example": base_url + "/???"}
            )
        return button_data
