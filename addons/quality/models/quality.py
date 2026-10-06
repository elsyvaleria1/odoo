from itertools import zip_longest
from typing import Self

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict


def _update_sequence_names(env, vals_list, sequence_code) -> None:
    """Name every vals dict that has no real name yet from `sequence_code`.

    `ir.sequence.next_by_code` searches for the sequence *and* draws one value,
    so naming a batch of records one at a time cost two round trips each --
    measured on a 25-line receipt, 50 of the 79 queries `action_confirm` spent
    were these.  `next_by_code_batch` does the search once and the draw once.
    """
    new_name = env._("New")
    todo = [
        vals for vals in vals_list if "name" not in vals or vals["name"] == new_name
    ]
    if not todo:
        return
    names = env["ir.sequence"].next_by_code_batch(sequence_code, len(todo)) or []
    for vals, name in zip_longest(todo, names):
        vals["name"] = name or new_name


_debug = DebugLog(__name__)


class QualityPointTest_Type(models.Model):
    _name = "quality.point.test_type"
    _access_anchors = frozendict({"company": ""})
    _description = "Quality Control Test Type"

    # Used instead of selection field in order to hide a choice depending on the view.
    name = fields.Char(
        translate=True,
        required=True,
    )
    technical_name = fields.Char(
        string="Technical name",
        required=True,
    )
    active = fields.Boolean(
        string="active",
        default=True,
    )

    @api.model
    def _get_default(self) -> Self:
        """The test type a new quality point or check falls back to.

        One implementation for the two of them: `quality.point` and
        `quality.check` each carried a `_get_default_test_type_id` *and* a
        `_get_domain_default`, so every module narrowing the default had
        to override the same thing four times.
        """
        return self.search(self._get_domain_default(), limit=1)

    @api.model
    def _get_domain_default(self):
        return Domain.TRUE


class QualityPoint(models.Model):
    _name = "quality.point"
    _description = "Quality Control Point"
    _inherit = ["mixin.mail.thread"]
    _order = "sequence, id"
    _check_company_auto = True

    def _get_default_team_id(self):
        return self.env["team.team"]._get_default_quality_team_for(self)

    def _get_default_test_type_id(self):
        return self.env["quality.point.test_type"]._get_default().id

    name = fields.Char(
        string="Reference",
        default=lambda self: self.env._("New"),
        copy=False,
        required=True,
    )
    sequence = fields.Integer()
    title = fields.Char(tracking=True)
    team_id = fields.Many2one(
        comodel_name="team.team",
        default=lambda self: self._get_default_team_id(),
        required=True,
        domain=[("use_quality", "=", True)],
        check_company=True,
        tracking=True,
    )
    product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Products",
        domain="[('type', '=', 'consu')]",
        check_company=True,
        tracking=True,
        help="Quality Point will apply to every selected Products.",
    )
    product_category_ids = fields.Many2many(
        comodel_name="product.category",
        string="Product Categories",
        tracking=True,
        help="Quality Point will apply to every Products in the selected Product Categories.",
    )

    picking_type_ids = fields.Many2many(
        comodel_name="stock.picking.type",
        string="Operation Types",
        required=True,
        check_company=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        domain=lambda self: [
            ("all_group_ids", "in", self.env.ref("quality.group_quality_user").id),
            ("share", "=", False),
        ],
        check_company=True,
    )
    active = fields.Boolean(
        default=True,
        tracking=True,
    )
    check_count = fields.Integer(compute="_compute_check_count")
    check_ids = fields.One2many(
        comodel_name="quality.check",
        inverse_name="point_id",
    )
    test_type_id = fields.Many2one(
        comodel_name="quality.point.test_type",
        default=lambda self: self._get_default_test_type_id(),
        required=True,
        tracking=True,
        help="Defines the type of the quality control point.",
    )
    test_type = fields.Char(
        related="test_type_id.technical_name",
        readonly=True,
    )
    note = fields.Html()
    reason = fields.Html(string="Cause")
    failure_location_ids = fields.Many2many(
        comodel_name="stock.location",
        string="Failure Locations",
        domain="[('usage', '=', 'internal')]",
        tracking=True,
        help="If quality check fails, a destination location is chosen from this list for\n"
        "- each failed specific product quantity if control is per quantity\n /"
        "- all quantities of a product if control is per product\n /"
        "- all quantities of products in the operation if control is per operation",
    )
    show_failure_location = fields.Boolean(compute="_compute_show_failure_location")

    @api.depends("check_ids")
    def _compute_check_count(self) -> None:
        _debug.perf.count("quality_check_count_compute", points=self)
        check_data = self.env["quality.check"]._read_group(
            [("point_id", "in", self.ids)], ["point_id"], ["__count"]
        )
        result = {point.id: count for point, count in check_data}
        for point in self:
            point.check_count = result.get(point.id, 0)

    @api.depends("test_type")
    def _compute_show_failure_location(self) -> None:
        for point in self:
            point.show_failure_location = point.test_type not in [
                "instructions",
                "picture",
            ]

    @api.model_create_multi
    def create(self, vals_list):
        _debug.lifecycle("quality_point_create", count=len(vals_list))
        _update_sequence_names(self.env, vals_list, "quality.point")
        return super().create(vals_list)

    def check_execute_now(self):
        """Whether this point should produce a check right now.

        Single-record by contract: `quality_control` answers `periodical` with
        a query over this point's own checks, and `random` with a draw per
        point.
        """
        _debug.pipeline("quality_check_execute_now", points=self)
        self.check_singleton()
        return True

    def _is_check_execution_sampled(self) -> bool:
        """True when `check_execute_now` draws a fresh answer on every call.

        A sampled point has to be asked once per prospective check.  Any other
        answers the same thing for a whole batch, so the caller can ask once --
        which matters because the batch is one call per *move line*.
        """
        _debug.logic("quality_check_sampled", points=self)
        self.check_singleton()
        return False

    def _get_execute_now_by_point(self) -> dict:
        """`{point id: verdict}` for the points that answer the same every time.

        Sampled points are deliberately absent: the caller must keep asking
        them per check, and `_is_execution_required` does.
        """
        _debug.logic("quality_check_by_point", points=self)
        return {
            point.id: point.check_execute_now()
            for point in self
            if not point._is_check_execution_sampled()
        }

    def _is_execution_required(self, settled) -> bool:
        """Whether to raise a check for this point now, reusing a settled verdict."""
        _debug.logic("quality_execution_required", points=self, settled=settled)
        self.check_singleton()
        if self.id in settled:
            return bool(settled[self.id])
        return bool(self.check_execute_now())


