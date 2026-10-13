from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import RedirectWarning, UserError

VALIDATION_ACTIVITY = "delivery_tracking.mail_activity_type_carrier_validation"


class StockPicking(models.Model):
    """Complete carrier deliveries through normal stock validation."""

    _inherit = "stock.picking"

    carrier_validation_error = fields.Char(
        string="Carrier Delivery Validation Blocked",
        copy=False,
        readonly=True,
        help="Reason the delivered transfer could not be validated automatically. "
        "Correct the issue and refresh tracking, or wait for the next scheduled run.",
    )

    def action_cancel(self):
        result = super().action_cancel()
        cancelled = self.filtered(lambda picking: picking.state == "cancel")
        cancelled.carrier_validation_error = False
        cancelled.activity_unlink([VALIDATION_ACTIVITY])
        return result

    def _action_done(self, *, cancel_backorder=False):
        result = super()._action_done(cancel_backorder=cancel_backorder)
        done = self.filtered(lambda picking: picking.state == "done")
        done.carrier_validation_error = False
        done.activity_feedback(
            [VALIDATION_ACTIVITY],
            feedback=self.env._("The delivered transfer was validated."),
        )
        return result

    def _is_carrier_auto_validation_enabled(self) -> bool:
        self.check_singleton()
        return bool(
            self.picking_type_id.code == "outgoing"
            and self.carrier_id.tracking_provider
            and self.carrier_id in self.picking_type_id.auto_validation_carrier_ids
            and self._get_carrier_tracking_references()
        )

    def _check_carrier_delivery_quantities(self) -> None:
        """Require complete quantities before invoking normal validation."""
        self.check_singleton()
        moves = self.move_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
        )
        if not moves:
            raise UserError(self.env._("The delivered transfer has no open moves."))
        any_picked = any(moves.mapped("picked"))
        for move in moves:
            quantity = move._get_picked_quantity() if move.picked else move.quantity
            if (
                move.product_uom_id.compare(move.quantity, move.product_uom_qty)
                or move.product_uom_id.compare(quantity, move.product_uom_qty)
                or (any_picked and not move.picked and move.product_uom_qty)
            ):
                raise UserError(
                    self.env._(
                        "The quantities for %(product)s do not cover the full demand. "
                        "Check the quantities and picked lines before retrying.",
                        product=move.product_id.display_name,
                    )
                )

    def _complete_carrier_deliveries(self) -> None:
        """Validate eligible deliveries and retain actionable stock errors."""
        for picking in self.try_lock_for_update():
            # A manual validation or guide change may have preceded this lock.
            picking.invalidate_recordset()
            if (
                picking.state != "assigned"
                or not picking._is_carrier_auto_validation_enabled()
                or picking.carrier_tracking_state != "delivered"
                or picking.carrier_tracking_error
            ):
                continue
            details = picking.carrier_tracking_details or {}
            if not all(
                details.get(reference, {}).get("state") == "delivered"
                for reference in picking._get_carrier_tracking_references()
            ):
                continue
            picking.move_ids.invalidate_recordset()
            picking.move_line_ids.invalidate_recordset()
            try:
                # Rolling back a wizard must also undo any automatically picked lines.
                with self.env.cr.savepoint():
                    picking._check_carrier_delivery_quantities()
                    picking.button_validate()
                    if picking.state != "done":
                        raise UserError(
                            self.env._(
                                "Validation requires an additional confirmation. "
                                "Open the transfer and validate it manually."
                            )
                        )
            except (UserError, RedirectWarning) as error:
                reason = str(error.args[0])
                picking.carrier_validation_error = reason
                activity = picking.activity_search([VALIDATION_ACTIVITY])
                note = Markup("<p>%s</p>") % reason
                if activity:
                    activity.write({"note": note})
                else:
                    user = (
                        picking.carrier_id.tracking_notify_user_id
                        or picking.user_id
                        or self.env.user
                    )
                    picking.activity_schedule(
                        VALIDATION_ACTIVITY,
                        summary=self.env._("Delivered: resolve the validation issue"),
                        note=note,
                        user_id=user.id,
                    )
            else:
                picking.message_post(
                    body=self.env._(
                        "Automatically validated after %(carrier)s confirmed delivery "
                        "of all tracking numbers: %(references)s.",
                        carrier=picking.carrier_id.name,
                        references=picking.carrier_tracking_ref,
                    )
                )
