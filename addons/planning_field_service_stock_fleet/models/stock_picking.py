from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    planning_slot_id = fields.Many2one(
        comodel_name="planning.slot",
        string="Visit",
        index="btree_not_null",
        copy=False,
        readonly=True,
        ondelete="set null",
        help="The visit on which the goods were handed over.",
    )

    def _register_delivery_failure(self, reason):
        visit = self.planning_slot_id
        super()._register_delivery_failure(reason)
        if visit:
            self.planning_slot_id = False
            visit._with_visit_deliveries_privilege(visit).message_post(
                body=self.env._(
                    "%(picking)s was not delivered: %(reason)s",
                    picking=self.name,
                    reason=reason,
                )
            )

    def _take_off_trip_as_correction(self, reason):
        tied = self.filtered("planning_slot_id")
        visits = {picking: picking.planning_slot_id for picking in tied}
        super()._take_off_trip_as_correction(reason)
        if not tied:
            return
        tied.planning_slot_id = False
        for picking, visit in visits.items():
            visit._with_visit_deliveries_privilege(visit).message_post(
                body=self.env._(
                    "%(picking)s came off the trip as a correction: %(reason)s",
                    picking=picking.name,
                    reason=reason,
                )
            )
