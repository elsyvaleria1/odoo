from odoo import models


class WizardMrpProductionProducePartial(models.TransientModel):
    _inherit = "wizard.mrp.production.produce.partial"

    def action_close_mo(self):
        if wo_id := self.env.context.get("workorder_id_to_finish", False):
            always_backorder_mo_ids = self.env.context.get(
                "always_backorder_mo_ids", []
            )
            return self._finish_workorder(
                self.env["mrp.workorder"].browse(wo_id),
                self.env["mrp.production"].browse(always_backorder_mo_ids),
            )
        return super().action_close_mo()

    def action_backorder(self):
        if wo_id := self.env.context.get("workorder_id_to_finish", False):
            always_backorder_mo_ids = self.env.context.get(
                "always_backorder_mo_ids", []
            )
            mo_ids_to_backorder = (
                self.mrp_production_backorder_line_ids.filtered(
                    lambda l: l.to_backorder
                ).mrp_production_id.ids
                + always_backorder_mo_ids
            )
            return self._finish_workorder(
                self.env["mrp.workorder"].browse(wo_id),
                self.env["mrp.production"].browse(mo_ids_to_backorder),
            )
        return super().action_backorder()

    def _finish_workorder(self, workorder_to_finish, productions_to_backorder):

        backorders = (
            productions_to_backorder and productions_to_backorder._split_productions()
        )
        backorders -= productions_to_backorder

        backorders_to_assign = backorders.filtered(
            lambda order: order.picking_type_id.reservation_method == "at_confirm"
        )
        backorders_to_assign.action_assign()

        return workorder_to_finish.post_record_production(backorders)
