from odoo import models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _merge_method(self, destination, source) -> dict:
        tickets = destination + source
        status_list = self.env["helpdesk.sla.status"]

        # a status without deadline (stage in "sla_id.exclude_stage_ids") sorts last
        for status in tickets.mapped("sla_status_ids").grouped("sla_id").values():
            status_list += min(status, key=lambda s: (not s.deadline, s.deadline))

        self.env["data_merge.record"]._update_foreign_keys(destination, source)
        destination.update(
            {"sla_status_ids": status_list, "sla_ids": status_list.mapped("sla_id")}
        )
        return {"post_merge": True, "log_chatter": True}
