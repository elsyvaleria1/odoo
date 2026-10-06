from odoo import fields, models


class PhoneCall(models.Model):
    _inherit = "phone.call"

    ticket_count = fields.Integer(
        related="partner_id.ticket_count",
        related_sudo=False,
        groups="helpdesk.group_helpdesk_user",
    )
    open_ticket_count = fields.Integer(
        related="partner_id.open_ticket_count",
        related_sudo=False,
        groups="helpdesk.group_helpdesk_user",
    )

    def voip_action_view_helpdesk_ticket(self):
        self.check_singleton()
        if self.ticket_count > 0:
            return self.partner_id.action_view_helpdesk_ticket()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_ticket_action_main_tree"
        )
        action["views"] = [[False, "form"]]
        action.update(
            {
                "context": {
                    "default_partner_phone": self.phone_number,
                    "default_partner_id": self.partner_id.id,
                },
            },
        )
        return action
