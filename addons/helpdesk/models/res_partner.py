from odoo import fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    ticket_count = fields.Integer(
        string="Tickets",
        compute="_compute_ticket_count",
    )
    sla_ids = fields.Many2many(
        comodel_name="helpdesk.sla",
        relation="helpdesk_sla_res_partner_rel",
        column1="res_partner_id",
        column2="helpdesk_sla_id",
        string="SLA Policies",
        help="SLA Policies that will automatically apply to the tickets submitted by this customer.",
    )

    def _compute_ticket_count(self) -> None:
        all_partners_subquery = self.with_context(active_test=False)._search(
            [("id", "child_of", self.ids)]
        )

        # group tickets by partner, and account for each partner in self
        groups = self.env["helpdesk.ticket"]._read_group(
            [("partner_id", "in", all_partners_subquery)],
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        self.ticket_count = 0
        for partner, count in groups:
            while partner:
                if partner in self:
                    partner.ticket_count += count
                partner = partner.with_context(prefetch_fields=False).parent_id

    def action_view_helpdesk_ticket(self):
        self.check_singleton()
        action = {
            **self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "helpdesk.helpdesk_ticket_action_main_tree"
            ),
            "display_name": self.env._(
                "%(partner_name)s's Tickets", partner_name=self.name
            ),
            "context": {},
        }
        all_child = self.with_context(active_test=False).search(
            [("id", "child_of", self.ids)]
        )
        search_domain = [("partner_id", "in", (self | all_child).ids)]
        if self.ticket_count <= 1:
            ticket_id = self.env["helpdesk.ticket"].search(search_domain, limit=1)
            action["res_id"] = ticket_id.id
            action["views"] = [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type == "form"
            ]
        else:
            action["domain"] = search_domain
            action["views"] = [
                (
                    self.env["ir.model.data"]._xmlid_to_res_id(
                        "helpdesk.helpdesk_tickets_view_tree_res_partner"
                    ),
                    view_type,
                )
                if view_type == "list"
                else (view_id, view_type)
                for view_id, view_type in action["views"]
            ]
        return action

    def write(self, vals):
        if vals.get("company_id"):
            tickets_other_company = self.env["helpdesk.ticket"].search_count(
                [
                    ("partner_id", "in", self.ids),
                    ("company_id", "!=", vals["company_id"]),
                ],
                limit=1,
            )
            if tickets_other_company:
                raise UserError(
                    self.env._(
                        "You cannot update the company of this partner because it would lead to inconsistency with some of its tickets."
                    )
                )
        return super().write(vals)