class QualityReason(models.Model):
    _name = "quality.reason"
    _access_anchors = frozendict({"company": ""})
    _description = "Root Cause for Quality Failure"

    name = fields.Char(
        translate=True,
        required=True,
    )


class QualityTag(models.Model):
    _name = "quality.tag"
    _access_anchors = frozendict({"company": ""})
    _description = "Quality Tag"

    name = fields.Char(
        string="Tag Name",
        required=True,
    )
    color = fields.Integer(
        string="Color Index",
        help="Used in the kanban view",
    )


class QualityAlertStage(models.Model):
    _name = "quality.alert.stage"
    _access_anchors = frozendict({"company": ""})
    _description = "Quality Alert Stage"
    _order = "sequence, id"
    _fold_name = "folded"

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer()
    folded = fields.Boolean()
    done = fields.Boolean(string="Alert Processed")
    team_ids = fields.Many2many(
        comodel_name="team.team",
        string="Teams",
        domain=[("use_quality", "=", True)],
    )


class QualityCheck(models.Model):
    _name = "quality.check"
    _description = "Quality Check"
    _order = "point_id, id"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _check_company_auto = True

    def _get_default_team_id(self):
        return self.env["team.team"]._get_default_quality_team_for(self)

    def _get_default_test_type_id(self):
        return self.env["quality.point.test_type"]._get_default().id

    name = fields.Char(
        string="Reference",
        copy=False,
    )
    point_id = fields.Many2one(
        comodel_name="quality.point",
        string="Control Point",
        index="btree_not_null",
        check_company=True,
    )
    title = fields.Char(
        compute="_compute_title",
        store=True,
        readonly=False,
    )
    quality_state = fields.Selection(
        selection=[("none", "To do"), ("pass", "Passed"), ("fail", "Failed")],
        string="Status",
        default="none",
        copy=False,
        tracking=True,
    )
    control_date = fields.Datetime(
        copy=False,
        tracking=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        index="btree_not_null",
        domain="[('type', '=', 'consu')]",
        check_company=True,
    )
    product_tracking = fields.Selection(related="product_id.tracking")
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        index="btree_not_null",
        check_company=True,
    )
    partner_id = fields.Many2one(
        related="picking_id.partner_id",
        string="Partner",
    )
    trace_ids = fields.Many2many(
        comodel_name="product.trace",
        string="Lot/Serial",
        domain="[('product_id', '=', product_id)]",
        check_company=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        tracking=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        compute="_compute_team_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        required=True,
        domain=[("use_quality", "=", True)],
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    alert_ids = fields.One2many(
        comodel_name="quality.alert",
        inverse_name="check_id",
        string="Alerts",
    )
    alert_count = fields.Integer(
        string="# Quality Alerts",
        compute="_compute_alert_count",
    )
    note = fields.Html(
        compute="_compute_note",
        store=True,
        readonly=False,
    )
    test_type_id = fields.Many2one(
        comodel_name="quality.point.test_type",
        compute="_compute_test_type_id",
        precompute=True,
        store=True,
        copy=True,
        readonly=False,
        required=True,
    )
    test_type = fields.Char(related="test_type_id.technical_name")
    picture = fields.Binary(attachment=True)
    additional_note = fields.Text(help="Additional remarks concerning this check.")
    failure_location_id = fields.Many2one(comodel_name="stock.location")

    @api.depends("alert_ids")
    def _compute_alert_count(self) -> None:
        alert_data = self.env["quality.alert"]._read_group(
            [("check_id", "in", self.ids)], ["check_id"], ["__count"]
        )
        alert_result = {check.id: count for check, count in alert_data}
        for check in self:
            check.alert_count = alert_result.get(check.id, 0)

    @api.depends("point_id")
    def _compute_title(self) -> None:
        for check in self:
            if check.point_id:
                check.title = check.point_id.title
            else:
                check.title = False

    @api.depends("point_id")
    def _compute_note(self) -> None:
        for check in self:
            if check.point_id:
                check.note = check.point_id.note
            else:
                check.note = False

    @api.depends("point_id")
    def _compute_team_id(self) -> None:
        for check in self:
            if check.point_id:
                check.team_id = check.point_id.team_id.id
            else:
                check.team_id = check._get_default_team_id()

    @api.depends("point_id")
    def _compute_test_type_id(self) -> None:
        # `_get_default_test_type_id` searches; hoisted out of the loop so a
        # batch of point-less checks costs one search instead of one each.
        default_test_type_id = None
        for check in self:
            if check.point_id:
                check.test_type_id = check.point_id.test_type_id.id
            else:
                if default_test_type_id is None:
                    default_test_type_id = check._get_default_test_type_id()
                check.test_type_id = default_test_type_id

    def _is_pass_fail_applicable(self) -> bool:
        """Return true if do_fail and do_pass can be applied."""
        return False

    @api.model_create_multi
    def create(self, vals_list):
        _update_sequence_names(self.env, vals_list, "quality.check")
        return super().create(vals_list)

    def write(self, vals):
        quality_state = vals.get("quality_state")
        if quality_state in ("pass", "fail"):
            # Closing a check records who closed it and when -- unless the
            # caller said.  The old guard read `not vals.get('control_date')`,
            # which is true of nearly every write, and answered it by calling
            # `do_pass` / `do_fail`, which wrote a second time and overwrote
            # an author that had just been supplied.
            vals = {
                "user_id": self.env.user.id,
                "control_date": fields.Datetime.now(),
                **vals,
            }
        res = super().write(vals)
        if quality_state in ("pass", "fail"):
            # `_on_pass` / `_on_fail` are what the bridge modules extend, and
            # they hang off the write rather than off `do_pass` / `do_fail` so
            # that a bare `quality_state = 'pass'` reaches them as well --
            # `mrp_workorder.check_quality_checks` does exactly that, and
            # relies on the move being picked afterwards.
            if quality_state == "pass":
                self._on_pass()
            else:
                self._on_fail()
        return res

    def do_fail(self):
        return self.write({"quality_state": "fail"})

    def do_pass(self):
        return self.write({"quality_state": "pass"})

    def _on_pass(self):
        """The checks in `self` have just been marked passed.

        Extension point for the bridge modules; the state is already written
        when this runs.  Multi-record by contract.
        """

    def _on_fail(self):
        """The checks in `self` have just been marked failed."""


class QualityAlert(models.Model):
    _name = "quality.alert"
    _description = "Quality Alert"
    _inherit = ["mixin.mail.thread.cc", "mixin.mail.activity"]
    _check_company_auto = True

    def _get_team_id_from_context(self):
        """The team the current action is scoped to, if any.

        Both the default stage and the kanban group expansion need it, and
        both had their own copy of this three-line lookup.
        """
        team_id = self.env.context.get("default_team_id")
        if (
            not team_id
            and self.env.context.get("active_model") == "team.team"
            and self.env.context.get("active_id")
        ):
            team_id = self.env.context["active_id"]
        # default_team_id is shared with every other usage's documents
        return (
            self.env["team.team"]
            .browse(team_id or ())
            .exists()
            .filtered("use_quality")
            .id
        )

    def _default_stage_id(self):
        """Gives default stage_id"""
        domain = Domain("team_ids", "=", False)
        if team_id := self._get_team_id_from_context():
            domain &= Domain("team_ids", "in", team_id)
        return self.env["quality.alert.stage"].search(domain, limit=1).id

    def _get_default_team_id(self):
        return self.env["team.team"]._get_default_quality_team_for(self)

    name = fields.Char(
        default=lambda self: self.env._("New"),
        copy=False,
    )
    description = fields.Html()
    stage_id = fields.Many2one(
        comodel_name="quality.alert.stage",
        default=lambda self: self._default_stage_id(),
        group_expand="_read_group_stage_ids",
        domain="['|', ('team_ids', '=', False), ('team_ids', 'in', team_id)]",
        ondelete="restrict",
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    reason_id = fields.Many2one(
        comodel_name="quality.reason",
        string="Root Cause",
    )
    tag_ids = fields.Many2many(
        comodel_name="quality.tag",
        string="Tags",
    )
    date_assign = fields.Datetime(string="Date Assigned")
    date_close = fields.Datetime(string="Date Closed")
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        index="btree_not_null",
        check_company=True,
    )
    action_corrective = fields.Html(string="Corrective Action")
    action_preventive = fields.Html(string="Preventive Action")
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        tracking=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        default=lambda self: self._get_default_team_id(),
        index=True,
        required=True,
        domain=[("use_quality", "=", True)],
        check_company=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Vendor",
        check_company=True,
    )
    check_id = fields.Many2one(
        comodel_name="quality.check",
        index="btree_not_null",
        check_company=True,
    )
    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product",
        domain="[('type', '=', 'consu')]",
        check_company=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product Variant",
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
    )
    trace_ids = fields.Many2many(
        comodel_name="product.trace",
        domain="['|', ('product_id', '=', product_id), ('product_id.product_tmpl_id', '=', product_tmpl_id)]",
        check_company=True,
    )
    priority = fields.Selection(
        selection=[("0", "Normal"), ("1", "Low"), ("2", "High"), ("3", "Very High")],
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        _update_sequence_names(self.env, vals_list, "quality.alert")
        return super().create(vals_list)

    def write(self, vals):
        if "stage_id" in vals and "date_close" not in vals:
            # A stage flagged `done` closes the alert.  The old code only ever
            # set the date, from a second, re-entrant `write`, so an alert
            # pulled back out of a done stage kept a close date it no longer
            # had -- and `self.stage_id` was read across the whole recordset.
            stage = self.env["quality.alert.stage"].browse(vals["stage_id"])
            vals = dict(vals, date_close=fields.Datetime.now() if stage.done else False)
        return super().write(vals)

    @api.onchange("product_tmpl_id")
    def onchange_product_tmpl_id(self) -> None:
        self.product_id = (
            self.product_tmpl_id.product_variant_ids.ids
            and self.product_tmpl_id.product_variant_ids.ids[0]
        )

    @api.onchange("team_id")
    def onchange_team_id(self) -> None:
        if self.team_id:
            self.company_id = self.team_id.company_id or self.env.company

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Show stages for the current team, plus any stage with no team."""
        team_id = self._get_team_id_from_context()
        domain = Domain("id", "in", stages.ids) | Domain("team_ids", "=", False)
        if team_id:
            domain |= Domain("team_ids", "in", team_id)
        stage_ids = stages.sudo()._search(domain, order=stages._order)
        return stages.browse(stage_ids)
