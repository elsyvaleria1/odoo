from itertools import batched

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class RepairOrder(models.Model):
    _inherit = "repair.order"

    quality_check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="repair_id",
        string="Checks",
    )
    quality_check_todo = fields.Boolean(compute="_compute_quality_check_counts")
    quality_check_fail = fields.Boolean(compute="_compute_quality_check_counts")
    quality_alert_ids = fields.One2many(
        comodel_name="quality.alert",
        inverse_name="repair_id",
        string="Alerts",
    )
    quality_alert_count = fields.Integer(compute="_compute_quality_alert_count")

    @api.depends("quality_check_ids.quality_state")
    def _compute_quality_check_counts(self) -> None:
        _debug.perf.count("repair_quality_counts_compute", repairs=self)
        data = self.env["quality.check"]._read_group(
            domain=[
                ("repair_id", "in", self.ids),
                ("quality_state", "in", ["none", "fail"]),
            ],
            groupby=["repair_id", "quality_state"],
            aggregates=["__count"],
        )
        mapped_data = {
            (repair.id, quality_state): count for repair, quality_state, count in data
        }
        for repair in self:
            repair.quality_check_fail = bool(mapped_data.get((repair.id, "fail")))
            repair.quality_check_todo = bool(mapped_data.get((repair.id, "none")))

    @api.depends("quality_alert_ids")
    def _compute_quality_alert_count(self) -> None:
        data = self.env["quality.alert"]._read_group(
            domain=[("repair_id", "in", self.ids)],
            groupby=["repair_id"],
            aggregates=["__count"],
        )
        mapped_data = {repair.id: count for repair, count in data}
        for repair in self:
            repair.quality_alert_count = mapped_data.get(repair.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        _debug.lifecycle("repair_quality_create", count=len(vals_list))
        res = super().create(vals_list)
        # One call for the batch: `_create_quality_checks_for_repair` is
        # multi-record and its point searches do not depend on the repair.
        res.filtered(
            lambda repair: repair.state in ("confirmed", "under_repair")
        )._create_quality_checks_for_repair(["product", "operation"])
        return res

    def write(self, vals):
        _debug.lifecycle("repair_quality_write", repairs=self, fields=len(vals))
        res = super().write(vals)
        started = self.filtered(
            lambda repair: repair.state in ("confirmed", "under_repair")
        )
        if not started:
            return res
        if "product_id" in vals:
            started.quality_check_ids.filtered(
                lambda c: c.measure_on == "product"
            ).unlink()
            started._create_quality_checks_for_repair(["product"])
        elif "trace_id" in vals:
            # Only the per-product checks carry a lot -- that is what
            # `_create_quality_checks_for_repair` fills in.  (`False` on an
            # m2m does clear it, measured; `Command.clear()` only says so.)
            product_checks = started.quality_check_ids.filtered(
                lambda c: c.measure_on == "product"
            )
            product_checks.trace_ids = (
                [Command.set([vals["trace_id"]])]
                if vals["trace_id"]
                else [Command.clear()]
            )
        return res

    def _create_quality_checks_for_repair(self, measures) -> None:
        _debug.pipeline("repair_quality_checks_create", repairs=self)
        if not self:
            return
        check_vals_list = []
        for measure in measures:
            points = (
                self.env["quality.point"]
                .sudo()
                .search(
                    self.env["quality.point"]._get_domain_quality_points(
                        self.product_id, self.picking_type_id, measure_on=measure
                    )
                )
            )
            for repair in self:
                domain = self.env["quality.point"]._get_domain_quality_points(
                    repair.product_id, repair.picking_type_id, measure_on=measure
                )
                for point_ids_batch in batched(points.ids, 10_000, strict=False):
                    # avoid fetching large HTML fields like `note` & `reason`
                    fields_to_fetch = [
                        "measure_frequency_type",
                        "repeat_unit",
                        "repeat_interval",
                        "measure_frequency_value",
                        "team_id",
                    ]
                    if len(self) > 1:
                        repair_points = (
                            self.env["quality.point"]
                            .sudo()
                            .search_fetch(
                                domain=Domain.AND(
                                    [[("id", "in", point_ids_batch)], domain]
                                ),
                                field_names=fields_to_fetch,
                            )
                        )
                    else:
                        # No need to find the intersection if there is only 1 repair,
                        # the initial set of points are valid for said repair.
                        repair_points = self.env["quality.point"].browse(
                            point_ids_batch
                        )
                        repair_points.fetch(fields_to_fetch)

                    settled = repair_points._get_execute_now_by_point()
                    check_vals_list.extend(
                        {
                            "point_id": point.id,
                            "team_id": point.team_id.id,
                            "measure_on": measure,
                            "product_id": repair.product_id.id
                            if measure == "product"
                            else False,
                            # `[]`, not `False`: an m2m takes commands.
                            "trace_ids": [Command.link(repair.trace_id.id)]
                            if measure == "product" and repair.trace_id
                            else [],
                            "repair_id": repair.id,
                        }
                        for point in repair_points
                        if point._is_execution_required(settled)
                    )
        self.env["quality.check"].sudo().create(check_vals_list)

    def action_view_quality_checks(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_main"
        )
        action["context"] = self.env.context.copy()
        action["domain"] = [("repair_id", "=", self.id)]
        action["context"].update(
            {
                "search_default_repair_id": [self.id],
                "default_repair_id": self.id,
            }
        )
        return action

    def action_view_quality_alerts(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_alert_action_check"
        )
        action["context"] = {
            "default_product_id": self.product_id.id,
            "default_product_tmpl_id": self.product_id.product_tmpl_id.id,
            "default_repair_id": self.id,
        }
        action["domain"] = [("repair_id", "=", self.id)]
        action["views"] = [(False, "list"), (False, "form")]
        if self.quality_alert_count == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.quality_alert_ids.id
        return action

    def action_check_quality(self):
        _debug.pipeline("repair_quality_check_open", repairs=self)
        self.check_singleton()
        checks = self.quality_check_ids.filtered(lambda x: x.quality_state == "none")
        if checks:
            return checks.action_view_quality_check_wizard()
        return None

    def _action_repair_confirm(self):
        _debug.pipeline("repair_quality_confirm", repairs=self)
        res = super()._action_repair_confirm()
        self._create_quality_checks_for_repair(["product", "operation"])
        return res

    def action_repair_done(self):
        if any(check.quality_state == "none" for check in self.quality_check_ids):
            raise UserError(self.env._("You still need to do the quality checks!"))
        return super().action_repair_done()

    def action_repair_cancel(self):
        res = super().action_repair_cancel()
        self.sudo().mapped("quality_check_ids").filtered(
            lambda c: c.quality_state == "none"
        ).unlink()
        return res
