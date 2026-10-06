from odoo import fields, models
from odoo.fields import Domain


class WhatsappMessage(models.Model):
    _inherit = "whatsapp.message"

    links_click_datetime = fields.Datetime(
        string="Clicked On",
        help="Stores last click datetime in case of multi clicks.",
    )
    marketing_trace_ids = fields.One2many(
        comodel_name="marketing.trace",
        inverse_name="whatsapp_message_id",
    )

    def set_clicked(self):
        self.write({"links_click_datetime": fields.Datetime.now()})
        for trace in self.marketing_trace_ids:
            trace.process_event("whatsapp_click")
        return self

    def _process_statuses(self, value):
        """Process statuses of whatsapp messages like: 'send', 'delivered' and 'read'."""
        processed_msgs = super()._process_statuses(value)
        status_mapping = {
            "send": "whatsapp_send",
            "delivered": "whatsapp_delivered",
            "read": "whatsapp_read",
        }

        for processed_msg in processed_msgs:
            traces = processed_msg.marketing_trace_ids
            trace_event = status_mapping.get(processed_msg.state, "")
            if trace_event and traces:
                for trace in traces:
                    trace.sudo().process_event(trace_event)

    def _get_domain_whatsapp_gc(self):
        return Domain.AND(
            [
                super()._get_domain_whatsapp_gc(),
                [("marketing_trace_ids", "!=", "False")],
            ]
        )

    def _handle_error(
        self, failure_type=False, whatsapp_error_code=False, error_message=False
    ):
        super()._handle_error(
            failure_type,
            whatsapp_error_code=whatsapp_error_code,
            error_message=error_message,
        )
        traces = self.sudo().marketing_trace_ids
        if not traces:
            return
        traces._settle_line("canceled", message=self.env._("WhatsApp canceled"))
        if self.state == "bounced":
            for trace in traces:
                trace.process_event("whatsapp_bounced")
