from odoo import api, fields, models


class MarketingTrace(models.Model):
    _inherit = "marketing.trace"

    whatsapp_message_id = fields.Many2one(
        comodel_name="whatsapp.message",
        string="Marketing Template",
        index="btree_not_null",
        readonly=False,
    )

    @api.depends("whatsapp_message_id")
    def _compute_links_click_datetime(self) -> None:
        wa_trace = self.filtered(lambda x: x.whatsapp_message_id)
        wa_trace.links_click_datetime = False
        super(MarketingTrace, self - wa_trace)._compute_links_click_datetime()
        for trace in wa_trace:
            trace.links_click_datetime = trace.whatsapp_message_id.links_click_datetime

    def _get_exclusive_events(self):
        return super()._get_exclusive_events() | {"whatsapp_bounced"}

    def _get_event_cancel_messages(self) -> dict:
        return {
            **super()._get_event_cancel_messages(),
            "whatsapp_read": self.env._("Parent Whatsapp message got opened"),
            "whatsapp_replied": self.env._("Parent Whatsapp was replied to"),
            "whatsapp_click": self.env._("Parent Whatsapp message was clicked"),
            "whatsapp_bounced": self.env._("Parent whatsapp was bounced"),
        }
