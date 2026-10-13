from collections import defaultdict
from datetime import UTC, datetime

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools import float_compare, float_is_zero
from odoo.tools.date_utils import get_intervals_hours

from odoo.addons.web.controllers.utils import clean_action

_debug = DebugLog(__name__)


class MrpWorkorder(models.Model):
    _name = "mrp.workorder"
    _inherit = ["mixin.hr", "mrp.workorder", "mixin.barcodes.barcode_events"]

    quality_point_ids = fields.Many2many(
        comodel_name="quality.point",
        compute="_compute_quality_point_ids",
        store=True,
    )

    check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="workorder_id",
    )
    finished_product_check_ids = fields.Many2many(
        comodel_name="quality.check",
        compute="_compute_finished_product_check_ids",
    )
    done_check_ids = fields.Many2many(
        comodel_name="quality.check",
        compute="_compute_done_check_ids",
    )
    quality_check_todo = fields.Boolean(compute="_compute_check")
    quality_check_fail = fields.Boolean(compute="_compute_check")
    quality_alert_ids = fields.One2many(
        comodel_name="quality.alert",
        inverse_name="workorder_id",
    )
    quality_alert_count = fields.Count(count_of="quality_alert_ids")

    current_quality_check_id = fields.Many2one(
        comodel_name="quality.check",
        check_company=True,
    )

    allow_producing_quantity_change = fields.Boolean(
        string="Allow Changes to Producing Quantity",
        default=True,
    )

    is_last_lot = fields.Boolean(
        string="Is Last lot",
        compute="_compute_is_last_lot",
    )
    is_first_started_wo = fields.Boolean(
        string="Is The first Work Order",
        compute="_compute_is_last_unfinished_wo",
    )
    is_last_unfinished_wo = fields.Boolean(
        string="Is Last Work Order To Process",
        compute="_compute_is_last_unfinished_wo",
        store=False,
    )
    move_id = fields.Many2one(
        related="current_quality_check_id.move_id",
        readonly=False,
    )
    move_line_ids = fields.One2many(related="move_id.move_line_ids")
    quality_state = fields.Selection(
        related="current_quality_check_id.quality_state",
        string="Quality State",
        readonly=False,
    )
    test_type_id = fields.Many2one(
        comodel_name="quality.point.test_type",
        related="current_quality_check_id.test_type_id",
        string="Test Type",
    )
    test_type = fields.Char(related="test_type_id.technical_name")
    user_id = fields.Many2one(
        related="current_quality_check_id.user_id",
        readonly=False,
    )
    worksheet_page = fields.Integer(string="Worksheet page")
    picture = fields.Binary(
        related="current_quality_check_id.picture",
        readonly=False,
    )
    product_description_variants = fields.Char(
        related="production_id.product_description_variants"
    )

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        compute="_compute_employee_id",
    )
    employee_name = fields.Char(compute="_compute_employee_id")

    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Working employees",
        copy=False,
    )
    employee_assigned_ids = fields.Many2many(
        comodel_name="hr.employee",
        relation="mrp_workorder_employee_assigned",
        column1="workorder_id",
        column2="employee_id",
        string="Assigned",
        domain="[('company_id', 'in', allowed_company_ids)]",
    )
    connected_employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        search="_search_connected_employee_ids",
        store=False,
    )

    allowed_employees = fields.Many2many(related="workcenter_id.employee_ids")
    all_employees_allowed = fields.Boolean(compute="_compute_all_employees_allowed")

    employee_costs_hour = fields.Float(
        string="Employee Cost per hour",
        default=0.0,
    )

    @api.depends(
        "operation_id.quality_point_ids",
        "operation_id.quality_point_ids.product_ids",
        "operation_id.quality_point_ids.company_id",
        "production_id.product_id",
        "company_id",
    )
    def _compute_quality_point_ids(self) -> None:
        for workorder in self:
            quality_points = workorder.operation_id.quality_point_ids
            quality_points = quality_points.filtered_domain(
                [
                    "|",
                    ("product_ids", "=", False),
                    ("product_ids", "in", workorder.production_id.product_id.ids),
                    ("company_id", "=", workorder.company_id.id),
                ]
            )
            workorder.quality_point_ids = quality_points

    @api.depends("qty_producing", "qty_remaining")
    def _compute_is_last_lot(self) -> None:
        for wo in self:
            precision = wo.production_id.product_uom_id.rounding
            wo.is_last_lot = (
                float_compare(
                    wo.qty_producing, wo.qty_remaining, precision_rounding=precision
                )
                >= 0
            )

    @api.depends("production_id.workorder_ids")
    def _compute_is_last_unfinished_wo(self) -> None:
        for wo in self:
            other_wos = wo.production_id.workorder_ids - wo
            wo.is_first_started_wo = all(other.state != "done" for other in other_wos)
            wo.is_last_unfinished_wo = all(
                other.state in ["done", "cancel"] for other in other_wos
            )

    @api.depends("check_ids")
    def _compute_finished_product_check_ids(self) -> None:
        for wo in self:
            wo.finished_product_check_ids = wo._get_finished_product_checks()

    def _get_finished_product_checks(self):
        self.check_singleton()
        precision = self.production_id.product_uom_id.rounding
        return self.check_ids.filtered(
            lambda check: (
                float_compare(
                    check.finished_product_sequence,
                    self.qty_produced,
                    precision_rounding=precision,
                )
                == 0
            )
        )

    @api.depends("check_ids.quality_state")
    def _compute_done_check_ids(self) -> None:
        for wo in self:
            wo.done_check_ids = wo.check_ids.filtered(
                lambda c: c.quality_state != "none"
            )

    def unlink(self):
        self.check_ids.sudo().unlink()
        return super().unlink()

    def action_back(self):
        self.check_singleton()
        if self._is_pending_required():
            self.button_pending()
        domain = [("state", "not in", ["done", "cancel", "blocked"])]
        if self.env.context.get("from_manufacturing_order"):
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "mrp_workorder.mrp_workorder_action_tablet"
            )
            action["domain"] = domain
            action["context"] = self.env["ir.actions.actions"]._eval_action_context(
                action["context"]
            ) | {
                "no_breadcrumbs": True,
                "search_default_production_id": self.production_id.id,
                "search_default_workcenter_id": False,
                "search_default_progress": False,
                "search_default_ready": False,
                "from_manufacturing_order": True,
            }
        elif self.env.context.get("from_production_order"):
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "mrp.mrp_workorder_todo"
            )
            action["target"] = "main"
            action["context"] = dict(
                self.env["ir.actions.actions"]._eval_action_context(action["context"]),
                no_breadcrumbs=True,
            )
        elif self.env.context.get("mrp_display"):
            return None
        else:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "mrp_workorder.mrp_workorder_action_tablet"
            )
            action["domain"] = domain
            action["context"] = self.env["ir.actions.actions"]._eval_action_context(
                action["context"], active_id=self.id
            ) | {
                "no_breadcrumbs": True,
                "search_default_workcenter_id": self.workcenter_id.id,
            }
        if self.employee_id:
            action["context"]["employee_id"] = self.employee_id.id
            action["context"]["employee_name"] = self.employee_id.name
        return clean_action(action, self.env)

    def action_cancel(self):
        self.mapped("check_ids").filtered(
            lambda c: c.quality_state == "none"
        ).sudo().unlink()
        return super().action_cancel()

    def action_generate_serial(self):
        self.check_singleton()
        return self.production_id.action_generate_serial(self)

    def _update_current_quality_check(self, position):
        self.check_singleton()
        assert position in ["first", "next", "previous", "last"]
        checks_to_consider = self.check_ids.filtered(
            lambda c: c.quality_state == "none"
        )
        if position == "first":
            check = checks_to_consider.filtered(
                lambda check: not check.previous_check_id
            )
        elif position == "next":
            check = self.current_quality_check_id.next_check_id
            if not check:
                check = checks_to_consider[:1]
            elif check.quality_state != "none":
                self.current_quality_check_id = check
                return self._update_current_quality_check(position="next")
        elif position == "previous":
            check = self.current_quality_check_id.previous_check_id
        else:
            check = checks_to_consider.filtered(lambda check: not check.next_check_id)
        self.write(
            {
                "allow_producing_quantity_change": not check.previous_check_id.filtered(
                    lambda c: c.quality_state != "fail"
                )
                and all(c.quality_state != "fail" for c in checks_to_consider)
                and self.is_first_started_wo,
                "current_quality_check_id": check.id,
            }
        )
        return check.id

    def action_menu(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.workorder",
            "views": [
                [
                    self.env.ref(
                        "mrp_workorder.mrp_workorder_view_form_tablet_menu"
                    ).id,
                    "form",
                ]
            ],
            "name": self.env._("Menu"),
            "target": "new",
            "res_id": self.id,
        }

    def action_add_component(self):
        self.check_singleton()
        return self.production_id.with_context(
            workorder_id=self.id
        ).action_add_component()

    def action_add_byproduct(self):
        self.check_singleton()
        return self.production_id.with_context(
            workorder_id=self.id
        ).action_add_byproduct()

    def action_add_workorder(self) -> dict:
        self.check_singleton()
        default_blocking_wo_id = self.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.mrp.production.add.workorder",
            "views": [
                [
                    self.env.ref(
                        "mrp_workorder.view_mrp_production_additional_workorder_wizard"
                    ).id,
                    "form",
                ]
            ],
            "name": self.env._("Add Work Order"),
            "target": "new",
            "context": {
                "default_production_id": self.production_id.id,
                "default_blocked_by_workorder_id": default_blocking_wo_id,
            },
        }

    def button_start(self, skip_invalid_state=False, bypass=False):
        skip_employee_check = bypass or (not request and not self.env.user.employee_id)
        main_employee = False
        if not skip_employee_check:
            if not self.env.context.get("mrp_display"):
                main_employee = self.env.user.employee_id.id
                if not self.env.user.employee_id:
                    _debug.logic(
                        "workorder_start_refused",
                        reason="user_has_no_employee",
                        workorders=self,
                    )
                    raise UserError(
                        self.env._(
                            "You need to link this user to an employee of this company to process the work order"
                        )
                    )
            else:
                connected_employees = self.env["hr.employee"].get_employees_connected()
                if len(connected_employees) == 0:
                    _debug.logic(
                        "workorder_start_refused",
                        reason="nobody_logged_in",
                        workorders=self,
                    )
                    raise UserError(
                        self.env._("You need to log in to process this work order.")
                    )
                main_employee = self._get_acting_employee().id
                if not main_employee:
                    _debug.logic(
                        "workorder_start_refused",
                        reason="no_session_chief",
                        workorders=self,
                    )
                    raise UserError(
                        self.env._("There is no session chief. Please log in.")
                    )
            if self and all(
                main_employee not in [emp.id for emp in wo.allowed_employees]
                and not wo.all_employees_allowed
                for wo in self
            ):
                _debug.logic(
                    "workorder_start_refused",
                    reason="employee_not_allowed",
                    workorders=self,
                    employee=main_employee,
                )
                raise UserError(
                    self.env._("You are not allowed to work on the workorder")
                )

        _debug.pipeline(
            "shopfloor_start",
            workorders=self,
            employee=main_employee or False,
            skipped_check=skip_employee_check,
        )
        res = super().button_start(skip_invalid_state=skip_invalid_state)

        if main_employee:
            main_employee = self.env["hr.employee"].browse(main_employee)
            for wo in self:
                if (
                    len(wo.allowed_employees) == 0
                    or main_employee in wo.allowed_employees
                ) and wo.state not in ("done", "cancel"):
                    wo.start_employee(main_employee.id)
                    wo.employee_ids |= main_employee
                    wo.employee_assigned_ids |= main_employee

        return res

    def button_finish(self):
        for workorder in self:
            if workorder.state in ("done", "cancel"):
                continue
            workorder.employee_costs_hour = workorder.workcenter_id.employee_costs_hour
        self.check_quality_checks()
        return super().button_finish()

    def check_quality_checks(self) -> None:
        for check in self.check_ids:
            if check.quality_state in ["pass", "fail"]:
                continue
            if check.test_type in [
                "register_consumed_materials",
                "register_byproducts",
                "instructions",
            ]:
                check.quality_state = "pass"
            else:
                raise UserError(
                    self.env._(
                        "You need to complete Quality Checks using the Shop Floor before marking Work Order as Done."
                    )
                )

    def action_propose_change(self, change_type, check_id) -> dict:
        change_type_to_title = {
            "update_step": "Update Instructions",
            "remove_step": "Remove Step",
            "set_picture": "Change Picture",
        }
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.mrp.workorder.update.instruction",
            "views": [
                [self.env.ref("mrp_workorder.view_propose_change_wizard").id, "form"]
            ],
            "name": change_type_to_title[change_type],
            "target": "new",
            "context": {
                "default_workorder_id": self.id,
                "default_step_id": check_id,
                "default_change_type": change_type,
            },
        }

    def action_add_step(self) -> dict:
        self.check_singleton()
        if self.current_quality_check_id:
            team = self.current_quality_check_id.team_id
        else:
            team = self.env["team.team"].search(
                [
                    ("use_quality", "=", True),
                    "|",
                    ("company_id", "=", self.company_id.id),
                    ("company_id", "=", False),
                ],
                limit=1,
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "quality.check",
            "views": [
                [self.env.ref("mrp_workorder.add_quality_check_from_tablet").id, "form"]
            ],
            "name": self.env._("Add a Step"),
            "target": "new",
            "context": {
                "default_test_type_id": self.env.ref(
                    "quality.test_type_instructions"
                ).id,
                "default_workorder_id": self.id,
                "default_production_id": self.production_id.id,
                "default_product_id": self.product_id.id,
                "default_team_id": team.id,
            },
        }

    def action_view_mes(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_workorder.action_mrp_display"
        )
        action["context"] = self.env["ir.actions.actions"]._eval_action_context(
            action["context"]
        ) | {
            "workcenter_id": self.workcenter_id.id,
            "search_default_progress": False,
            "search_default_ready": False,
            "search_default_name": self.production_id.name,
            "shouldHideNewWorkcenterButton": True,
        }
        action["context"].pop("search_default_filter_ready", None)
        return action

    def action_log_note(self):
        return self.production_id.action_log_note()

    @api.depends("check_ids.quality_state")
    def _compute_check(self) -> None:
        for workorder in self:
            todo = False
            fail = False
            for check in workorder.check_ids:
                if check.quality_state == "none":
                    todo = True
                elif check.quality_state == "fail":
                    fail = True
                if fail and todo:
                    break
            workorder.quality_check_fail = fail
            workorder.quality_check_todo = todo

    def _create_checks(self) -> None:
        for wo in self:
            production = wo.production_id

            move_raw_ids = wo.move_raw_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            )
            move_finished_ids = wo.move_finished_ids.filtered_domain(
                [
                    ("state", "not in", ("done", "cancel")),
                    ("product_id", "!=", wo.production_id.product_id.id),
                ]
            )
            previous_check = self.env["quality.check"]
            _debug.pipeline(
                "workorder_checks_created",
                workorder=wo.id,
                points=len(wo.quality_point_ids),
                raw_moves=len(move_raw_ids),
                finished_moves=len(move_finished_ids),
            )
            for point in wo.quality_point_ids:
                if point.check_execute_now():
                    moves = self.env["stock.move"]
                    values = {
                        "production_id": production.id,
                        "workorder_id": wo.id,
                        "point_id": point.id,
                        "team_id": point.team_id.id,
                        "company_id": wo.company_id.id,
                        "product_id": production.product_id.id,
                        "finished_product_sequence": wo.qty_produced,
                        "previous_check_id": previous_check.id,
                        "worksheet_document": point.worksheet_document,
                    }
                    if point.test_type == "register_byproducts":
                        moves = move_finished_ids.filtered_domain(
                            [("product_id", "=", point.component_id.id)]
                        )
                        if not moves:
                            moves = production.move_finished_ids.filtered_domain(
                                [
                                    ("operation_id", "=", False),
                                    ("product_id", "=", point.component_id.id),
                                ]
                            )
                    elif point.test_type == "register_consumed_materials":
                        moves = move_raw_ids.filtered_domain(
                            [("product_id", "=", point.component_id.id)]
                        )
                        if not moves:
                            moves = production.move_raw_ids.filtered_domain(
                                [
                                    ("operation_id", "=", False),
                                    ("product_id", "=", point.component_id.id),
                                ]
                            )
                    else:
                        check = self.env["quality.check"].create(values)
                        previous_check.next_check_id = check
                        previous_check = check
                    for move in moves:
                        check_vals = values.copy()
                        check_vals.update(wo._prepare_check_vals_from_move(move))
                        check_vals.update({"previous_check_id": previous_check.id})
                        check = self.env["quality.check"].create(check_vals)
                        previous_check.next_check_id = check
                        previous_check = check

            wo._update_current_quality_check(position="first")

    def _get_byproduct_move_to_update(self):
        moves = super()._get_byproduct_move_to_update()
        return moves.filtered(lambda m: m.product_id.tracking == "none")

    def pre_record_production(self) -> None:
        self.check_singleton()
        self._check_company()
        if any(
            x.quality_state == "none"
            for x in self.check_ids
            if x.test_type != "instructions"
        ):
            raise UserError(self.env._("You still need to do the quality checks!"))
        if (
            float_compare(
                self.qty_producing, 0, precision_rounding=self.product_uom_id.rounding
            )
            <= 0
        ):
            raise UserError(
                self.env._(
                    "Please set the quantity you are currently producing. It should be different from zero."
                )
            )

    def record_production(self):
        if not self:
            return True
        self.check_singleton()

        self.pre_record_production()

        backorder = False
        if (
            float_compare(
                self.qty_producing,
                self.qty_remaining,
                precision_rounding=self.product_uom_id.rounding,
            )
            == -1
            and self.is_first_started_wo
        ):
            _debug.logic(
                "record_production",
                workorder=self.id,
                by="short_quantity",
                create_backorder=self.production_id.picking_type_id.create_backorder,
                producing=self.qty_producing,
                remaining=self.qty_remaining,
            )
            match self.production_id.picking_type_id.create_backorder:
                case "ask":
                    return self.production_id.with_context(
                        workorder_id_to_finish=self.id
                    )._prepare_action_backorder_wizard(self.production_id)
                case "always":
                    backorder = self.production_id._split_productions(
                        {
                            self.production_id: [
                                self.qty_producing,
                                self.qty_remaining - self.qty_producing,
                            ]
                        }
                    )[1:]
                    for workorder in backorder.workorder_ids:
                        if not self.env.context.get("no_start_next", False):
                            workorder.qty_producing = workorder.qty_remaining
                    self.production_id.product_qty = self.qty_producing

        elif self.operation_id:
            backorder = (
                self.production_id.production_group_id.production_ids
                - self.production_id
            ).filtered(
                lambda p: (
                    p.workorder_ids.filtered(
                        lambda wo: wo.operation_id == self.operation_id
                    ).state
                    not in ("cancel", "done")
                )
            )[:1]
        else:
            index = list(self.production_id.workorder_ids).index(self)
            backorder = (
                self.production_id.production_group_id.production_ids
                - self.production_id
            ).filtered(
                lambda p: (
                    index < len(p.workorder_ids)
                    and p.workorder_ids[index].state not in ("cancel", "done")
                )
            )[:1]

        _debug.pipeline(
            "record_production_settled", workorder=self.id, backorder=backorder or False
        )
        return self.post_record_production(backorder)

    def post_record_production(self, backorders=False):

        self.button_finish()

        if backorders:
            for wo in (self.production_id | backorders).workorder_ids:
                if wo.state in ("done", "cancel"):
                    continue
                wo.current_quality_check_id.update(
                    wo._prepare_check_vals_from_move(wo.move_id)
                )

        return self.action_back()

    def _prepare_check_vals_from_move(self, move):
        self.check_singleton()
        vals = {"move_id": move.id}
        move_line_id = move.move_line_ids[:1]
        if move_line_id:
            vals.update(
                {
                    "trace_ids": move_line_id.trace_id.ids,
                }
            )
        return vals

    def open_tablet_view(self):
        self.check_singleton()
        self.env["hr.employee"].login_user_employee()
        if self._is_start_required():
            self.button_start()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_workorder.tablet_client_action"
        )
        action["target"] = "fullscreen"
        action["res_id"] = self.id
        action["context"] = {
            "active_id": self.id,
            "from_production_order": self.env.context.get("from_production_order"),
            "from_manufacturing_order": self.env.context.get(
                "from_manufacturing_order"
            ),
        }
        return action

    def action_view_manufacturing_order(self):
        no_start_next = self.env.context.get("no_start_next", True)
        action = self.with_context(no_start_next=no_start_next).do_finish()
        try:
            with self.env.cr.savepoint():
                res = self.production_id.button_mark_done()
                if res is not True:
                    res["context"] = dict(res.get("context", {}), from_workorder=True)
                    return res
        except (UserError, ValidationError) as e:
            self.production_id.activity_schedule(
                "mail.mail_activity_data_warning",
                note=str(e),
                summary=self.env._(
                    "The %(production)s could not be closed",
                    production=self.production_id.name,
                ),
                user_id=self.env.user.id,
            )
            return {
                "type": "ir.actions.act_window",
                "res_model": "mrp.production",
                "views": [[self.env.ref("mrp.mrp_production_form_view").id, "form"]],
                "res_id": self.production_id.id,
                "target": "main",
            }
        return action

    def do_finish(self):
        self.check_singleton()
        self.end_all()
        if self.state != "done":
            action = self.record_production()
            self._set_default_time_log()
            if action is not True:
                return action
        return self.action_back()

    def _action_confirm(self):
        res = super()._action_confirm()
        self.filtered(
            lambda wo: wo.state != "cancel" and not wo.check_ids
        )._create_checks()
        return res

    def _update_qty_producing(self, quantity):
        if float_is_zero(quantity, precision_rounding=self.product_uom_id.rounding):
            self.check_ids.unlink()
        super()._update_qty_producing(quantity)

    def _web_gantt_reschedule_is_record_candidate(
        self, start_date_field_name, stop_date_field_name
    ):
        return self.state not in [
            "progress",
            "done",
            "cancel",
        ] and super()._web_gantt_reschedule_is_record_candidate(
            start_date_field_name, stop_date_field_name
        )

    def _web_gantt_reschedule_compute_dates(
        self,
        date_candidate,
        search_forward,
        start_date_field_name,
        stop_date_field_name,
    ):
        from_date, to_date = self.workcenter_id._get_first_available_slot(
            date_candidate,
            self.duration_expected,
            forward=search_forward,
            reservations_to_ignore=self.reservation_id,
        )
        return [from_date, to_date]

    def _web_gantt_reschedule_write_new_dates(
        self, new_start_date, new_stop_date, start_date_field_name, stop_date_field_name
    ):
        return super(
            MrpWorkorder, self.with_context(bypass_duration_calculation=True)
        )._web_gantt_reschedule_write_new_dates(
            new_start_date, new_stop_date, start_date_field_name, stop_date_field_name
        )

    def _web_gantt_progress_bar_workcenter_id(self, res_ids, start, stop) -> dict:
        self.env["mrp.workorder"].check_access("read")
        workcenters = self.env["mrp.workcenter"].search([("id", "in", res_ids)])
        workorders = self.env["mrp.workorder"].search(
            [
                ("workcenter_id", "in", res_ids),
                ("state", "not in", ["done", "cancel"]),
                ("date_start", "<=", stop.replace(tzinfo=None)),
                ("date_end", ">=", start.replace(tzinfo=None)),
            ]
        )
        planned_hours = defaultdict(float)
        workcenters_work_intervals, _dummy = (
            workcenters.resource_id._get_valid_work_intervals(start, stop)
        )
        for workorder in workorders:
            max_start = max(start, workorder.date_start.replace(tzinfo=UTC))
            min_finished = min(stop, workorder.date_end.replace(tzinfo=UTC))
            interval = Intervals(
                [(max_start, min_finished, self.env["resource.calendar.attendance"])]
            )
            work_intervals = (
                interval
                & workcenters_work_intervals[workorder.workcenter_id.resource_id.id]
            )
            planned_hours[workorder.workcenter_id] += get_intervals_hours(
                work_intervals
            )
        work_hours = {
            id: get_intervals_hours(work_intervals)
            for id, work_intervals in workcenters_work_intervals.items()
        }
        return {
            workcenter.id: {
                "value": planned_hours[workcenter],
                "max_value": work_hours.get(workcenter.resource_id.id, 0.0),
            }
            for workcenter in workcenters
        }

    @api.model
    def get_gantt_data(
        self,
        domain,
        groupby,
        read_specification,
        limit=None,
        offset=0,
        unavailability_fields=None,
        progress_bar_fields=None,
        start_date=None,
        stop_date=None,
        scale=None,
    ):
        gantt_data = super(
            MrpWorkorder, self.with_context(prefix_product=True)
        ).get_gantt_data(
            domain,
            groupby,
            read_specification,
            limit=limit,
            offset=offset,
            unavailability_fields=unavailability_fields,
            progress_bar_fields=progress_bar_fields,
            start_date=start_date,
            stop_date=stop_date,
            scale=scale,
        )
        if "workcenter_id" not in gantt_data["unavailabilities"]:
            workcenter_ids = set()
            if groupby and "workcenter_id" in groupby:
                for group in gantt_data["groups"]:
                    res_id = (
                        group["workcenter_id"][0] if group["workcenter_id"] else False
                    )
                    workcenter_ids.add(res_id)
            else:
                for record in gantt_data["records"]:
                    res_id = (
                        record["workcenter_id"]["id"]
                        if record.get("workcenter_id")
                        else False
                    )
                    workcenter_ids.add(res_id)
            start, stop = (
                fields.Datetime.from_string(start_date),
                fields.Datetime.from_string(stop_date),
            )
            gantt_data["unavailabilities"]["workcenter_id"] = (
                self._gantt_unavailability(
                    "workcenter_id", workcenter_ids, start, stop, scale
                )
            )
        return gantt_data

    @api.model
    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        start, stop = start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start = max(start, today)
        if field_name == "workcenter_id":
            return dict(
                self._web_gantt_progress_bar_workcenter_id(res_ids, start, stop),
                warning=self.env._(
                    "This workcenter isn't expected to have open workorders during this period. Work hours :"
                ),
            )
        raise NotImplementedError("This Progress Bar is not implemented.")

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        if field_name != "workcenter_id":
            return super()._gantt_unavailability(
                field_name, res_ids, start, stop, scale
            )

        workcenters = self.env["mrp.workcenter"].browse(res_ids)
        unavailability_mapping = workcenters._get_unavailability_intervals(start, stop)

        result = {}
        for workcenter in workcenters:
            result[workcenter.id] = [
                {"start": interval[0], "stop": interval[1]}
                for interval in unavailability_mapping[workcenter.id]
            ]
        return result

    @api.model
    def get_shopfloor_limit(self):
        return self.env.registry.settings.get(
            self.env, "mrp_workorder.wo_shop_floor_maximum_card_count", False
        )

    def _is_pending_required(self) -> bool:
        return bool(
            self.is_user_working
            and self.working_state != "blocked"
            and len(self.employee_ids.ids) == 0
        )

    def _is_start_required(self) -> bool:
        if self.working_state != "blocked" and self.state in (
            "ready",
            "blocked",
            "progress",
        ):
            if self.env["hr.employee"].get_session_owner():
                return True
            else:
                self.button_start(bypass=True)
        return False

    @api.depends("employee_ids")
    def _compute_employee_id(self) -> None:
        main_employee_connected = self.env["hr.employee"].get_session_owner()
        self.employee_id = main_employee_connected
        self.employee_name = (
            self.env["hr.employee"].browse(main_employee_connected).name
        )

    def _search_connected_employee_ids(self, operator, value) -> list:
        main_employee_connected = self.env["hr.employee"].get_session_owner()
        if not main_employee_connected:
            return []
        search_query = self.env["mrp.workorder"]._search(
            [("employee_assigned_ids", "=", main_employee_connected)]
        )
        return [("id", operator, search_query)]

    @api.depends("allowed_employees")
    def _compute_all_employees_allowed(self) -> None:
        for wo in self:
            wo.all_employees_allowed = len(wo.allowed_employees) == 0

    def start_employee(self, employee_id) -> None:
        self.check_singleton()
        if self.working_state == "blocked":
            _debug.logic(
                "employee_start_refused",
                reason="workcenter_blocked",
                workorder=self.id,
                employee=employee_id,
            )
            raise UserError(
                self.env._("Please unblock the work center to start the work order.")
            )
        if employee_id in self.employee_ids.ids and any(
            not t.date_end for t in self.time_ids if t.employee_id.id == employee_id
        ):
            return
        self.employee_ids = [Command.link(employee_id)]
        time_data = self._prepare_timeline_vals(self.duration, fields.Datetime.now())
        time_data["employee_id"] = employee_id
        self.env["mrp.workcenter.productivity"].create(time_data)
        _debug.lifecycle("employee_started", workorder=self.id, employee=employee_id)
        self.state = "progress"

    def stop_employee(self, employee_ids) -> None:
        _debug.lifecycle(
            "employees_stopped", workorders=self, employees=len(employee_ids)
        )
        self.employee_ids = [Command.unlink(emp) for emp in employee_ids]
        self.env["mrp.workcenter.productivity"].search(
            [
                ("employee_id", "in", employee_ids),
                ("workorder_id", "in", self.ids),
                ("date_end", "=", False),
            ]
        )._close()

    def _is_timer_start_required(self) -> bool:
        self.check_singleton()
        return not request and not self.env.user.employee_id

    def _get_employee_costs_hour(self):
        self.check_singleton()
        return self.employee_costs_hour or self.workcenter_id.employee_costs_hour

    def _get_cost(self, date=False):
        total_workcenter_cost = super()._get_cost(date)
        for wo in self:
            if wo._is_cost_estimate_required():
                total_workcenter_cost += wo._get_expected_labour_cost()
            elif date:
                total_workcenter_cost += sum(
                    wo.time_ids.filtered(
                        lambda t: t.date_end and t.date_end <= date
                    ).mapped("total_cost")
                )
            else:
                total_workcenter_cost += sum(wo.time_ids.mapped("total_cost"))
        return total_workcenter_cost

    def button_pending(self) -> None:
        Employee = self.env["hr.employee"]
        if self.env.context.get("mrp_display") and not (
            Employee.get_employees_connected()
        ):
            raise UserError(
                self.env._("You need to log in to process this work order.")
            )
        employee = self._get_acting_employee()
        if employee:
            self.stop_employee([employee.id])
        super().button_pending()

    def action_mark_as_done(self):
        main_employee_connected = self._get_acting_employee().id

        for wo in self:
            if not main_employee_connected:
                raise UserError(
                    self.env._(
                        "You must be logged in to process some of these work orders."
                    )
                )
            if len(wo.allowed_employees) != 0 and main_employee_connected not in [
                employee.id for employee in wo.allowed_employees
            ]:
                raise UserError(
                    self.env._(
                        "You are not allow to work on some of these work orders."
                    )
                )
        return super().action_mark_as_done()

    def _get_expected_operation_cost(self, without_employee_cost=False):
        expected_machine_cost = super()._get_expected_operation_cost()
        if without_employee_cost:
            return expected_machine_cost
        return expected_machine_cost + self._get_expected_labour_cost()

    def _get_expected_labour_cost(self):
        self.check_singleton()
        return (
            (self.duration_expected / 60)
            * self._get_employee_costs_hour()
            * (self.operation_id.employee_ratio or 1)
        )

    def _get_theoretical_operation_cost(self, without_employee_cost=False):
        current_machine_cost = super()._get_theoretical_operation_cost()
        if without_employee_cost:
            return current_machine_cost
        return current_machine_cost + self._get_theoretical_employee_cost()

    def _get_theoretical_employee_cost(self):
        return (
            (self.get_duration() / 60)
            * self.workcenter_id.employee_costs_hour
            * (self.operation_id.employee_ratio or 1)
        )

    def _get_current_operation_cost(self):
        current_machine_cost = super()._get_current_operation_cost()
        current_labour_cost = sum(self.time_ids.mapped("total_cost"))
        return current_machine_cost + current_labour_cost

    def end_all(self):
        self.employee_ids = [Command.clear()]
        return super().end_all()

    def action_mrp_workorder_dependencies(self, action_name):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "mrp.action_mrp_workorder_%s" % action_name
        )
        ref = (
            "mrp_workorder.workcenter_line_gantt_production_dependencies"
            if action_name == "production"
            else "mrp_workorder.mrp_workorder_view_gantt_dependencies"
        )

        if self.env.user.has_group("mrp.group_mrp_workorder_dependencies"):
            action["views"] = [(self.env.ref(ref).id, "gantt")] + [
                (id, kind) for id, kind in action["views"] if kind != "gantt"
            ]
        return action

    def _prepare_timeline_vals(self, duration, date_start, date_end=False):
        time_data = super()._prepare_timeline_vals(
            duration=duration, date_start=date_start, date_end=date_end
        )
        employee = self._get_connected_employee()
        time_data["employee_id"] = employee.id
        time_data["description"] = self.env._(
            "Time Tracking: %(user)s", user=employee.name
        )
        return time_data

    def set_qty_producing(self) -> None:
        self.check_singleton()
        self.production_id.set_qty_producing()

        current_check = self.check_ids.filtered(lambda c: not c.previous_check_id)[:1]
        while (
            current_check
            and current_check.next_check_id
            and (
                current_check.test_type != "register_production"
                or current_check.quality_state != "none"
            )
        ):
            current_check = current_check.next_check_id

        if (
            current_check
            and current_check.test_type == "register_production"
            and current_check.quality_state == "none"
        ):
            current_check.action_next()
        elif not any(c.test_type == "register_production" for c in self.check_ids):
            first_check = self.check_ids.filtered(lambda c: not c.previous_check_id)
            new_check = self.env["quality.check"].create(
                [
                    {
                        "title": self.env._("Register Production"),
                        "test_type_id": self.env.ref(
                            "mrp_workorder.test_type_register_production"
                        ).id,
                        "workorder_id": self.id,
                        "quality_state": "pass",
                        "production_id": self.production_id.id,
                        "product_id": self.product_id.id,
                        "trace_ids": self.production_id.trace_producing_ids.ids,
                        "team_id": self.env["team.team"]._get_quality_team(
                            self.env["team.team"]._get_domain_company_compatible(
                                self.company_id.id
                                or self.env.context.get(
                                    "default_company_id", self.env.company.id
                                )
                            )
                        ),
                    }
                ]
            )
            if first_check:
                new_check._insert_in_chain("before", first_check)
            else:
                self.current_quality_check_id = new_check

    def _get_connected_employee(self):
        if not self.env.context.get("mrp_display") and self.employee_assigned_ids:
            return self.employee_assigned_ids[0]
        return self._get_acting_employee()

    def _get_acting_employee(self):
        Employee = self.env["hr.employee"]
        if self.env.context.get("mrp_display"):
            return Employee.browse(
                self.env.context.get("employee_id") or Employee.get_session_owner()
            )
        return self.env.user.employee_id
