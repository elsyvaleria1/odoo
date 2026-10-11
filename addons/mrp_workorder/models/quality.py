import base64

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog
from odoo.tools import is_html_empty

_debug = DebugLog(__name__)


class QualityPointTest_Type(models.Model):
    _inherit = "quality.point.test_type"

    allow_registration = fields.Boolean(
        search="_search_allow_registration",
        default=False,
        store=False,
    )

    def _search_allow_registration(self, operator, value) -> list:
        if value:
            return []
        else:
            return [
                (
                    "technical_name",
                    "not in",
                    [
                        "register_production",
                        "register_byproducts",
                        "register_consumed_materials",
                        "print_label",
                    ],
                )
            ]


class MrpRoutingWorkcenter(models.Model):
    _inherit = "mrp.routing.workcenter"

    quality_point_ids = fields.One2many(
        comodel_name="quality.point",
        inverse_name="operation_id",
        copy=True,
    )
    quality_point_count = fields.Integer(
        string="Instructions",
        compute="_compute_quality_point_count",
    )

    employee_ratio = fields.Float(
        string="Employee Capacity",
        default=1,
        help="Number of employees needed to complete operation.",
    )

    default_picking_type_ids = fields.One2many(
        comodel_name="stock.picking.type",
        compute="_compute_default_picking_type_ids",
    )

    @api.depends("employee_ratio")
    def _compute_cost(self) -> None:
        super()._compute_cost()
        for operation in self:
            operation.cost += (
                (operation.time_total / 60.0)
                * operation.workcenter_id.employee_costs_hour
                * (operation.employee_ratio or 1)
            )

    @api.depends("quality_point_ids")
    def _compute_quality_point_count(self) -> None:
        # sudo() is needed here because shop-floor users don't have model-level
        # access to quality.point; keep the company guard in the domain
        # explicitly so the count doesn't leak points from other companies.
        read_group_res = (
            self.env["quality.point"]
            .sudo()
            ._read_group(
                [
                    ("id", "in", self.quality_point_ids.ids),
                    ("company_id", "in", self.env.companies.ids + [False]),
                ],
                ["operation_id"],
                ["__count"],
            )
        )
        data = {operation.id: count for operation, count in read_group_res}
        for operation in self:
            operation.quality_point_count = data.get(operation.id, 0)

    def _compute_default_picking_type_ids(self) -> None:
        self.default_picking_type_ids = self.env["stock.picking.type"].search(
            [("code", "=", "mrp_operation")]
        )

    def write(self, vals):
        if "active" in vals:
            self.with_context(active_test=False).quality_point_ids.write(
                {"active": vals["active"]}
            )
        res = super().write(vals)
        if "bom_id" in vals:
            for operation in self:
                operation.quality_point_ids._update_product_ids_from_bom(
                    operation.bom_id
                )
        return res

    def copy(self, default=None):
        new_workcenters = super().copy(default)
        if default and "bom_id" in default:
            for new_workcenter in new_workcenters:
                new_workcenter.quality_point_ids._update_product_ids_from_bom(
                    new_workcenter.bom_id
                )
        return new_workcenters


