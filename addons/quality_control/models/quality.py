import random
from datetime import datetime
from math import sqrt
from typing import Self

from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, SQL, float_round

_debug = DebugLog(__name__)


class QualityPoint(models.Model):
    _name = "quality.point"
    _inherit = ["quality.point", "mixin.recurrence.interval"]
    _rec_names_search = ["name", "title"]

    failure_message = fields.Html()
    measure_on = fields.Selection(
        selection=[
            ("operation", "Operation"),
            ("product", "Product"),
            ("move_line", "Quantity"),
        ],
        string="Control per",
        default="product",
        required=True,
        tracking=True,
        help="""Operation = One quality check is requested at the operation level.
                  Product = A quality check is requested per product.
                 Quantity = A quality check is requested for each new product quantity registered, with partial quantity checks also possible.""",
    )
    measure_frequency_type = fields.Selection(
        selection=[
            ("all", "All"),
            ("random", "Randomly"),
            ("periodical", "Periodically"),
            ("on_demand", "On-demand"),
        ],
        string="Control Frequency",
        default="all",
        required=True,
        tracking=True,
    )
    measure_frequency_value = fields.Float(
        string="Percentage",
        tracking=True,
        help="The probability of each quality check being generated",
    )
    repeat_interval = fields.Integer(tracking=True)
    repeat_unit = fields.Selection(
        default="day",
        tracking=True,
    )
    is_lot_tested_fractionally = fields.Boolean(
        string="Lot Tested Fractionally",
        compute="_compute_is_lot_tested_fractionally",
        help="Determines if only a fraction of the lot should be tested",
    )
    testing_percentage_within_lot = fields.Float(
        default=100,
        tracking=True,
        help="Defines the percentage within a lot that should be tested",
    )
    norm = fields.Float(
        digits="Quality Tests",
        tracking=True,
    )
    tolerance_min = fields.Float(
        string="Min Tolerance",
        digits="Quality Tests",
        tracking=True,
    )
    tolerance_max = fields.Float(
        string="Max Tolerance",
        digits="Quality Tests",
        tracking=True,
    )
    norm_unit = fields.Char(
        default=lambda self: "mm",
        tracking=True,
    )
    average = fields.Float(compute="_compute_standard_deviation_and_average")
    standard_deviation = fields.Float(compute="_compute_standard_deviation_and_average")
    spreadsheet_template_id = fields.Many2one(
        comodel_name="quality.spreadsheet.template",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    spreadsheet_check_cell = fields.Char(
        related="spreadsheet_template_id.check_cell",
        readonly=False,
    )

    @api.depends("name", "title")
    def _compute_display_name(self):
        for point in self:
            point.display_name = (
                f"{point.name} - {point.title}" if point.title else point.name
            )

    @api.depends("testing_percentage_within_lot")
    def _compute_is_lot_tested_fractionally(self) -> None:
        for point in self:
            point.is_lot_tested_fractionally = point.testing_percentage_within_lot < 100

    @api.depends("test_type", "check_ids.quality_state", "check_ids.measure")
    def _compute_standard_deviation_and_average(self) -> None:
        _debug.perf.count("quality_spc_stats_compute", points=self)
        self.filtered(lambda point: point.test_type == "measure").check_ids.fetch(
            ["quality_state", "measure"]
        )
        for point in self:
            if point.test_type != "measure":
                point.average = 0
                point.standard_deviation = 0
                continue
            mean = 0.0
            s = 0.0
            n = 0
            for check in point.check_ids:
                if check.quality_state == "none":
                    continue
                n += 1
                delta = check.measure - mean
                mean += delta / n
                delta2 = check.measure - mean
                s += delta * delta2

            if n > 1:
                point.average = mean
                point.standard_deviation = sqrt(s / (n - 1))
            elif n == 1:
                point.average = mean
                point.standard_deviation = 0.0
            else:
                point.average = 0.0
                point.standard_deviation = 0.0

    @api.onchange("norm")
    def onchange_norm(self) -> None:
        if not self.tolerance_max:
            self.tolerance_max = self.norm

    def check_execute_now(self):
        _debug.pipeline("quality_check_execute_now", points=self)
        self.check_singleton()
        if self.measure_frequency_type == "all":
            return True
        elif self.measure_frequency_type == "random":
            return random.random() < self.measure_frequency_value / 100.0
        elif self.measure_frequency_type == "periodical":
            date_previous = datetime.today() - self._get_recurrence_delta()
            has_checks = bool(
                self.env["quality.check"].search_count(
                    [
                        ("point_id", "=", self.id),
                        (
                            "create_date",
                            ">=",
                            date_previous.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        ),
                    ],
                    limit=1,
                )
            )
            return not has_checks
        return super().check_execute_now()

    def _is_check_execution_sampled(self) -> bool:
        _debug.logic("quality_check_sampled", points=self)
        self.check_singleton()
        return (
            self.measure_frequency_type == "random"
            or super()._is_check_execution_sampled()
        )

    def action_see_quality_checks(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_main"
        )
        action["domain"] = [("point_id", "=", self.id)]
        action["context"] = {
            "default_company_id": self.company_id.id,
            "default_point_id": self.id,
        }
        return action

    def action_view_spc_control(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_spc"
        )
        if self.test_type == "measure":
            action["context"] = {
                "group_by": ["name", "point_id"],
                "graph_measure": ["measure"],
                "graph_mode": "line",
            }
        action["domain"] = [("point_id", "=", self.id), ("quality_state", "!=", "none")]
        return action

    def _prepare_check_vals_list(
        self, products, company_id, existing_checks=False
    ) -> list[ValuesType]:
        _debug.pipeline("quality_check_values_build", points=self, products=products)
        point_values = []
        existing_keys = {
            (check.point_id.id, check.team_id.id, check.product_id.id)
            for check in existing_checks or ()
        }

        for point in self:
            if not point.check_execute_now():
                continue
            point_products = point.product_ids

            if point.product_category_ids:
                point_product_from_categories = self.env["product.product"].search(
                    [
                        ("categ_id", "child_of", point.product_category_ids.ids),
                        ("id", "in", products.ids),
                    ]
                )
                point_products |= point_product_from_categories

            if not point.product_ids and not point.product_category_ids:
                point_products |= products

            for product in point_products:
                if product not in products:
                    continue
                point_key = (point.id, point.team_id.id, product.id)
                if point_key in existing_keys:
                    continue
                point_values.append(point._prepare_check_vals(product, company_id))
                existing_keys.add(point_key)

        return point_values

    def _prepare_check_vals(
        self, product: models.BaseModel, company_id: int
    ) -> ValuesType:
        self.check_singleton()
        return {
            "point_id": self.id,
            "measure_on": self.measure_on,
            "team_id": self.team_id.id,
            "product_id": product.id,
            "company_id": company_id,
        }

    @api.model
    def _get_domain_quality_points(
        self, product_ids, picking_type_id, measure_on=False, on_demand=False
    ):
        _debug.logic("quality_points_domain", points=self)
        domain = Domain("picking_type_ids", "in", picking_type_id.ids)
        domain_in_products_or_categs = Domain(
            "product_ids", "in", product_ids.ids
        ) | Domain("product_category_ids", "parent_of", product_ids.categ_id.ids)
        domain_no_products_and_categs = Domain("product_ids", "=", False) & Domain(
            "product_category_ids", "=", False
        )
        domain &= domain_in_products_or_categs | domain_no_products_and_categs
        if measure_on:
            domain &= Domain("measure_on", "=", measure_on)
        domain &= Domain(
            "measure_frequency_type", "=" if on_demand else "!=", "on_demand"
        )
        return domain


class QualityCheck(models.Model):
    _inherit = "quality.check"

    product_id = fields.Many2one(
        compute="_compute_product_id",
        store=True,
        readonly=False,
    )

    trace_ids = fields.Many2many(
        compute="_compute_trace_ids",
        store=True,
        readonly=False,
    )

    failure_message = fields.Html(
        related="point_id.failure_message",
        readonly=True,
    )
    measure = fields.Float(
        digits="Quality Tests",
        default=0.0,
        tracking=True,
    )
    measure_success = fields.Selection(
        selection=[("none", "No measure"), ("pass", "Pass"), ("fail", "Fail")],
        compute="_compute_measure_success",
        store=True,
        readonly=True,
    )
    tolerance_min = fields.Float(
        related="point_id.tolerance_min",
        string="Min Tolerance",
        readonly=True,
    )
    tolerance_max = fields.Float(
        related="point_id.tolerance_max",
        string="Max Tolerance",
        readonly=True,
    )
    warning_message = fields.Text(compute="_compute_warning_message")
    norm_unit = fields.Char(
        related="point_id.norm_unit",
        readonly=True,
    )
    qty_to_test = fields.Float(
        string="Quantity to Test",
        digits="Product Unit",
        compute="_compute_qty_to_test",
        help="Quantity of product to test within the lot",
    )
    qty_tested = fields.Float(
        string="Quantity Tested",
        digits="Product Unit",
        help="Quantity of product tested within the lot",
    )
    measure_on = fields.Selection(
        selection=[
            ("operation", "Operation"),
            ("product", "Product"),
            ("move_line", "Quantity"),
        ],
        string="Control per",
        compute="_compute_measure_on",
        default="product",
        store=True,
        required=True,
        help="""Operation = One quality check is requested at the operation level.
                  Product = A quality check is requested per product.
                 Quantity = A quality check is requested for each new product quantity registered, with partial quantity checks also possible.""",
    )
    move_line_id = fields.Many2one(
        comodel_name="stock.move.line",
        string="Stock Move Line",
        index="btree_not_null",
        check_company=True,
        help="In case of Quality Check by Quantity, Move Line on which the Quality Check applies",
    )
    lot_name = fields.Char(
        related="move_line_id.lot_name",
        string="Lot/Serial Number Name",
    )
    trace_line_id = fields.Many2one(
        comodel_name="product.trace",
        compute="_compute_trace_line_id",
        store=True,
    )
    qty_line = fields.Float(
        string="Quantity",
        compute="_compute_qty_line",
    )
    qty_passed = fields.Float(
        string="Quantity Passed",
        compute="_compute_qty_passed",
        store=True,
        help="Quantity of product that passed the quality check",
    )
    qty_failed = fields.Float(
        string="Quantity Failed",
        compute="_compute_qty_failed",
        store=True,
        help="Quantity of product that failed the quality check",
    )
    uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unit",
    )
    show_lot_text = fields.Boolean(compute="_compute_show_lot_text")
    is_lot_tested_fractionally = fields.Boolean(
        related="point_id.is_lot_tested_fractionally"
    )
    testing_percentage_within_lot = fields.Float(
        related="point_id.testing_percentage_within_lot"
    )
    spreadsheet_id = fields.Many2one(
        comodel_name="quality.check.spreadsheet",
        domain="[('company_id', 'in', company_ids)]",
    )
    allowed_product_ids = fields.Many2many(
        comodel_name="product.product",
        compute="_compute_allowed_product_ids",
    )
    spreadsheet_template_id = fields.Many2one(
        comodel_name="quality.spreadsheet.template",
        compute="_compute_spreadsheet_template_id",
        store=True,
        copy=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    point_spreadsheet_template_id = fields.Many2one(
        related="point_id.spreadsheet_template_id",
        string="Control Point Spreadsheet Template",
    )
    hide_picking_id = fields.Boolean(compute="_compute_hide_source_documents")

    @api.depends("picking_id")
    def _compute_allowed_product_ids(self) -> None:
        _debug.perf.count("quality_allowed_products_compute", checks=self)
        for check in self:
            check.allowed_product_ids = False
            if check.picking_id:
                check.allowed_product_ids = check.picking_id.move_ids.product_id

    def _source_document_fields(self):
        return ("picking_id",)

    @api.depends(lambda self: self._source_document_fields())
    def _compute_hide_source_documents(self) -> None:
        names = self._source_document_fields()
        for check in self:
            anchors = {name for name in names if check[name]}
            for name in names:
                check[f"hide_{name}"] = bool(anchors - {name}) and name not in anchors

    @api.depends("point_id")
    def _compute_spreadsheet_template_id(self) -> None:
        for check in self:
            if check.point_id and check.point_id.spreadsheet_template_id:
                check.spreadsheet_template_id = check.point_id.spreadsheet_template_id
            else:
                check.spreadsheet_template_id = False

    @api.depends("point_id")
    def _compute_measure_on(self) -> None:
        for check in self:
            if check.point_id:
                check.measure_on = check.point_id.measure_on
            else:
                check.measure_on = "product"

    @api.depends("measure_on")
    def _compute_product_id(self) -> None:
        for check in self:
            if check.measure_on == "operation":
                check.product_id = False

    @api.depends("measure_on")
    def _compute_trace_ids(self) -> None:
        for check in self:
            if check.measure_on == "operation":
                check.trace_ids = False

    @api.depends("measure_success")
    def _compute_warning_message(self) -> None:
        _debug.perf.count("quality_check_warning_compute", checks=self)
        for rec in self:
            if rec.measure_success == "fail":
                rec.warning_message = self.env._(
                    "You measured %(measure).2f %(unit)s and it should be between %(tolerance_min).2f and %(tolerance_max).2f %(unit)s.",
                    measure=rec.measure,
                    unit=rec.norm_unit,
                    tolerance_min=rec.point_id.tolerance_min,
                    tolerance_max=rec.point_id.tolerance_max,
                )
            else:
                rec.warning_message = ""

    @api.depends("move_line_id.quantity")
    def _compute_qty_line(self):
        for qc in self:
            qc.qty_line = qc.move_line_id.quantity

    @api.depends("qty_line", "quality_state")
    def _compute_qty_passed(self) -> None:
        for qc in self:
            if qc.quality_state == "pass":
                qc.qty_passed = qc.qty_line
            else:
                qc.qty_passed = 0

    @api.depends("qty_line", "quality_state")
    def _compute_qty_failed(self) -> None:
        for qc in self:
            if qc.quality_state == "fail":
                qc.qty_failed = qc.qty_line
            else:
                qc.qty_failed = 0

    @api.depends("move_line_id.trace_id")
    def _compute_trace_line_id(self) -> None:
        for qc in self:
            qc.trace_line_id = qc.move_line_id.trace_id
            if qc.trace_line_id and qc._update_lot_from_lot_line():
                qc.trace_ids = qc.trace_line_id

    def _update_lot_from_lot_line(self) -> bool:
        return True

    @api.depends(
        "measure",
        "point_id.test_type",
        "point_id.tolerance_min",
        "point_id.tolerance_max",
    )
    def _compute_measure_success(self) -> None:
        for rec in self:
            if rec.point_id.test_type != "measure":
                rec.measure_success = "none"
            elif (
                rec.point_id.tolerance_min <= rec.measure <= rec.point_id.tolerance_max
            ):
                rec.measure_success = "pass"
            else:
                rec.measure_success = "fail"

    @api.depends(
        "qty_line",
        "testing_percentage_within_lot",
        "is_lot_tested_fractionally",
        "product_id.uom_id",
    )
    def _compute_qty_to_test(self) -> None:
        for qc in self:
            if qc.is_lot_tested_fractionally:
                qc.qty_to_test = float_round(
                    qc.qty_line * qc.testing_percentage_within_lot / 100,
                    precision_rounding=qc.product_id.uom_id.rounding or 0.01,
                    rounding_method="UP",
                )
            else:
                qc.qty_to_test = qc.qty_line

    @api.depends("trace_line_id", "move_line_id")
    def _compute_show_lot_text(self) -> None:
        for qc in self:
            if qc.trace_line_id or not qc.move_line_id:
                qc.show_lot_text = False
            else:
                qc.show_lot_text = True

    @api.constrains("product_id", "picking_id")
    def _check_allowed_product_ids_with_picking(self) -> None:
        for check in self:
            if (
                check.product_id
                and check.picking_id
                and check.product_id not in check.picking_id.move_ids.product_id
            ):
                raise ValidationError(
                    self.env._(
                        "%(product_name)s is not in Picking %(picking_name)s",
                        product_name=check.product_id.name,
                        picking_name=check.picking_id.name,
                    )
                )

    def _is_pass_fail_applicable(self) -> bool:
        if self.test_type in ["passfail", "measure"]:
            return True
        return super()._is_pass_fail_applicable()

    def _check_to_unlink(self):
        return True

    def _measure_passes(self) -> bool:
        self.check_singleton()
        return self.measure_success != "fail"

    def do_measure(self):
        self.check_singleton()
        if self._measure_passes():
            return self.do_pass()
        else:
            return self.do_fail()

    def do_alert(self) -> dict:
        self.check_singleton()
        alert = self.env["quality.alert"].create(
            {
                "check_id": self.id,
                "product_id": self.product_id.id,
                "product_tmpl_id": self.product_id.product_tmpl_id.id,
                "trace_ids": self.trace_ids.ids,
                "user_id": self.user_id.id,
                "team_id": self.team_id.id,
                "company_id": self.company_id.id,
            }
        )
        return {
            "name": self.env._("Quality Alert"),
            "type": "ir.actions.act_window",
            "res_model": "quality.alert",
            "views": [
                (self.env.ref("quality_control.quality_alert_view_form").id, "form")
            ],
            "res_id": alert.id,
            "context": {"default_check_id": self.id},
        }

    def action_see_alerts(self):
        self.check_singleton()
        if len(self.alert_ids) == 1:
            return {
                "name": self.env._("Quality Alert"),
                "type": "ir.actions.act_window",
                "res_model": "quality.alert",
                "views": [
                    (self.env.ref("quality_control.quality_alert_view_form").id, "form")
                ],
                "res_id": self.alert_ids.ids[0],
                "context": {"default_check_id": self.id},
            }
        else:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "quality_control.quality_alert_action_check"
            )
            action["domain"] = [("id", "in", self.alert_ids.ids)]
            action["context"] = dict(self.env.context, default_check_id=self.id)
            return action

    def action_view_quality_check_wizard(self, current_check_id=None):
        check_ids = sorted(self.ids)
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.action_quality_check_wizard"
        )
        check_id = self.browse(current_check_id or check_ids[0])
        action["name"] = check_id._get_check_action_name()
        action["context"] = self.env.context.copy()
        action["context"].update(
            {
                "default_check_ids": check_ids,
                "default_current_check_id": check_id.id,
                "default_qty_tested": check_id.qty_to_test,
            }
        )
        return action

    def action_view_spreadsheet(self):
        if not self.spreadsheet_id:
            self.spreadsheet_id = self._create_spreadsheet_from_template()
        action = self.spreadsheet_id.action_view_spreadsheet()
        action["params"]["check_id"] = self.id
        return action

    def _create_spreadsheet_from_template(self):
        self.check_singleton()
        spreadsheet_template = self.spreadsheet_template_id
        spreadsheet = self.env["quality.check.spreadsheet"].create(
            {
                "name": spreadsheet_template.name,
                "spreadsheet_data": spreadsheet_template.spreadsheet_data,
                "check_cell": self.point_id.spreadsheet_check_cell,
            }
        )
        spreadsheet.spreadsheet_snapshot = spreadsheet_template.spreadsheet_snapshot
        spreadsheet_template._copy_revisions_to(spreadsheet)
        return spreadsheet

    def unlink(self):
        self.spreadsheet_id.unlink()
        return super().unlink()

    def _can_move_to_failure_location(self) -> bool:
        self.check_singleton()
        return bool(self.quality_state == "fail" and self.picking_id)

    def _move_to_failure_location(self, failure_location_id, failed_qty=None) -> None:
        for check in self:
            if not check._can_move_to_failure_location():
                continue
            match check.measure_on:
                case "operation":
                    if failure_location_id:
                        check._move_to_failure_location_operation(failure_location_id)
                case "product":
                    if failure_location_id:
                        check._move_to_failure_location_product(failure_location_id)
                case "move_line":
                    check._move_to_failure_location_move_line(
                        failure_location_id, failed_qty
                    )

    def _move_to_failure_location_move_line(
        self, failure_location_id, failed_qty
    ) -> None:
        self.check_singleton()
        if not failed_qty:
            self.do_pass()
            return
        move_line = self.move_line_id
        move = move_line.move_id
        dest_location = failure_location_id or move_line.location_dest_id.id
        failed_qty = min(failed_qty, move_line.quantity)
        self.failure_location_id = dest_location
        if failed_qty == move_line.quantity:
            move_line.location_dest_id = dest_location
            if move_line.quantity == move.quantity:
                move.location_dest_id = dest_location
            else:
                move.with_context(do_not_unreserve=True).product_uom_qty -= failed_qty
                move.copy(
                    {
                        "location_dest_id": dest_location,
                        "move_orig_ids": move.move_orig_ids,
                        "product_uom_qty": failed_qty,
                        "state": "assigned",
                        "move_line_ids": [Command.link(move_line.id)],
                    }
                )
            return
        move.with_context(do_not_unreserve=True).product_uom_qty -= failed_qty
        move_line.quantity -= failed_qty
        failed_move_line = move_line.with_context(
            default_check_ids=None, no_checks=True
        ).copy(
            {
                "location_dest_id": dest_location,
                "quantity": failed_qty,
            }
        )
        move.copy(
            {
                "location_dest_id": dest_location,
                "move_orig_ids": move.move_orig_ids,
                "product_uom_qty": failed_qty,
                "state": "assigned",
                "move_line_ids": [Command.link(failed_move_line.id)],
            }
        )
        new_check = self.create(failed_move_line._prepare_check_vals(self.point_id))
        self.move_line_id = failed_move_line
        new_check.move_line_id = move_line
        new_check.qty_tested = 0
        new_check.do_pass()

    def _move_to_failure_location_operation(self, failure_location_id):
        self.check_singleton()
        if self.picking_id and failure_location_id:
            self.picking_id.move_ids.location_dest_id = failure_location_id
            self.failure_location_id = failure_location_id

    def _move_to_failure_location_product(self, failure_location_id):
        self.check_singleton()
        if self.picking_id and failure_location_id:
            self.picking_id.move_ids.filtered(
                lambda m: m.product_id == self.product_id
            ).location_dest_id = failure_location_id
        self.failure_location_id = failure_location_id

    def _get_check_action_name(self):
        self.check_singleton()
        action_name = self.title or "Quality Check"
        if self.product_id:
            action_name += " : %s" % self.product_id.display_name
        if self.qty_line and self.uom_id:
            action_name += " - %s %s" % (self.qty_line, self.uom_id.name)
        if self.lot_name or self.trace_line_id or self.trace_ids:
            action_name += " - %s" % (
                self.lot_name or self.trace_line_id.name or self.trace_ids.name
            )
        return action_name

    def _is_to_do(self, checkable_products, check_picked=False) -> bool:
        self.check_singleton()
        if self.quality_state != "none":
            return False
        if self.measure_on != "operation":
            if self.product_id not in checkable_products:
                return False
            if self.move_line_id:
                if not self.move_line_id._is_checkable(check_picked):
                    return False
        if self.move_line_id and self.product_id.tracking in ["serial", "lot"]:
            if (
                self.move_line_id.picking_type_use_create_lots
                or self.move_line_id.picking_type_use_existing_lots
            ):
                if not self.move_line_id.trace_id and not self.move_line_id.lot_name:
                    return False
        return True

    def _filtered_to_do(self, checkable_products, check_picked=False) -> Self:
        return self.filtered(
            lambda check: check._is_to_do(checkable_products, check_picked=check_picked)
        )


