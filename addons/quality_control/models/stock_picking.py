from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import float_is_zero
from odoo.tools.authority_keys import declare_authority_keys
from odoo.tools.misc import OrderedSet

declare_authority_keys("quality_control", "skip_check")

_debug = DebugLog(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="picking_id",
        string="Checks",
    )
    quality_check_todo = fields.Boolean(
        string="Pending checks",
        compute="_compute_check",
        search="_search_quality_check_todo",
    )
    quality_check_fail = fields.Boolean(compute="_compute_check")
    quality_alert_ids = fields.One2many(
        comodel_name="quality.alert",
        inverse_name="picking_id",
        string="Alerts",
    )
    quality_alert_count = fields.Count(count_of="quality_alert_ids")

    @api.depends("check_ids.quality_state")
    def _compute_check(self) -> None:
        # Without the dependency both flags were cached for the whole
        # transaction: a check created or graded afterwards never moved them,
        # and `quality_check_todo` is what the barcode UI and the batch view
        # read to decide whether anything is left to do.
        # Only prefetch needed QC fields to avoid to bloat the cache by fetching other QC data.
        self.check_ids.fetch(["quality_state"])
        for picking in self:
            states = set(picking.check_ids.mapped("quality_state"))
            picking.quality_check_todo = "none" in states
            picking.quality_check_fail = "fail" in states

    def _search_quality_check_todo(self, operator, value):
        if operator != "in":
            return NotImplemented

        domain = [("picking_id", "!=", False), ("quality_state", "=", "none")]
        query_check_picking = self.env["quality.check"]._search(domain)
        return [("id", "in", query_check_picking.subselect("picking_id"))]

    def _checks_to_do(self):
        _debug.logic("picking_checks_to_do", pickings=self)
        check_ids_to_do = OrderedSet()
        for picking in self:
            has_picked = any(picking.move_ids.mapped("picked"))
            if has_picked:
                checkable_lines = picking.move_line_ids.filtered(
                    lambda ml: ml._is_checkable(check_picked=True)
                )
            else:
                checkable_lines = picking.move_line_ids
            checkable_products = checkable_lines.product_id
            # `picking.check_ids`, not `self.check_ids`: every picking used to
            # be offered the whole recordset's checks, so validating two
            # transfers together pulled in a sibling's check whenever *this*
            # picking happened to move the same product.
            checks_to_do = picking.check_ids._filtered_to_do(
                checkable_products, check_picked=has_picked
            )
            check_ids_to_do.update(checks_to_do.ids)
        return self.env["quality.check"].browse(check_ids_to_do)

    def check_quality(self):
        _debug.pipeline("picking_quality_check_open", pickings=self)
        checks = self._checks_to_do()
        if checks:
            return checks.action_view_quality_check_wizard()
        return True

    def _create_backorder(self, backorder_moves=None):
        _debug.pipeline("quality_backorder_create", pickings=self)
        res = super()._create_backorder(backorder_moves=backorder_moves)
        if self.env.context.get("skip_check"):
            return res
        for backorder in res:
            # Do not link the QC of move lines with quantity of 0 in backorder.
            backorder.move_line_ids.filtered(
                lambda ml: (
                    not float_is_zero(
                        ml.quantity, precision_rounding=ml.product_uom_id.rounding
                    )
                )
            ).check_ids.picking_id = backorder
            if backorder.backorder_id.state in ("done", "cancel"):
                backorder.backorder_id.check_ids.filtered(
                    lambda qc: qc.quality_state == "none"
                ).sudo().unlink()
            backorder.move_ids._create_quality_checks()
        return res

    def _action_done(self, **kwargs):
        if self._checks_to_do():
            raise UserError(self.env._("You still need to do the quality checks!"))
        return super()._action_done(**kwargs)

    def _pre_action_done_hook(self, **validate_kwargs):
        _debug.logic("picking_quality_gate", pickings=self)
        res = super()._pre_action_done_hook(**validate_kwargs)
        if res is not True:
            return res
        action = self.with_context(picking_validation=True).check_quality()
        if isinstance(action, dict):
            action["context"].update(
                self._get_validation_resume_defaults(validate_kwargs)
            )
        return action

    def action_cancel(self):
        _debug.lifecycle("quality_picking_cancel", pickings=self)
        res = super().action_cancel()
        self.sudo().mapped("check_ids").filtered(
            lambda x: x.quality_state == "none"
        ).unlink()
        return res

    def action_view_quality_check_picking(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_picking"
        )
        action["context"] = self.env.context.copy()
        action["context"].update(
            {
                "search_default_picking_id": [self.id],
                "default_picking_id": self.id,
                "show_lots_text": self.show_lots_text,
            }
        )
        return action

    def action_view_on_demand_quality_check(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_main"
        )
        action["views"] = [(False, "form")]
        action["context"] = {
            **self.env.context,
            "default_product_id": self.product_id.id
            if len(self.move_ids.ids) == 1
            else False,
            "default_product_tmpl_id": self.move_ids.product_tmpl_id.ids,
            "default_picking_id": self.id,
        }
        return action

    def button_quality_alert(self):
        _debug.lifecycle("quality_alert_open", pickings=self)
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_alert_action_check"
        )
        action["views"] = [(False, "form")]
        action["context"] = {
            "default_product_id": self.product_id.id,
            "default_product_tmpl_id": self.product_id.product_tmpl_id.id,
            "default_picking_id": self.id,
        }
        return action

    def open_quality_alert_picking(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_alert_action_check"
        )
        action["context"] = {
            "default_product_id": self.product_id.id,
            "default_product_tmpl_id": self.product_id.product_tmpl_id.id,
            "default_picking_id": self.id,
        }
        action["domain"] = [("id", "in", self.quality_alert_ids.ids)]
        action["views"] = [(False, "list"), (False, "form")]
        if self.quality_alert_count == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.quality_alert_ids.id
        return action
