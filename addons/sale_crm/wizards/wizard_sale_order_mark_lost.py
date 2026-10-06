from odoo import api, fields, models


class WizardSaleOrderMarkLost(models.TransientModel):
    _inherit = "wizard.sale.order.mark.lost"

    opportunity_ids = fields.Many2many(
        comodel_name="crm.lead",
        compute="_compute_opportunity_ids",
    )
    close_opportunities = fields.Boolean(
        string="Mark Opportunities as Lost",
        compute="_compute_close_opportunities",
        store=True,
        readonly=False,
        help="Close the opportunities these quotations belong to, when none of "
        "them keeps another open quotation.",
    )

    @api.depends("order_ids", "outcome")
    def _compute_opportunity_ids(self) -> None:
        for wizard in self:
            wizard.opportunity_ids = (
                wizard._get_opportunities_left_open()
                if wizard.outcome == "lost"
                else False
            )

    @api.depends("opportunity_ids")
    def _compute_close_opportunities(self) -> None:
        for wizard in self:
            wizard.close_opportunities = bool(wizard.opportunity_ids)

    def _get_opportunities_left_open(self):
        return self.order_ids.opportunity_id.filtered(
            lambda lead: (
                lead.active
                and lead.won_status != "won"
                and not (
                    lead.order_ids.filtered(lambda order: order.state == "draft")
                    - self.order_ids._origin
                )
            )
        )

    def action_close(self):
        opportunities = self.opportunity_ids if self.close_opportunities else False
        result = super().action_close()
        if opportunities:
            opportunities.action_set_lost(
                lost_reason_id=self.loss_reason_id.id,
            )
        return result
