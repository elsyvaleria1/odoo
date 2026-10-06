from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardQualityCheckDecide(models.TransientModel):
    _name = "wizard.quality.check.decide"
    _inherit = ["mixin.stock.picking.validation"]
    _description = "Wizard for Quality Check Pop Up"

    check_ids = fields.Many2many(
        comodel_name="quality.check",
        required=True,
    )
    current_check_id = fields.Many2one(
        comodel_name="quality.check",
        required=True,
    )
    nb_checks = fields.Count(count_of="check_ids")
    position_current_check = fields.Integer(compute="_compute_position")
    is_last_check = fields.Boolean(compute="_compute_position")
    failure_location_id = fields.Many2one(
        comodel_name="stock.location",
        compute="_compute_failure_location_id",
        store=True,
        readonly=False,
    )
    qty_failed = fields.Float()

    # fields linked to the current_check_id
    potential_failure_location_ids = fields.Many2many(
        related="current_check_id.point_id.failure_location_ids"
    )
    name = fields.Char(related="current_check_id.name")
    title = fields.Char(related="current_check_id.title")
    product_id = fields.Many2one(related="current_check_id.product_id")
    lot_name = fields.Char(related="current_check_id.lot_name")
    trace_line_id = fields.Many2one(related="current_check_id.trace_line_id")
    qty_line = fields.Float(related="current_check_id.qty_line")
    qty_to_test = fields.Float(related="current_check_id.qty_to_test")
    qty_tested = fields.Float(
        related="current_check_id.qty_tested",
        readonly=False,
    )
    measure = fields.Float(
        related="current_check_id.measure",
        readonly=False,
    )
    measure_on = fields.Selection(related="current_check_id.measure_on")
    quality_state = fields.Selection(related="current_check_id.quality_state")
    test_type = fields.Char(related="current_check_id.test_type")
    norm_unit = fields.Char(related="current_check_id.norm_unit")
    picture = fields.Binary(
        related="current_check_id.picture",
        readonly=False,
    )
    note = fields.Html(
        related="current_check_id.note",
        readonly=False,
    )
    additional_note = fields.Text(
        related="current_check_id.additional_note",
        readonly=False,
    )
    is_lot_tested_fractionally = fields.Boolean(
        related="current_check_id.is_lot_tested_fractionally"
    )
    testing_percentage_within_lot = fields.Float(
        related="current_check_id.testing_percentage_within_lot"
    )
    uom_id = fields.Many2one(related="current_check_id.uom_id")
    warning_message = fields.Text(related="current_check_id.warning_message")
    failure_message = fields.Html(related="current_check_id.failure_message")
    show_lot_text = fields.Boolean(related="current_check_id.show_lot_text")
    product_tracking = fields.Selection(related="current_check_id.product_tracking")

    @api.depends("potential_failure_location_ids")
    def _compute_failure_location_id(self) -> None:
        for wz in self:
            if len(wz.potential_failure_location_ids) == 1:
                wz.failure_location_id = wz.potential_failure_location_ids

    @api.depends("current_check_id", "check_ids")
    def _compute_position(self) -> None:
        for wz in self:
            check_ids = wz.check_ids.ids
            # `.index()` raises ValueError rather than rendering the wizard;
            # a current check that is not in the list is one of one.
            position = (
                check_ids.index(wz.current_check_id.id) + 1
                if wz.current_check_id.id in check_ids
                else 1
            )
            wz.position_current_check = position
            wz.is_last_check = position >= len(check_ids)

    def do_measure(self):
        # `quality.check.do_measure` grades; the wizard only decides which of
        # its own two buttons the verdict corresponds to.
        _debug.pipeline("quality_check_measure", wizards=self)
        self.check_singleton()
        if self.current_check_id._measure_passes():
            return self.do_pass()
        return self.do_fail()

    def confirm_measure(self):
        _debug.pipeline("quality_check_measure_confirm", wizards=self)
        self.current_check_id.do_measure()
        self.current_check_id._move_to_failure_location(
            self.failure_location_id.id, self.qty_failed
        )
        return self.action_generate_next_window()

    def do_pass(self):
        _debug.lifecycle("quality_check_pass", wizards=self)
        if self.test_type == "picture" and not self.picture:
            raise UserError(self.env._("You must provide a picture before validating"))
        self.current_check_id.do_pass()
        return self.action_generate_next_window()

    def do_fail(self):
        _debug.lifecycle("quality_check_fail", wizards=self)
        if self.potential_failure_location_ids:
            return self.show_failure_message()
        if self.measure_on == "move_line":
            if self.product_tracking == "serial":
                self.qty_failed = self.qty_line
            else:
                return self.show_failure_message()
        if self.failure_message or self.warning_message:
            self.current_check_id.do_fail()
            return self.show_failure_message()
        return self.confirm_fail()

    def confirm_fail(self):
        self.current_check_id.do_fail()
        self.current_check_id._move_to_failure_location(
            self.failure_location_id.id, self.qty_failed
        )
        return self.action_generate_next_window()

    def action_generate_next_window(self):
        action = {"type": "ir.actions.act_window_close"}
        if not self.is_last_check:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "quality_control.action_quality_check_wizard"
            )
            check_id = self.check_ids[self.position_current_check]
            action["name"] = check_id._get_check_action_name()
            action["context"] = dict(
                self.env["ir.actions.actions"]._eval_action_context(action["context"])
            )
            action["context"].update(
                self.env.context,
                default_current_check_id=check_id.id,
                from_failure_form=False,
                default_qty_tested=check_id.qty_to_test,
            )
        if self._get_pickings_to_validate():
            validate_action = self._resume_validation()
            if (
                validate_action is not True
                and validate_action.get("xml_id")
                != "quality_control.action_quality_check_wizard"
            ):
                return validate_action
        return action

    def action_generate_previous_window(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.action_quality_check_wizard"
        )
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(action["context"])
        )
        if self.env.context.get("from_failure_form"):
            check_id = self.current_check_id
        else:
            check_id = self.check_ids[self.position_current_check - 2]
        action["name"] = check_id._get_check_action_name()
        action["context"].update(
            self.env.context,
            default_current_check_id=check_id.id,
            from_failure_form=False,
            default_qty_tested=check_id.qty_to_test,
        )
        return action

    def action_view_spreadsheet(self):
        action = self.current_check_id.action_view_spreadsheet()
        action["context"] = self.env.context
        action["params"]["quality_check_wizard_id"] = self.id
        return action

    def show_failure_message(self) -> dict:
        self.qty_failed = self.qty_line
        # No trailing comma: both branches used to build a one-element *tuple*,
        # and the dialog was titled `('Quality Check Failed',)`.  The product
        # name is only used when there is one -- an operation check has none,
        # and so does a product check whose product was never set, which the
        # old `measure_on` test did not cover.
        if self.product_id:
            name = self.env._(
                "Quality Check Failed for %(product_name)s",
                product_name=self.product_id.display_name,
            )
        else:
            name = self.env._("Quality Check Failed")
        return {
            "name": name,
            "type": "ir.actions.act_window",
            "res_model": "wizard.quality.check.decide",
            "views": [
                (
                    self.env.ref(
                        "quality_control.quality_check_wizard_form_failure"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
            "res_id": self.id,
            "context": {
                **self.env.context,
                "from_failure_form": True,
            },
        }

    def correct_measure(self):
        self.current_check_id.quality_state = "none"
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "quality_control.action_quality_check_wizard"
        )
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(action["context"])
        )
        action["context"].update(
            self.env.context,
            default_check_ids=self.check_ids.ids,
            default_current_check_id=self.current_check_id.id,
            from_failure_form=False,
        )
        return action