class QualityAlert(models.Model):
    _inherit = "quality.alert"

    title = fields.Char()

    def action_see_check(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Quality Check"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "quality.check",
            "target": "current",
            "res_id": self.check_id.id,
        }

    @api.depends("name", "title")
    def _compute_display_name(self):
        for record in self:
            record.display_name = " - ".join(
                part for part in (record.name, record.title) if part
            )

    @api.model
    def name_create(self, name):
        record = self.create(
            {
                "title": name,
            }
        )
        return record.id, record.display_name

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        custom_values = dict(custom_values or {})
        custom_values["name"] = self.env["ir.sequence"].next_by_code(
            "quality.alert"
        ) or self.env._("New")
        if msg_dict.get("subject"):
            custom_values["title"] = msg_dict["subject"]
        if msg_dict.get("body"):
            custom_values["description"] = msg_dict["body"]
        return super().message_new(msg_dict, custom_values)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    quality_control_point_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )
    quality_pass_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )
    quality_fail_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )

    @api.depends("product_variant_ids")
    def _compute_quality_check_qty(self) -> None:
        point_variants_by_tmpl = {
            product_tmpl: product_tmpl.with_context(
                active_test=product_tmpl.active
            ).product_variant_ids
            for product_tmpl in self
        }
        checks_by_product = self.product_variant_ids._count_quality_checks_by_product()
        points_by_product = (
            self.env["product.product"]
            .union(*point_variants_by_tmpl.values())
            ._count_quality_points_by_product()
        )
        for product_tmpl in self:
            fail = pass_ = 0
            for variant in product_tmpl.product_variant_ids:
                variant_fail, variant_pass = checks_by_product.get(variant.id, (0, 0))
                fail += variant_fail
                pass_ += variant_pass
            product_tmpl.quality_fail_qty = fail
            product_tmpl.quality_pass_qty = pass_
            product_tmpl.quality_control_point_qty = sum(
                points_by_product.get(variant.id, 0)
                for variant in point_variants_by_tmpl[product_tmpl]
            )

    def action_view_quality_control_points(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_point_action"
        )
        action["context"] = dict(
            self.env.context, default_product_ids=self.product_variant_ids.ids
        )

        action["views"] = [
            (self.env.ref("quality.quality_point_view_tree").id, "list"),
            (False, "form"),
            (False, "kanban"),
        ]
        domain_in_products_or_categs = [
            "|",
            ("product_ids", "in", self.product_variant_ids.ids),
            ("product_category_ids", "parent_of", self.categ_id.ids),
        ]
        domain_no_products_and_categs = [
            ("product_ids", "=", False),
            ("product_category_ids", "=", False),
        ]
        action["domain"] = Domain.OR(
            [domain_in_products_or_categs, domain_no_products_and_categs]
        )
        return action

    def action_see_quality_checks(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_main"
        )
        action["context"] = dict(
            self.env.context,
            default_product_id=self.product_variant_id.id,
            create=False,
        )
        action["domain"] = [
            "|",
            ("product_id", "in", self.product_variant_ids.ids),
            "&",
            ("measure_on", "=", "operation"),
            ("picking_id.move_ids.product_tmpl_id", "=", self.id),
        ]
        return action


