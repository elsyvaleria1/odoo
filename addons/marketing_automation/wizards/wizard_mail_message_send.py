from odoo import fields, models


class WizardMailMessageSend(models.TransientModel):
    _inherit = "wizard.mail.message.send"

    marketing_activity_id = fields.Many2one(comodel_name="marketing.activity")

    def _prepare_mail_values_mailing_traces(self, mail_values_all):
        """Override method to link mail automation activity with mail statistics"""
        trace_values_all = super()._prepare_mail_values_mailing_traces(mail_values_all)
        if not (
            self.marketing_activity_id
            and self.composition_mode == "mass_mail"
            and (self.mass_mailing_name or self.mass_mailing_id)
        ):
            return trace_values_all

        sent_trace_ids = self.env.context.get("marketing_trace_ids")
        domain = [
            ("activity_id", "=", self.marketing_activity_id.id),
            ("res_id", "in", list(trace_values_all)),
        ]
        if sent_trace_ids:
            domain.append(("id", "in", sent_trace_ids))
        # if somehow several traces match a record, the last one wins the mapping below
        traces = self.env["marketing.trace"].search(domain, order="id ASC")
        traces_mapping = {trace.res_id: trace.id for trace in traces}
        for res_id, trace_values in trace_values_all.items():
            if res_id in traces_mapping:
                trace_values["marketing_trace_id"] = traces_mapping[res_id]
        return trace_values_all
