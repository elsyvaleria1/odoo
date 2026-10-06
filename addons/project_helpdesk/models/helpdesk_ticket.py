from odoo import models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def action_convert_to_task(self) -> dict:
        return {
            "name": self.env._("Convert to Task"),
            "view_mode": "form",
            "res_model": "wizard.helpdesk.ticket.convert.task",
            "views": [(False, "form")],
            "type": "ir.actions.act_window",
            "target": "new",
            "context": {
                **self.env.context,
                "to_convert": self.ids,
                "dialog_size": "medium",
            },
        }