class QualityPoint(models.Model):
    _inherit = "quality.point"

    def _default_product_ids(self):
        # Determines a default product from the default operation's BOM.
        operation_id = self.env.context.get("default_operation_id")
        if not operation_id:
            return None
        bom = self.env["mrp.routing.workcenter"].browse(operation_id).bom_id
        return (
            bom.product_id.ids
            if bom.product_id
            else bom.product_tmpl_id.product_variant_id.ids
        )

    is_workorder_step = fields.Boolean(compute="_compute_is_workorder_step")
    operation_id = fields.Many2one(
        comodel_name="mrp.routing.workcenter",
        string="Step",
        index="btree_not_null",
        check_company=True,
    )
    bom_id = fields.Many2one(related="operation_id.bom_id")
    bom_active = fields.Boolean(
        related="bom_id.active",
        string="Related Bill of Material Active",
    )
    component_ids = fields.One2many(
        comodel_name="product.product",
        compute="_compute_component_ids",
    )
    product_ids = fields.Many2many(
        default=lambda self: self._default_product_ids(),
        domain="operation_id and [('id', 'in', bom_product_ids)] or [('type', '=', 'consu'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    bom_product_ids = fields.One2many(
        comodel_name="product.product",
        compute="_compute_bom_product_ids",
    )
    test_type_id = fields.Many2one(
        comodel_name="quality.point.test_type",
        domain="[('allow_registration', '=', operation_id and is_workorder_step)]",
    )
    test_report_type = fields.Selection(
        selection=[("pdf", "PDF"), ("zpl", "ZPL")],
        string="Report Type",
        default="pdf",
        required=True,
    )
    worksheet_document = fields.Binary(string="Image/PDF")
    # Used with type register_consumed_materials the product raw to encode.
    component_id = fields.Many2one(
        comodel_name="product.product",
        string="Product To Register",
        check_company=True,
    )

    @api.onchange("bom_product_ids", "is_workorder_step")
    def _onchange_bom_product_ids(self) -> None:
        if self.is_workorder_step and self.bom_product_ids:
            self.product_ids &= self.bom_product_ids
            self.product_category_ids = False

    @api.depends(
        "bom_id.product_id",
        "bom_id.product_tmpl_id.product_variant_ids",
        "is_workorder_step",
        "bom_id",
    )
    def _compute_bom_product_ids(self) -> None:
        self.bom_product_ids = False
        points_for_workorder_step = self.filtered(lambda p: p.operation_id and p.bom_id)
        for point in points_for_workorder_step:
            bom_product_ids = (
                point.bom_id.product_id
                or point.bom_id.product_tmpl_id.product_variant_ids
            )
            point.bom_product_ids = bom_product_ids.filtered_domain(
                [
                    (
                        "product_tmpl_id.company_id",
                        "in",
                        [False, point.company_id._origin.id],
                    )
                ]
            )

    @api.depends("product_ids", "test_type_id", "is_workorder_step")
    def _compute_component_ids(self) -> None:
        self.component_ids = False
        for point in self:
            if point.test_type == "register_byproducts":
                point.component_ids = point.bom_id.byproduct_ids.product_id
            else:
                bom_products = (
                    point.bom_id.product_id
                    or point.bom_id.product_tmpl_id.product_variant_ids
                )
                # If product_ids is set the step will exist only for these product variant then we can filter out for the bom explode
                if point.product_ids:
                    bom_products &= point.product_ids._origin

                component_product_ids = set()
                for product in bom_products:
                    _dummy, lines_done = point.bom_id._explode(product, 1.0)
                    component_product_ids |= {
                        line[0].product_id.id for line in lines_done
                    }
                point.component_ids = self.env["product.product"].browse(
                    component_product_ids
                )

    @api.depends("operation_id", "picking_type_ids")
    def _compute_is_workorder_step(self) -> None:
        for quality_point in self:
            quality_point.is_workorder_step = quality_point.picking_type_ids and all(
                pt.code == "mrp_operation" for pt in quality_point.picking_type_ids
            )

    @api.depends("operation_id")
    def _compute_show_failure_location(self) -> None:
        super()._compute_show_failure_location()
        for point in self:
            point.show_failure_location = (
                point.show_failure_location and not point.operation_id
            )

    def _update_product_ids_from_bom(self, bom_id) -> None:
        products = bom_id.product_id or bom_id.product_tmpl_id.product_variant_ids
        self.product_ids = [Command.set(products.ids)]

    @api.onchange("operation_id")
    def _onchange_operation_id(self) -> None:
        if self.operation_id:
            self._update_product_ids_from_bom(self.bom_id)

    @api.onchange("test_type_id")
    def _onchange_test_type_id(self) -> None:
        if self.test_type_id.technical_name not in (
            "register_byproducts",
            "register_consumed_materials",
        ):
            self.component_id = False

    def write(self, vals):
        res = super().write(vals)
        if "picking_type_ids" in vals:
            self.filtered(lambda p: not p.is_workorder_step).operation_id = False
        return res

    def action_view_worksheet_document(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Worksheet Preview"),
            "res_model": "quality.point",
            "res_id": self.id,
            "views": [
                (
                    self.env.ref(
                        "mrp_workorder.quality_point_worksheet_document_preview_form"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
        }


class QualityAlert(models.Model):
    _inherit = "quality.alert"

    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Operation",
        index="btree_not_null",
        check_company=True,
    )
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Work Center",
        check_company=True,
    )
    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Production Order",
        index="btree_not_null",
        check_company=True,
    )


