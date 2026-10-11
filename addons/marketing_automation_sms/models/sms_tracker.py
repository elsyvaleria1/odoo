from odoo import models


class SmsTracker(models.Model):
    _inherit = "sms.tracker"

    def _update_sms_traces(
        self, trace_status, failure_type=False, failure_reason=False
    ):
        traces = super()._update_sms_traces(
            trace_status, failure_type=failure_type, failure_reason=failure_reason
        )
        if traces and trace_status == "bounce":
            for marketing_trace in traces.marketing_trace_id:
                marketing_trace.process_event("sms_bounce")
        return traces