class ProductProduct(models.Model):
    _inherit = "product.product"

    quality_control_point_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )
    quality_pass_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )
    quality_fail_qty = fields.Integer(
        compute="_compute_quality_check_qty",
        groups="quality.group_quality_user",
    )

    quality_check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="product_id",
        string="Quality Checks",
    )

    @api.depends("quality_check_ids.quality_state")
    @api.depends_context("company")
    def _compute_quality_check_qty(self) -> None:
        checks_by_product = self._count_quality_checks_by_product()
        points_by_product = self._count_quality_points_by_product()
        for product in self:
            product.quality_fail_qty, product.quality_pass_qty = checks_by_product.get(
                product.id, (0, 0)
            )
            product.quality_control_point_qty = points_by_product.get(product.id, 0)

    def _count_quality_checks(self) -> tuple:
        quality_fail_qty = quality_pass_qty = 0
        for fail, passed in self._count_quality_checks_by_product().values():
            quality_fail_qty += fail
            quality_pass_qty += passed
        return quality_fail_qty, quality_pass_qty

    def _count_quality_checks_by_product(self):
        counts = dict.fromkeys(self.ids, (0, 0))
        if not self:
            return counts
        company_domain = [
            ("company_id", "=", self.env.company.id),
            ("quality_state", "in", ("pass", "fail")),
        ]
        named = self.env["quality.check"]._read_group(
            [*company_domain, ("product_id", "in", self.ids)],
            ["product_id", "quality_state"],
            ["__count"],
        )
        by_operation = self.env["quality.check"]._read_group(
            [
                *company_domain,
                ("measure_on", "=", "operation"),
                ("product_id", "=", False),
                ("picking_id.move_ids.product_id", "in", self.ids),
            ],
            ["picking_id"],
            ["quality_state:array_agg"],
        )
        for product, quality_state, count in named:
            fail, passed = counts[product.id]
            counts[product.id] = (
                (fail + count, passed)
                if quality_state == "fail"
                else (fail, passed + count)
            )
        for picking, states in by_operation:
            for product in picking.move_ids.product_id & self:
                fail, passed = counts[product.id]
                counts[product.id] = (
                    fail + states.count("fail"),
                    passed + states.count("pass"),
                )
        return counts

    def _count_quality_points(self):
        return sum(self._count_quality_points_by_product().values())

    def _count_quality_points_by_product(self):
        counts = dict.fromkeys(self.ids, 0)
        if not self:
            return counts
        query = self.env["quality.point"]._search(
            [("company_id", "=", self.env.company.id)]
        )

        additional_where_clause = self._additional_quality_point_where_clause()
        if additional_where_clause:
            query.add_where(additional_where_clause)

        categ_ids_by_product = {
            product.id: [
                int(parent_id)
                for parent_id in (product.categ_id.parent_path or "").split("/")[:-1]
            ]
            for product in self
        }
        product_ids_by_categ = {}
        for product_id, categ_ids in categ_ids_by_product.items():
            for categ_id in categ_ids:
                product_ids_by_categ.setdefault(categ_id, []).append(product_id)

        query.add_where(
            SQL(
                """(
                    -- QP names one of these products
                    EXISTS (SELECT 1 FROM product_product_quality_point_rel rel WHERE rel.quality_point_id = quality_point.id AND rel.product_product_id = ANY(%s))
                    -- or one of their categories, or an ancestor of one
                    OR EXISTS (SELECT 1 FROM product_category_quality_point_rel rel WHERE rel.quality_point_id = quality_point.id AND rel.product_category_id = ANY(%s))
                    -- or names neither, and so applies to everything
                    OR (
                        NOT EXISTS (SELECT 1 FROM product_product_quality_point_rel rel WHERE rel.quality_point_id = quality_point.id)
                        AND NOT EXISTS (SELECT 1 FROM product_category_quality_point_rel rel WHERE rel.quality_point_id = quality_point.id)
                    )
                )
            """,
                self.ids,
                list(product_ids_by_categ),
            )
        )
        rows = self.env.execute_query(
            SQL(
                """SELECT quality_point.id,
                      ARRAY(SELECT rel.product_product_id FROM product_product_quality_point_rel rel WHERE rel.quality_point_id = quality_point.id),
                      ARRAY(SELECT rel.product_category_id FROM product_category_quality_point_rel rel WHERE rel.quality_point_id = quality_point.id)
                 FROM %s WHERE %s""",
                query.from_clause,
                query.where_clause or SQL("TRUE"),
            )
        )
        for _point_id, point_product_ids, point_categ_ids in rows:
            if not point_product_ids and not point_categ_ids:
                matched = set(counts)
            else:
                matched = set(point_product_ids) & set(counts)
                for categ_id in point_categ_ids:
                    matched.update(product_ids_by_categ.get(categ_id, ()))
            for product_id in matched:
                counts[product_id] += 1
        return counts

    def action_view_quality_control_points(self):
        self.check_singleton()
        action = self.product_tmpl_id.action_view_quality_control_points()
        action["context"].update(default_product_ids=self.ids)

        domain_in_products_or_categs = [
            "|",
            ("product_ids", "in", self.ids),
            ("product_category_ids", "parent_of", self.categ_id.ids),
        ]
        domain_no_products_and_categs = [
            ("product_ids", "=", False),
            ("product_category_ids", "=", False),
        ]
        action["domain"] = Domain.OR(
            [domain_in_products_or_categs, domain_no_products_and_categs]
        )
        return action

    def action_see_quality_checks(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.quality_check_action_main"
        )
        action["context"] = dict(
            self.env.context, default_product_id=self.id, create=False
        )
        action["domain"] = [
            "|",
            ("product_id", "=", self.id),
            "&",
            ("measure_on", "=", "operation"),
            ("picking_id.move_ids.product_id", "=", self.id),
        ]
        return action

    def _additional_quality_point_where_clause(self) -> SQL:
        return SQL()