class QualityCheck(models.Model):
    _inherit = "quality.check"

    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Operation",
        index="btree_not_null",
        check_company=True,
    )
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        related="workorder_id.workcenter_id",
    )
    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Production Order",
        index="btree_not_null",
        check_company=True,
    )

    # doubly linked chain for tablet view navigation
    next_check_id = fields.Many2one(comodel_name="quality.check")
    previous_check_id = fields.Many2one(comodel_name="quality.check")

    # For components registration
    move_id = fields.Many2one(
        comodel_name="stock.move",
        string="Stock Move",
        index="btree_not_null",
        check_company=True,
    )
    component_id = fields.Many2one(
        comodel_name="product.product",
        check_company=True,
    )
    component_barcode = fields.Char(related="component_id.barcode")
    component_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="move_id.product_uom_id",
        string="Component Unit",
        readonly=True,
    )

    finished_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        related="production_id.trace_producing_ids",
        string="Finished Lot/Serial",
    )
    component_tracking = fields.Selection(
        related="component_id.tracking",
        string="Is Component Tracked",
    )

    # Workorder specific fields
    is_user_working = fields.Boolean(related="workorder_id.is_user_working")
    consumption = fields.Selection(related="workorder_id.consumption")
    working_state = fields.Selection(related="workorder_id.working_state")

    # Computed fields
    title = fields.Char(compute="_compute_title")
    result = fields.Char(compute="_compute_result")

    # Used to group the steps belonging to the same production
    # We use a float because it is actually filled in by the produced quantity at the step creation.
    finished_product_sequence = fields.Float(string="Finished Product Sequence Number")
    worksheet_document = fields.Binary(string="Image/PDF")

    # Employees
    employee_id = fields.Many2one(comodel_name="hr.employee")

    @api.model_create_multi
    def create(self, vals_list):
        quality_points = {
            value["point_id"] for value in vals_list if value.get("point_id")
        }
        quality_points_component_mapping = {
            point.id: point.component_id.id
            for point in self.env["quality.point"].browse(list(quality_points))
            if point.component_id
        }
        for value in vals_list:
            if value.get("component_id") or not value.get("point_id"):
                continue
            component = quality_points_component_mapping.get(value["point_id"])
            if component:
                value["component_id"] = component
        return super().create(vals_list)

    @api.depends(
        "test_type_id",
        "component_id",
        "component_id.name",
        "workorder_id",
        "workorder_id.name",
    )
    def _compute_title(self) -> None:
        super()._compute_title()
        for check in self:
            if not check.title and not check.point_id and check.component_id:
                check.title = f'{check.test_type_id.display_name} "{check.component_id.name or check.workorder_id.name}"'

    @api.depends(
        "point_id",
        "quality_state",
        "component_id",
        "component_uom_id",
        "trace_ids",
        "picture",
    )
    def _compute_result(self) -> None:
        for check in self:
            if check.quality_state == "none":
                check.result = ""
            else:
                check.result = check._get_check_result()

    def copy(self, default=None):
        default = dict(default or {})
        new_checks = super().copy(default)

        for old_check, new_check in zip(self, new_checks, strict=False):
            # only insert into chain if the quality check is linked with another quality check
            if old_check.previous_check_id or old_check.next_check_id:
                new_check._insert_in_chain("after", old_check)
        return new_checks

    def _get_check_result(self):
        if self.test_type in ("register_consumed_materials", "register_byproducts"):
            if len(self.trace_ids) == 1:
                return f"{self.component_id.name} - {self.trace_ids[0].name}, {self.component_uom_id.name}"
            return f"{self.component_id.name}, {self.component_uom_id.name}"
        if self.test_type == "picture" and self.picture:
            # `picture` is `quality`'s, which this module already depends on,
            # so the branch belongs here beside the field it feeds rather than
            # in a bridge that may not be installed.
            return self.env._("Picture Uploaded")
        return ""

    def action_print(self):
        quality_point_id = self.point_id
        report_type = quality_point_id.test_report_type

        if self.product_id.tracking == "none":
            res = self._get_product_label_action(report_type)
        elif self.workorder_id.finished_trace_ids:
            res = self._get_lot_label_action(report_type)
        else:
            raise UserError(
                self.env._("You did not set a lot/serial number for the final product")
            )

        # The button goes immediately to the next step
        res["next_check_id"] = self._next()
        return res

    def _get_print_qty(self):
        uom_unit = self.env.ref("base.product_uom_unit")
        if (
            self.product_tracking != "serial"
            and self.product_id.uom_id._has_common_reference(uom_unit)
        ):
            qty = int(self.workorder_id.qty_producing) or int(
                self.workorder_id.qty_production
            )
        else:
            qty = 1
        return qty

    def _get_product_label_action(self, report_type):
        self.check_singleton()
        xml_id = "product.action_view_label_layout"
        wizard_action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            xml_id
        )
        wizard_action["context"] = {"default_product_ids": self.product_id.ids}
        if report_type == "zpl":
            wizard_action["context"]["default_print_format"] = "zpl"
        wizard_action["id"] = self.env.ref(xml_id).id
        return wizard_action

    def _get_lot_label_action(self, report_type):
        qty = self._get_print_qty()

        if report_type == "zpl":
            xml_id = "stock.label_lot_template"
        else:
            xml_id = "stock.action_report_lot_label"
        res = self.env.ref(xml_id).report_action(
            self.workorder_id.finished_trace_ids.ids * qty
        )
        res["id"] = self.env.ref(xml_id).id
        return res

    def action_next(self):
        self.check_singleton()
        return {"next_check_id": self._next()}

    def add_check_in_chain(self, notify_bom=True) -> None:
        self.check_singleton()
        _debug.pipeline(
            "check_added_to_chain",
            check=self.id,
            workorder=self.workorder_id.id,
            by="after_current"
            if self.workorder_id.current_quality_check_id
            else "first",
        )
        if self.workorder_id.current_quality_check_id:
            self._insert_in_chain("after", self.workorder_id.current_quality_check_id)
        else:
            self.workorder_id.current_quality_check_id = self
        if notify_bom and self.workorder_id.production_id.bom_id:
            body = self.env._(
                "BoM feedback (%(production)s - %(operation)s)",
                production=self.workorder_id.production_id.name,
                operation=self.workorder_id.operation_id.name,
            )
            body += Markup("<br/>%s") % self.env._(
                "New Step suggested by %(user_name)s", user_name=self.env.user.name
            )
            if self.title:
                body += Markup("<br/><b>%s</b> %s") % (self.env._("Title:"), self.title)
            if self.note and not is_html_empty(self.note):
                body += Markup("<br/><b>%s</b>%s") % (
                    self.env._("Instruction:"),
                    self.note,
                )
            attachments = []
            if self.worksheet_document:
                attachments = [("document", base64.b64decode(self.worksheet_document))]
            self.workorder_id.production_id.bom_id.message_post(
                body=body, attachments=attachments
            )

    def _next(self):
        """Set this as the current check, pass it if still pending, and advance the workorder to the next check."""
        self.check_singleton()
        self.workorder_id.current_quality_check_id = self.id

        if self.test_type == "picture" and not self.picture:
            _debug.logic("check_refused", reason="picture_missing", check=self.id)
            raise UserError(self.env._("Please upload a picture."))

        _debug.lifecycle(
            "check_advanced",
            check=self.id,
            workorder=self.workorder_id.id,
            test_type=self.test_type,
            state=self.quality_state,
        )
        if self.quality_state == "none":
            self.do_pass()

        return self.workorder_id._update_current_quality_check(position="next")

    def _insert_in_chain(self, position, relative) -> None:
        """Insert the quality check `self` in a chain of quality checks.

        The chain of quality checks is implicitly given by the `relative` argument,
        i.e. by following its `previous_check_id` and `next_check_id` fields.

        :param position: Where we need to insert `self` according to `relative`
        :type position: string
        :param relative: Where we need to insert `self` in the chain
        :type relative: A `quality.check` record.
        """
        self.check_singleton()
        assert position in ["before", "after"]
        if position == "before":
            new_previous = relative.previous_check_id
            self.next_check_id = relative
            self.previous_check_id = new_previous
            new_previous.next_check_id = self
            relative.previous_check_id = self
        else:
            new_next = relative.next_check_id
            self.next_check_id = new_next
            self.previous_check_id = relative
            new_next.previous_check_id = self
            relative.next_check_id = self

    def _on_pass(self):
        # Moved off `do_pass`, which only the button reached:
        # `check_quality_checks` closes a check by writing the field, and
        # the move it names has to end up picked either way.
        super()._on_pass()
        _debug.lifecycle("checks_passed", checks=self)
        for check in self:
            if check.move_id:
                check.move_id.picked = True
            if check.workorder_id:
                if check.workorder_id.employee_id:
                    # `check`, not `self`: this is inside the per-record loop,
                    # and reading it off the recordset raises on more than one.
                    check.employee_id = check.workorder_id.employee_id
                if check.workorder_id.state == "ready":
                    check.workorder_id.button_start(bypass=True)
