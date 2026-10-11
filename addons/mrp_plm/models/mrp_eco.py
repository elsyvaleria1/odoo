from collections import defaultdict

from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpEcoType(models.Model):
    _name = "mrp.eco.type"
    _description = "ECO Type"
    _inherit = ["mixin.mail.alias", "mixin.mail.thread"]

    _order = "sequence, id"

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer()
    nb_ecos = fields.Integer(
        string="ECOs",
        compute="_compute_nb",
    )
    nb_approvals = fields.Integer(
        string="Waiting Approvals",
        compute="_compute_nb",
    )
    nb_approvals_my = fields.Integer(
        string="Waiting my Approvals",
        compute="_compute_nb",
    )
    nb_validation = fields.Integer(
        string="To Apply",
        compute="_compute_nb",
    )
    color = fields.Integer(default=1)
    stage_ids = fields.Many2many(
        comodel_name="mrp.eco.stage",
        relation="mrp_eco_stage_type_rel",
        column1="type_id",
        column2="stage_id",
        string="Stages",
    )

    def _compute_nb(self) -> None:
        MrpEco = self.env["mrp.eco"]
        nb_ecos = {
            eco_type.id: count
            for eco_type, count in MrpEco._read_group(
                [("type_id", "in", self.ids), ("state", "!=", "done")],
                ["type_id"],
                ["__count"],
            )
        }
        nb_validation = {
            eco_type.id: count
            for eco_type, count in MrpEco._read_group(
                [
                    ("type_id", "in", self.ids),
                    ("stage_id.allow_apply_change", "=", True),
                    ("state", "=", "progress"),
                ],
                ["type_id"],
                ["__count"],
            )
        }
        nb_approvals = {
            eco_type.id: count
            for eco_type, count in MrpEco._read_group(
                [
                    ("type_id", "in", self.ids),
                    ("approval_request_ids.state", "=", "pending"),
                ],
                ["type_id"],
                ["__count"],
            )
        }
        nb_approvals_my = {
            eco_type.id: count
            for eco_type, count in MrpEco._read_group(
                [
                    ("type_id", "in", self.ids),
                    ("awaiting_my_validation", "=", True),
                ],
                ["type_id"],
                ["__count"],
            )
        }

        for eco_type in self:
            eco_type.nb_ecos = nb_ecos.get(eco_type.id, 0)
            eco_type.nb_validation = nb_validation.get(eco_type.id, 0)
            eco_type.nb_approvals = nb_approvals.get(eco_type.id, 0)
            eco_type.nb_approvals_my = nb_approvals_my.get(eco_type.id, 0)

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values["alias_model_id"] = self.env["ir.model"]._get("mrp.eco").id
        if self.id:
            values["alias_defaults"] = defaults = self._prepare_alias_defaults()
            defaults["type_id"] = self.id
        return values


class MrpEcoApprovalTemplate(models.Model):
    _name = "mrp.eco.approval.template"
    _order = "sequence"
    _description = "ECO Approval Template"

    name = fields.Char(
        string="Role",
        required=True,
    )
    sequence = fields.Integer()
    approval_type = fields.Selection(
        selection=[
            ("optional", "Approves, but the approval is optional"),
            ("mandatory", "Is required to approve"),
            ("comment", "Comments only"),
        ],
        default="mandatory",
        index=True,
        required=True,
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Users",
        required=True,
        domain=lambda self: [
            ("all_group_ids", "in", self.env.ref("mrp_plm.group_plm_user").id)
        ],
    )
    stage_id = fields.Many2one(
        comodel_name="mrp.eco.stage",
        index=True,
        required=True,
    )
    step_id = fields.Many2one(
        comodel_name="approval.category.step",
        copy=False,
        readonly=True,
        ondelete="set null",
        help="The approval step this role asks and counts through",
    )

    @api.constrains("user_ids", "stage_id")
    def _check_unique_user_stage(self) -> None:
        domain = Domain.OR(
            [
                [
                    ("id", "!=", record.id),
                    ("stage_id", "=", record.stage_id.id),
                    ("user_ids", "in", record.user_ids.ids),
                ]
                for record in self.filtered("user_ids")
            ]
        )
        duplicate = self.env["mrp.eco.approval.template"].search_count(domain, limit=1)
        if duplicate:
            raise ValidationError(
                self.env._("A user cannot be assigned more than once to the same stage")
            )

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._sync_approval_step()
        return templates

    def write(self, vals):
        result = super().write(vals)
        if {"name", "sequence", "approval_type", "user_ids", "stage_id"} & set(vals):
            self._sync_approval_step()
        return result

    def unlink(self):
        steps = self.sudo().step_id
        result = super().unlink()
        steps.exists().unlink()
        return result

    def _prepare_approval_step_values(self) -> dict:
        self.check_singleton()
        return {
            "category_id": self.env.ref("mrp_plm.approval_category_eco").id,
            "name": self.name,
            "sequence": self.stage_id.sequence * 100 + (self.sequence or 0),
            "minimum": 1,
            "advisory": self.approval_type != "mandatory",
            "user_ids": [Command.set(self.user_ids.ids)],
            "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
            "subject_model_id": self.env["ir.model"]._get_id("mrp.eco"),
            "subject_domain": repr([("stage_id", "=", self.stage_id.id)]),
        }

    def _sync_approval_step(self) -> None:
        for template in self.sudo():
            values = template._prepare_approval_step_values()
            if template.step_id:
                template.step_id.write(values)
            else:
                template.step_id = self.env["approval.category.step"].create(values)


class MrpEcoStage(models.Model):
    _name = "mrp.eco.stage"
    _description = "ECO Stage"
    _order = "sequence, id"
    _fold_name = "folded"

    @api.model
    def _get_sequence(self):
        others = self.search(
            [("sequence", "!=", False)], order="sequence desc", limit=1
        )
        if others:
            return (others[0].sequence or 0) + 1
        return 1

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=lambda self: self._get_sequence())
    folded = fields.Boolean(string="Folded in kanban view")
    allow_apply_change = fields.Boolean(
        string="Allow to apply changes",
        help="Allow to apply changes from this stage.",
    )
    final_stage = fields.Boolean(
        help="Once the changes are applied, the ECOs will be moved to this stage."
    )
    type_ids = fields.Many2many(
        comodel_name="mrp.eco.type",
        relation="mrp_eco_stage_type_rel",
        column1="stage_id",
        column2="type_id",
        string="Types",
        required=True,
    )
    approval_template_ids = fields.One2many(
        comodel_name="mrp.eco.approval.template",
        inverse_name="stage_id",
        string="Approvals",
    )
    approval_roles = fields.Char(
        compute="_compute_approvals",
        store=True,
    )
    is_blocking = fields.Boolean(
        string="Blocking Stage",
        compute="_compute_is_blocking",
        store=True,
    )
    legend_blocked = fields.Char(
        string="Red Kanban Label",
        translate=True,
        default=lambda s: s.env._("Blocked"),
        required=True,
        help="Override the default value displayed for the blocked state for kanban selection, when the ECO is in that stage.",
    )
    legend_done = fields.Char(
        string="Green Kanban Label",
        translate=True,
        default=lambda s: s.env._("Ready"),
        required=True,
        help="Override the default value displayed for the done state for kanban selection, when the ECO is in that stage.",
    )
    legend_normal = fields.Char(
        string="Grey Kanban Label",
        translate=True,
        default=lambda s: s.env._("In Progress"),
        required=True,
        help="Override the default value displayed for the normal state for kanban selection, when the ECO is in that stage.",
    )
    description = fields.Text(help="Description and tooltips of the stage states.")

    @api.depends("approval_template_ids.name")
    def _compute_approvals(self) -> None:
        for rec in self:
            rec.approval_roles = ", ".join(rec.approval_template_ids.mapped("name"))

    @api.depends("approval_template_ids.approval_type")
    def _compute_is_blocking(self) -> None:
        for rec in self:
            rec.is_blocking = any(
                template.approval_type == "mandatory"
                for template in rec.approval_template_ids
            )


class MrpEco(models.Model):
    _name = "mrp.eco"
    _description = "Engineering Change Order (ECO)"
    _inherit = [
        "mixin.mail.thread.cc",
        "mixin.mail.activity",
        "mixin.approval.subjects",
    ]

    @api.model
    def _get_type_selection(self) -> list:
        return [
            ("bom", self.env._("Bill of Materials")),
            ("product", self.env._("Product Only")),
        ]

    name = fields.Char(
        string="Reference",
        copy=False,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        check_company=True,
        tracking=True,
    )
    type_id = fields.Many2one(
        comodel_name="mrp.eco.type",
        required=True,
    )
    stage_id = fields.Many2one(
        comodel_name="mrp.eco.stage",
        default=lambda self: self.env["mrp.eco.stage"].search(
            [("type_ids", "in", self.env.context.get("default_type_id"))], limit=1
        ),
        copy=False,
        group_expand="_read_group_stage_ids",
        domain="[('type_ids', 'in', type_id)]",
        ondelete="restrict",
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    tag_ids = fields.Many2many(
        comodel_name="mrp.eco.tag",
        string="Tags",
    )
    priority = fields.Selection(
        selection=[("0", "Normal"), ("1", "High")],
        index=True,
        tracking=True,
    )
    note = fields.Html()
    effectivity = fields.Selection(
        selection=[("asap", "As soon as possible"), ("date", "At Date")],
        string="Effective",
        compute="_compute_effectivity",
        inverse="_inverse_effectivity",
        store=True,
        help="Date on which the changes should be applied. For reference only.",
    )
    effectivity_date = fields.Datetime(
        string="Effective Date",
        tracking=True,
        help="For reference only.",
    )
    awaiting_my_validation = fields.Boolean(
        compute="_compute_awaiting_my_validation",
        search="_search_awaiting_my_validation",
        help="The stage's approval request asks the current user and is still waiting",
    )
    approval_approver_ids = fields.Many2many(
        comodel_name="approval.approver",
        string="Approvals",
        compute="_compute_approval_approver_ids",
        help="Every role's decision on this change, stage by stage",
    )

    state = fields.Selection(
        selection=[
            ("confirmed", "To Do"),
            ("progress", "In Progress"),
            ("rebase", "Rebase"),
            ("conflict", "Conflict"),
            ("done", "Done"),
        ],
        string="Status",
        default="confirmed",
        index=True,
        copy=False,
        readonly=True,
        required=True,
    )
    user_can_approve = fields.Boolean(
        string="Can Approve",
        compute="_compute_user_approval",
        help="Technical field to check if approval by current user is required",
    )
    user_can_reject = fields.Boolean(
        string="Can Reject",
        compute="_compute_user_approval",
        help="Technical field to check if reject by current user is possible",
    )
    kanban_state = fields.Selection(
        selection=[
            ("normal", "In Progress"),
            ("done", "Approved"),
            ("blocked", "Blocked"),
        ],
        compute="_compute_kanban_state",
        store=True,
        copy=False,
        readonly=False,
    )
    legend_blocked = fields.Char(
        related="stage_id.legend_blocked",
        string="Kanban Blocked Explanation",
        related_sudo=False,
    )
    legend_done = fields.Char(
        related="stage_id.legend_done",
        string="Kanban Valid Explanation",
        related_sudo=False,
    )
    legend_normal = fields.Char(
        related="stage_id.legend_normal",
        string="Kanban Ongoing Explanation",
        related_sudo=False,
    )
    kanban_state_label = fields.Char(
        compute="_compute_kanban_state_label",
        tracking=True,
    )
    allow_change_kanban_state = fields.Boolean(
        compute="_compute_allow_change_kanban_state"
    )
    allow_change_stage = fields.Boolean(compute="_compute_allow_change_stage")
    allow_apply_change = fields.Boolean(
        string="Show Apply Change",
        compute="_compute_allow_apply_change",
    )

    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product",
        index="btree_not_null",
        check_company=True,
    )
    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Manufacturing Orders",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    type = fields.Selection(
        selection=_get_type_selection,
        string="Apply on",
        default="bom",
        required=True,
    )
    bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Bill of Materials",
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
        check_company=True,
    )
    new_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="New Bill of Materials",
        index="btree_not_null",
        copy=False,
    )
    new_bom_revision = fields.Integer(
        related="new_bom_id.version",
        string="BoM Revision",
        readonly=False,
    )
    will_update_version = fields.Boolean(
        string="Update Version",
        default=True,
        help="If unchecked, the version of the product/BoM will remain unchanged once the ECO is applied",
    )
    bom_change_ids = fields.One2many(
        comodel_name="mrp.eco.bom.change",
        inverse_name="eco_id",
        string="ECO BoM Changes",
        compute="_compute_bom_change_ids",
        store=True,
        help="Difference between old BoM and new BoM revision",
    )
    bom_change_ids_on_line = fields.One2many(
        comodel_name="mrp.eco.bom.change",
        inverse_name="eco_id",
        string="ECO BoM Changes - Component",
        domain=[("bom_line_id", "!=", False)],
    )
    bom_change_ids_on_byproduct = fields.One2many(
        comodel_name="mrp.eco.bom.change",
        inverse_name="eco_id",
        string="ECO BoM Changes - By-Product",
        domain=[("byproduct_id", "!=", False)],
    )
    bom_rebase_ids = fields.One2many(
        comodel_name="mrp.eco.bom.change",
        inverse_name="rebase_id",
        string="BoM Rebase",
    )
    routing_change_ids = fields.One2many(
        comodel_name="mrp.eco.routing.change",
        inverse_name="eco_id",
        string="ECO Routing Changes",
        compute="_compute_routing_change_ids",
        store=True,
        help="Difference between old operation and new operation revision",
    )
    document_count = fields.Count(
        count_of="document_ids",
        string="# Attachments",
    )
    document_ids = fields.One2many(
        comodel_name="document.document",
        inverse_name="res_id",
        string="Attachments",
        domain=lambda self: [("res_model", "=", self._name)],
        bypass_search_access=True,
    )
    displayed_image_id = fields.Many2one(
        comodel_name="document.document",
        domain="[('res_model', '=', 'mrp.eco'), ('res_id', '=', id), ('mimetype', 'ilike', 'image')]",
    )
    displayed_image_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        related="displayed_image_id.attachment_id",
        readonly=False,
    )
    color = fields.Integer()
    active = fields.Boolean(
        default=True,
        help="If the active field is set to False, it will allow you to hide the engineering change order without removing it.",
    )
    current_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="New Bom",
    )
    previous_change_ids = fields.One2many(
        comodel_name="mrp.eco.bom.change",
        inverse_name="eco_rebase_id",
        string="Previous ECO Changes",
        compute="_compute_previous_bom_change",
        store=True,
    )

    @api.depends("effectivity_date")
    def _compute_effectivity(self) -> None:
        for eco in self:
            eco.effectivity = "date" if eco.effectivity_date else "asap"

    def _inverse_effectivity(self) -> None:
        for eco in self:
            if eco.effectivity == "asap":
                eco.effectivity_date = False

    def _mark_rebase_conflicts(self, new_bom_lines, changes=None):
        reb_conflicts = self.env["mrp.eco.bom.change"]
        if changes is None:
            changes = self.env["mrp.eco.bom.change"]
        for reb_line in changes:
            new_line = new_bom_lines.get(reb_line.product_id, None)
            if new_line and (
                reb_line.old_operation_id,
                reb_line.old_uom_id,
                reb_line.old_product_qty,
            ) != (new_line.operation_id, new_line.product_uom_id, new_line.product_qty):
                reb_conflicts |= reb_line
        _debug.logic(
            "eco_conflict_scan",
            eco=self.id,
            changes=len(changes),
            conflicts=len(reb_conflicts),
        )
        reb_conflicts.write({"conflict": True})
        return reb_conflicts

    def _prepare_bom_change_commands(self, old_bom, new_bom):
        new_bom_commands = [Command.clear()]
        old_bom_lines = {line._get_sync_values(): line for line in old_bom.bom_line_ids}
        if new_bom:
            for new_line in new_bom.bom_line_ids:
                old_line = old_bom_lines.get(new_line._get_sync_values())
                if old_line:
                    old_bom_lines.pop(old_line._get_sync_values())
                    if (
                        new_line.product_uom_id != old_line.product_uom_id
                        or tools.float_compare(
                            new_line.product_qty,
                            old_line.product_qty,
                            precision_rounding=new_line.product_uom_id.rounding,
                        )
                    ):
                        new_bom_commands += [
                            Command.create(
                                {
                                    "change_type": "update",
                                    "product_id": new_line.product_id.id,
                                    "old_product_qty": old_line.product_qty,
                                    "new_product_qty": new_line.product_qty,
                                    "old_uom_id": old_line.product_uom_id.id,
                                    "new_uom_id": new_line.product_uom_id.id,
                                    "old_operation_id": old_line.operation_id.id,
                                    "new_operation_id": new_line.operation_id.id,
                                    "bom_line_id": new_line.id,
                                }
                            )
                        ]
                else:
                    new_bom_commands += [
                        Command.create(
                            {
                                "change_type": "add",
                                "product_id": new_line.product_id.id,
                                "new_product_qty": new_line.product_qty,
                                "new_uom_id": new_line.product_uom_id.id,
                                "new_operation_id": new_line.operation_id.id,
                                "bom_line_id": new_line.id,
                            }
                        )
                    ]
            for old_line in old_bom_lines.values():
                new_bom_commands += [
                    Command.create(
                        {
                            "change_type": "remove",
                            "product_id": old_line.product_id.id,
                            "old_product_qty": old_line.product_qty,
                            "old_uom_id": old_line.product_uom_id.id,
                            "old_operation_id": old_line.operation_id.id,
                            "bom_line_id": old_line.id,
                        }
                    )
                ]

        old_byproducts = {
            byproduct._get_sync_values(): byproduct
            for byproduct in old_bom.byproduct_ids
        }
        if new_bom:
            for new_byproduct in new_bom.byproduct_ids:
                old_byproduct = old_byproducts.get(new_byproduct._get_sync_values())
                if old_byproduct:
                    old_byproducts.pop(old_byproduct._get_sync_values())
                    if (
                        new_byproduct.product_uom_id != old_byproduct.product_uom_id
                        or tools.float_compare(
                            new_byproduct.product_qty,
                            old_byproduct.product_qty,
                            precision_rounding=new_byproduct.product_uom_id.rounding,
                        )
                    ):
                        new_bom_commands += [
                            Command.create(
                                {
                                    "change_type": "update",
                                    "product_id": new_byproduct.product_id.id,
                                    "old_product_qty": old_byproduct.product_qty,
                                    "new_product_qty": new_byproduct.product_qty,
                                    "old_uom_id": old_byproduct.product_uom_id.id,
                                    "new_uom_id": new_byproduct.product_uom_id.id,
                                    "old_operation_id": old_byproduct.operation_id.id,
                                    "new_operation_id": new_byproduct.operation_id.id,
                                    "byproduct_id": new_byproduct.id,
                                }
                            )
                        ]
                else:
                    new_bom_commands += [
                        Command.create(
                            {
                                "change_type": "add",
                                "product_id": new_byproduct.product_id.id,
                                "new_product_qty": new_byproduct.product_qty,
                                "new_uom_id": new_byproduct.product_uom_id.id,
                                "new_operation_id": new_byproduct.operation_id.id,
                                "byproduct_id": new_byproduct.id,
                            }
                        )
                    ]
            for old_byproduct in old_byproducts.values():
                new_bom_commands += [
                    Command.create(
                        {
                            "change_type": "remove",
                            "product_id": old_byproduct.product_id.id,
                            "old_product_qty": old_byproduct.product_qty,
                            "old_uom_id": old_byproduct.product_uom_id.id,
                            "old_operation_id": old_byproduct.operation_id.id,
                            "byproduct_id": old_byproduct.id,
                        }
                    )
                ]

        return new_bom_commands

    def rebase(self, old_bom_lines, new_bom_lines, rebase_lines) -> bool:
        for reb_line in rebase_lines:
            new_bom_line = new_bom_lines.get(reb_line.product_id, None)
            if new_bom_line:
                if new_bom_line.product_qty + reb_line.upd_product_qty > 0.0:
                    new_bom_line.write(
                        {
                            "product_qty": new_bom_line.product_qty
                            + reb_line.upd_product_qty,
                            "product_uom_id": reb_line.new_uom_id.id,
                            "operation_id": reb_line.new_operation_id.id,
                        }
                    )
                else:
                    new_bom_line.unlink()
            else:
                old_line = old_bom_lines.get(reb_line.product_id, None)
                if old_line:
                    old_line.copy({"bom_id": self.new_bom_id.id})
        return True

    def apply_rebase(self):
        self.check_singleton()
        vals = {"state": "progress"}
        if self.bom_rebase_ids:
            new_bom_lines = {
                line.product_id: line for line in self.new_bom_id.bom_line_ids
            }
            if self._mark_rebase_conflicts(new_bom_lines, self.bom_rebase_ids):
                _debug.logic("eco_rebase", eco=self.id, by="conflict_on_rebase_lines")
                return self.write({"state": "conflict"})
            else:
                old_bom_lines = {
                    line.product_id: line for line in self.bom_id.bom_line_ids
                }
                self.rebase(old_bom_lines, new_bom_lines, self.bom_rebase_ids)
                self.bom_rebase_ids.unlink()
        if self.previous_change_ids:
            new_bom_lines = {
                line.product_id: line for line in self.new_bom_id.bom_line_ids
            }
            if self._mark_rebase_conflicts(new_bom_lines, self.previous_change_ids):
                _debug.logic("eco_rebase", eco=self.id, by="conflict_on_previous")
                return self.write({"state": "conflict"})
            else:
                new_activated_bom_lines = {
                    line.product_id: line for line in self.current_bom_id.bom_line_ids
                }
                self.rebase(
                    new_activated_bom_lines, new_bom_lines, self.previous_change_ids
                )
                self.previous_change_ids.unlink()
        if self.current_bom_id:
            self.new_bom_id.write(
                {
                    "version": (
                        self.will_update_version and self.current_bom_id.version + 1
                    )
                    or self.current_bom_id.version,
                    "previous_bom_id": self.current_bom_id.id,
                }
            )
            vals.update({"bom_id": self.current_bom_id.id, "current_bom_id": False})
        self.message_post(body=self.env._("Successfully Rebased!"))
        return self.write(vals)

    @api.depends(
        "bom_id.bom_line_ids.product_id",
        "bom_id.bom_line_ids.product_qty",
        "bom_id.bom_line_ids.product_uom_id",
        "bom_id.bom_line_ids.operation_id",
        "bom_id.bom_line_ids.bom_product_template_attribute_value_ids",
        "new_bom_id.bom_line_ids.product_id",
        "new_bom_id.bom_line_ids.product_qty",
        "new_bom_id.bom_line_ids.product_uom_id",
        "new_bom_id.bom_line_ids.operation_id",
        "new_bom_id.bom_line_ids.bom_product_template_attribute_value_ids",
        "bom_id.byproduct_ids.product_id",
        "bom_id.byproduct_ids.product_qty",
        "bom_id.byproduct_ids.product_uom_id",
        "bom_id.byproduct_ids.operation_id",
        "bom_id.byproduct_ids.bom_product_template_attribute_value_ids",
        "new_bom_id.byproduct_ids.product_id",
        "new_bom_id.byproduct_ids.product_qty",
        "new_bom_id.byproduct_ids.product_uom_id",
        "new_bom_id.byproduct_ids.operation_id",
        "new_bom_id.byproduct_ids.bom_product_template_attribute_value_ids",
    )
    def _compute_bom_change_ids(self) -> None:
        for eco in self:
            eco.bom_change_ids = eco._prepare_bom_change_commands(
                eco.bom_id, eco.new_bom_id
            )

    @api.depends(
        "bom_id.bom_line_ids",
        "current_bom_id.bom_line_ids",
        "current_bom_id.bom_line_ids.product_qty",
        "current_bom_id.bom_line_ids.product_uom_id",
        "current_bom_id.bom_line_ids.operation_id",
    )
    def _compute_previous_bom_change(self) -> None:
        for eco in self:
            if eco.current_bom_id:
                eco.previous_change_ids = eco._prepare_bom_change_commands(
                    eco.bom_id, eco.current_bom_id
                )
            else:
                eco.previous_change_ids = False

    @api.depends(
        "state",
        "type",
        "bom_id.operation_ids",
        "bom_id.operation_ids.name",
        "bom_id.operation_ids.workcenter_id",
        "bom_id.operation_ids.bom_product_template_attribute_value_ids",
        "bom_id.operation_ids.active",
        "bom_id.operation_ids.time_mode",
        "bom_id.operation_ids.time_mode_batch",
        "bom_id.operation_ids.time_cycle_manual",
        "new_bom_id.operation_ids",
        "new_bom_id.operation_ids.name",
        "new_bom_id.operation_ids.workcenter_id",
        "new_bom_id.operation_ids.bom_product_template_attribute_value_ids",
        "new_bom_id.operation_ids.active",
        "new_bom_id.operation_ids.time_mode",
        "new_bom_id.operation_ids.time_mode_batch",
        "new_bom_id.operation_ids.time_cycle_manual",
    )
    def _compute_routing_change_ids(self):
        for rec in self:
            if rec.state == "confirmed" or rec.type == "product":
                rec.routing_change_ids = [Command.clear()]
                continue
            new_routing_commands = [Command.clear()]
            old_routing_lines = defaultdict(lambda: self.env["mrp.routing.workcenter"])
            for op in rec.bom_id.operation_ids:
                old_routing_lines[op._get_sync_values()] |= op
            if rec.new_bom_id and rec.bom_id:
                for operation in rec.new_bom_id.operation_ids:
                    key = operation._get_sync_values()
                    old_op = old_routing_lines[key][:1]
                    if old_op:
                        old_routing_lines[key] -= old_op
                        if (
                            old_op.time_mode != operation.time_mode
                            or old_op.time_mode_batch != operation.time_mode_batch
                            or tools.float_compare(
                                old_op.time_cycle_manual, operation.time_cycle_manual, 2
                            )
                            != 0
                        ):
                            new_routing_commands += [
                                Command.create(
                                    {
                                        "change_type": "update",
                                        "workcenter_id": operation.workcenter_id.id,
                                        "upd_time_mode": old_op.time_mode
                                        + " -> "
                                        + operation.time_mode
                                        if operation.time_mode != old_op.time_mode
                                        else "",
                                        "upd_time_mode_batch": operation.time_mode_batch
                                        - old_op.time_mode_batch
                                        if operation.time_mode == "auto"
                                        else 0,
                                        "upd_time_cycle_manual": operation.time_cycle_manual
                                        - old_op.time_cycle_manual
                                        if operation.time_mode == "manual"
                                        else 0,
                                        "operation_id": operation.id,
                                    }
                                )
                            ]
                        new_routing_commands += self._prepare_detailed_change_commands(
                            operation, old_op
                        )
                    else:
                        new_routing_commands += [
                            Command.create(
                                {
                                    "change_type": "add",
                                    "workcenter_id": operation.workcenter_id.id,
                                    "upd_time_mode": operation.time_mode,
                                    "upd_time_mode_batch": operation.time_mode_batch,
                                    "upd_time_cycle_manual": operation.time_cycle_manual,
                                    "operation_id": operation.id,
                                }
                            )
                        ]
                        new_routing_commands += self._prepare_detailed_change_commands(
                            operation, None
                        )
            for old_ops in old_routing_lines.values():
                for old_op in old_ops:
                    new_routing_commands += [
                        Command.create(
                            {
                                "change_type": "remove",
                                "workcenter_id": old_op.workcenter_id.id,
                                "operation_id": old_op.id,
                            }
                        )
                    ]
            rec.routing_change_ids = new_routing_commands

    def _prepare_detailed_change_commands(self, new, old):
        return []

    @api.depends(
        "stage_id.approval_template_ids.approval_type",
        "stage_id.approval_template_ids.user_ids",
        "approval_request_ids.state",
        "approval_request_ids.approver_ids.state",
        "approval_request_ids.approver_ids.user_id",
        "approval_request_ids.approver_ids.delegate_id",
    )
    @api.depends_context("uid")
    def _compute_user_approval(self) -> None:
        for eco in self:
            request = (
                eco._get_stage_request() if eco.id else eco.env["approval.request"]
            )
            asked = eco.stage_id.approval_template_ids.filtered(
                lambda template: (
                    template.approval_type in ("mandatory", "optional")
                    and self.env.user in template.user_ids
                )
            )
            pending = (
                eco._get_my_stage_rows(request) if request else request.approver_ids
            )
            refused = (
                eco._get_my_stage_rows(request, ("refused",))
                if request.state == "refused"
                else request.approver_ids.browse()
            )
            eco.user_can_approve = bool(asked) and bool(pending or refused)
            eco.user_can_reject = bool(asked) and bool(pending)

    @api.depends("approval_request_ids.approver_ids")
    def _compute_approval_approver_ids(self) -> None:
        for eco in self:
            eco.approval_approver_ids = eco.sudo().approval_request_ids.approver_ids

    @api.depends(
        "approval_request_ids.state",
        "approval_request_ids.approver_ids.state",
        "approval_request_ids.approver_ids.user_id",
        "approval_request_ids.approver_ids.delegate_id",
    )
    @api.depends_context("uid")
    def _compute_awaiting_my_validation(self) -> None:
        waiting = self.search(
            [("id", "in", self.ids), ("awaiting_my_validation", "=", True)]
        )
        for eco in self:
            eco.awaiting_my_validation = eco in waiting

    def _search_awaiting_my_validation(self, operator, value):
        if operator != "in":
            return NotImplemented
        rows = (
            self.env["approval.approver"]
            .sudo()
            .search(
                [
                    ("request_id.res_model", "=", self._name),
                    ("request_id.state", "=", "pending"),
                    ("state", "=", "pending"),
                    "|",
                    ("user_id", "=", self.env.uid),
                    ("delegate_id", "=", self.env.uid),
                ]
            )
        )
        return [("id", "in", rows.request_id.mapped("res_id"))]

    @api.depends("stage_id", "approval_request_ids.state")
    def _compute_kanban_state(self) -> None:
        for rec in self:
            request = (
                rec._get_stage_request() if rec.id else rec.env["approval.request"]
            )
            if not rec.stage_id.approval_template_ids or not request:
                rec.kanban_state = "normal"
            elif request.state == "approved":
                rec.kanban_state = "done"
            elif request.state == "refused":
                rec.kanban_state = "blocked"
            else:
                rec.kanban_state = "normal"

    @api.depends("kanban_state", "stage_id", "stage_id.approval_template_ids")
    def _compute_allow_change_stage(self) -> None:
        for rec in self:
            if rec.stage_id.approval_template_ids:
                rec.allow_change_stage = rec.kanban_state == "done"
            else:
                rec.allow_change_stage = rec.kanban_state in ["normal", "done"]

    @api.depends("state", "stage_id.allow_apply_change")
    def _compute_allow_apply_change(self) -> None:
        for rec in self:
            rec.allow_apply_change = rec.stage_id.allow_apply_change and rec.state in (
                "confirmed",
                "progress",
            )

    @api.depends("stage_id.approval_template_ids")
    def _compute_allow_change_kanban_state(self) -> None:
        for rec in self:
            rec.allow_change_kanban_state = not rec.stage_id.approval_template_ids

    @api.depends("stage_id", "kanban_state")
    def _compute_kanban_state_label(self) -> None:
        for eco in self:
            if eco.kanban_state == "normal":
                eco.kanban_state_label = eco.legend_normal
            elif eco.kanban_state == "blocked":
                eco.kanban_state_label = eco.legend_blocked
            else:
                eco.kanban_state_label = eco.legend_done

    @api.onchange("product_tmpl_id")
    def onchange_product_tmpl_id(self) -> None:
        if self.product_tmpl_id.bom_ids:
            bom_product_tmpl = (
                self.bom_id.product_tmpl_id or self.bom_id.product_id.product_tmpl_id
            )
            if bom_product_tmpl != self.product_tmpl_id:
                self.bom_id = self.product_tmpl_id.bom_ids.ids[0]

    @api.onchange("type_id")
    def onchange_type_id(self) -> None:
        self.stage_id = (
            self.env["mrp.eco.stage"]
            .search([("type_ids", "in", self.type_id.id)], limit=1)
            .id
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            prefix = self.env["ir.sequence"].next_by_code("mrp.eco") or ""
            vals["name"] = "%s%s" % (
                (prefix and "%s: " % prefix) or "",
                vals.get("name", ""),
            )
        ecos = super().create(vals_list)
        ecos._raise_stage_requests()
        return ecos

    def write(self, vals):
        if vals.get("stage_id"):
            newstage = self.env["mrp.eco.stage"].browse(vals["stage_id"])
            for eco in self:
                if eco.stage_id and (
                    (newstage.sequence, newstage.id)
                    > (eco.stage_id.sequence, eco.stage_id.id)
                ):
                    if not eco.allow_change_stage:
                        _debug.logic(
                            "eco_stage_refused",
                            eco=eco.id,
                            reason="approvals_pending",
                            stage=newstage.id,
                        )
                        raise UserError(
                            self.env._(
                                "You cannot change the stage, as approvals are still required."
                            )
                        )
                    has_blocking_stages = self.env["mrp.eco.stage"].search_count(
                        [
                            ("sequence", ">=", eco.stage_id.sequence),
                            ("sequence", "<=", newstage.sequence),
                            ("type_ids", "in", eco.type_id.id),
                            ("id", "not in", [eco.stage_id.id] + [vals["stage_id"]]),
                            ("is_blocking", "=", True),
                        ]
                    )
                    if has_blocking_stages:
                        _debug.logic(
                            "eco_stage_refused",
                            eco=eco.id,
                            reason="blocking_stage_between",
                            stage=newstage.id,
                        )
                        raise UserError(
                            self.env._(
                                "You cannot change the stage, as approvals are required in the process."
                            )
                        )
                if eco.stage_id != newstage:
                    eco._cancel_stage_request()
        if "displayed_image_attachment_id" in vals:
            doc = False
            if vals["displayed_image_attachment_id"]:
                doc = self.env["document.document"].search(
                    [("attachment_id", "=", vals["displayed_image_attachment_id"])]
                )
                if not doc:
                    doc = self.env["document.document"].create(
                        [{"attachment_id": vals["displayed_image_attachment_id"]}]
                    )
            vals.pop("displayed_image_attachment_id")
            vals["displayed_image_id"] = doc
        if "will_update_version" in vals:
            for eco in self:
                if (
                    eco.new_bom_id
                    and eco.state != "done"
                    and eco.will_update_version != vals["will_update_version"]
                ):
                    eco.new_bom_id.version += 1 if vals["will_update_version"] else -1
        if vals.get("type") == "product":
            vals["bom_id"] = False
            vals["new_bom_id"] = False
        res = super().write(vals)
        _debug.lifecycle("write", ecos=self, fields=list(vals))
        if vals.get("stage_id"):
            self._raise_stage_requests()
        return res

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        search_domain = []
        if self.env.context.get("default_type_ids"):
            search_domain = [("type_ids", "in", self.env.context["default_type_ids"])]

        stage_ids = stages.sudo()._search(search_domain, order=stages._order)
        return stages.browse(stage_ids)

    def _message_post_after_hook(self, message, msg_vals):
        super()._message_post_after_hook(message, msg_vals)
        if (
            message.message_type == "comment"
            and message.author_id == self.env.user.partner_id
        ):
            self._record_comment_advice()

    def _get_stage_subject_key(self, stage=None) -> str:
        self.check_singleton()
        return f"stage:{(stage or self.stage_id).id}"

    def _get_approval_subject_category(self, subject_key):
        return self.env.ref("mrp_plm.approval_category_eco", raise_if_not_found=False)

    def _prepare_approval_subject_request_values(self, subject_key, category):
        vals = super()._prepare_approval_subject_request_values(subject_key, category)
        vals["request_owner_id"] = self.user_id.id or self.env.ref("base.user_root").id
        vals["name"] = self.env._(
            "%(eco)s at %(stage)s", eco=self.display_name, stage=self.stage_id.name
        )
        return vals

    def _get_stage_request(self):
        self.check_singleton()
        return self.sudo()._get_approval_request(self._get_stage_subject_key())

    def _raise_stage_requests(self) -> None:
        for eco in self.sudo():
            if not eco.stage_id.approval_template_ids:
                continue
            if eco._get_live_approval_request(eco._get_stage_subject_key()):
                continue
            eco._raise_approval_request(eco._get_stage_subject_key())

    def _cancel_stage_request(self) -> None:
        self.check_singleton()
        request = self.sudo()._get_live_approval_request(self._get_stage_subject_key())
        if request:
            request._force_terminal(
                "cancelled",
                self.env._(
                    "%(eco)s left %(stage)s before its approval was decided.",
                    eco=self.display_name,
                    stage=self.stage_id.name,
                ),
            )

    def _restart_stage_request(self, refused):
        self.check_singleton()
        request = self._raise_approval_request(self._get_stage_subject_key())
        changer = self.env.user
        for row in refused.approver_ids.filtered(
            lambda row: row.decision_date and row.decided_by_user_id != changer
        ):
            new_rows = request.approver_ids.filtered_domain(
                [("user_id", "=", row.user_id.id), ("state", "=", "pending")]
            )
            if not new_rows:
                continue
            steps = new_rows.step_ids & row.decided_step_ids
            if row.state == "approved" and steps:
                request.sudo().with_user(row.decided_by_user_id).action_approve(
                    approver=new_rows, steps=steps
                )
        return request

    def _get_my_stage_rows(self, request, states=("pending",)):
        self.check_singleton()
        return request.approver_ids.filtered(
            lambda row: (
                row._get_effective_approver() == self.env.user and row.state in states
            )
        )

    def approve(self) -> None:
        for eco in self:
            request = eco._get_stage_request()
            if request.state == "refused" and eco._get_my_stage_rows(
                request, ("refused",)
            ):
                request = eco.sudo()._restart_stage_request(request)
            rows = eco._get_my_stage_rows(request)
            if not rows:
                _debug.logic(
                    "eco_approve_refused", eco=eco.id, reason="not_an_approver"
                )
                raise UserError(
                    self.env._(
                        "You are not asked to approve this change at this stage."
                    )
                )
            _debug.lifecycle("eco_approved", eco=eco.id, rows=len(rows))
            request.sudo().action_approve(approver=rows)

    def reject(self) -> None:
        for eco in self:
            request = eco._get_stage_request()
            rows = eco._get_my_stage_rows(request)
            if not rows:
                _debug.logic("eco_reject_refused", eco=eco.id, reason="not_an_approver")
                raise UserError(
                    self.env._("You are not asked to decide this change at this stage.")
                )
            _debug.lifecycle("eco_rejected", eco=eco.id, rows=len(rows))
            request.sudo().with_context(skip_wizard=True).action_refuse(approver=rows)

    def _record_comment_advice(self) -> None:
        self.check_singleton()
        request = self.sudo()._get_live_approval_request(self._get_stage_subject_key())
        if not request:
            return
        comment_steps = self.stage_id.approval_template_ids.filtered(
            lambda template: (
                template.approval_type == "comment"
                and self.env.user in template.user_ids
            )
        ).step_id
        rows = self._get_my_stage_rows(request).filtered(
            lambda row: row.step_ids & comment_steps
        )
        if rows:
            request.sudo().action_approve(
                approver=rows, steps=rows.step_ids & comment_steps
            )

    def conflict_resolve(self) -> bool:
        self.check_singleton()
        vals = {"state": "progress"}
        if self.current_bom_id:
            vals.update({"bom_id": self.current_bom_id.id, "current_bom_id": False})
        self.write(vals)
        self.new_bom_id.write(
            {
                "version": (self.will_update_version and self.bom_id.version + 1)
                or self.bom_id.version,
                "previous_bom_id": self.bom_id.id,
            }
        )
        rebase_lines = self.bom_rebase_ids + self.previous_change_ids
        _debug.lifecycle(
            "eco_conflict_resolved", eco=self.id, rebase_lines=len(rebase_lines)
        )
        rebase_lines.unlink()
        return True

    def action_new_revision(self) -> None:
        for eco in self:
            domain = Domain(
                [
                    ("res_model", "=", "product.template"),
                    ("res_id", "=", eco.product_tmpl_id.id),
                ]
            )
            if eco.type == "bom":
                if eco.production_id:
                    eco.new_bom_id = eco.production_id._create_revision_bom(
                        eco.will_update_version
                    )
                if not eco.new_bom_id:
                    eco.new_bom_id = eco.bom_id.sudo().copy(
                        default={
                            "version": eco.bom_id.version + eco.will_update_version,
                            "active": False,
                            "previous_bom_id": eco.bom_id.id,
                        }
                    )
                if eco.bom_id.product_id:
                    domain |= Domain(
                        [
                            "&",
                            ("res_model", "=", "product.product"),
                            ("res_id", "in", eco.bom_id.product_id.ids),
                        ]
                    )
                else:
                    domain |= Domain(
                        [
                            "&",
                            ("res_model", "=", "product.product"),
                            (
                                "res_id",
                                "in",
                                self.env["product.product"]
                                .search(
                                    [("product_tmpl_id", "in", eco.product_tmpl_id.ids)]
                                )
                                .ids,
                            ),
                        ]
                    )
                domain &= Domain("attached_on_mrp", "=", "bom")
            else:
                domain |= Domain(
                    [
                        "&",
                        ("res_model", "=", "product.product"),
                        (
                            "res_id",
                            "in",
                            self.env["product.product"]
                            .search(
                                [("product_tmpl_id", "in", eco.product_tmpl_id.ids)]
                            )
                            .ids,
                        ),
                    ]
                )
            docs = self.env["document.document"].search(domain)
            for doc in docs:
                doc.copy(
                    {
                        "res_model": "mrp.eco",
                        "res_id": eco.id,
                        "origin_attachment_id": doc.attachment_id.id,
                    }
                )
        self.write({"state": "progress"})

    def action_apply(self):
        self._check_company()
        eco_need_action = self.env["mrp.eco"]
        _debug.pipeline("eco_apply", ecos=self)
        for eco in self:
            if eco.state == "done":
                _debug.logic("eco_apply_skipped", eco=eco.id, reason="done")
                continue
            if eco.state == "rebase":
                eco.apply_rebase()
            if eco.allow_apply_change:
                if eco.type == "product":
                    eco.product_tmpl_id.version = (
                        eco.will_update_version and eco.product_tmpl_id.version + 1
                    ) or eco.product_tmpl_id.version
                else:
                    eco.mapped("new_bom_id").apply_new_version()

                for attach in eco.with_context(active_test=False).document_ids:
                    origin = attach.origin_attachment_id
                    if not attach.active:
                        origin.unlink()
                        continue
                    if origin.checksum == attach.checksum:
                        if attach.origin_attachment_id.name != attach.name:
                            attach.origin_attachment_id.name = attach.name
                        if attach.origin_attachment_id.company_id != attach.company_id:
                            attach.origin_attachment_id.company_id = attach.company_id
                        continue
                    new_doc = attach.copy(
                        {
                            "res_model": "product.template",
                            "res_id": eco.product_tmpl_id.id,
                        }
                    )
                    attach.origin_attachment_id = new_doc.attachment_id.id

                vals = {"state": "done"}
                stage_id = (
                    eco.env["mrp.eco.stage"]
                    .search(
                        [
                            ("final_stage", "=", True),
                            ("type_ids", "in", eco.type_id.id),
                        ],
                        limit=1,
                    )
                    .id
                )
                if stage_id:
                    vals["stage_id"] = stage_id
                _debug.lifecycle(
                    "eco_applied", eco=eco.id, type=eco.type, stage=stage_id or False
                )
                eco.write(vals)
            else:
                _debug.logic("eco_apply_blocked", eco=eco.id, reason="not_allowed")
                eco_need_action |= eco
        if eco_need_action:
            return {
                "name": self.env._("Eco"),
                "type": "ir.actions.act_window",
                "view_mode": "list, form",
                "views": [[False, "list"], [False, "form"]],
                "res_model": "mrp.eco",
                "target": "current",
                "domain": [("id", "in", eco_need_action.ids)],
                "context": {"search_default_changetoapply": False},
            }
        return None

    def action_see_attachments(self) -> dict:
        self.check_singleton()
        attachment_view = self.env.ref("mrp_plm.view_document_file_kanban_mrp_plm")
        context = {
            "default_res_model": self._name,
            "default_res_id": self.id,
            "default_company_id": self.company_id.id,
            "search_default_all": 1,
            "create": self.state != "done",
            "edit": self.state != "done",
            "delete": self.state != "done",
        }

        if self.type == "bom":
            context["eco_bom"] = True

        return {
            "name": self.env._("Attachments"),
            "domain": ["&", ("res_model", "=", self._name), ("res_id", "=", self.id)],
            "res_model": "document.document",
            "type": "ir.actions.act_window",
            "view_id": attachment_view.id,
            "views": [(attachment_view.id, "kanban"), (False, "form")],
            "view_mode": "kanban,list,form",
            "help": self.env._("""<p class="o_view_nocontent_smiling_face">
                        Upload files to your ECO, that will be applied to the product later
                    </p><p>
                        Use this feature to store any files, like drawings or specifications.
                    </p>"""),
            "limit": 80,
            "context": context,
        }

    def action_view_production(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "mrp.action_mrp_production_form"
        )
        action["res_id"] = self.production_id.id
        return action

    def open_new_bom(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Eco BoM"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mrp.bom",
            "target": "current",
            "res_id": self.new_bom_id.id,
            "context": {
                "default_product_tmpl_id": self.product_tmpl_id.id,
                "default_product_id": self.product_tmpl_id.product_variant_id.id,
                "create": self.state != "done",
                "edit": self.state != "done",
                "delete": self.state != "done",
            },
        }


class MrpEcoBomChange(models.Model):
    _name = "mrp.eco.bom.change"
    _description = "ECO BoM changes"

    eco_id = fields.Many2one(
        comodel_name="mrp.eco",
        string="Engineering Change",
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="eco_id.company_id")
    eco_rebase_id = fields.Many2one(
        comodel_name="mrp.eco",
        string="ECO Rebase",
        index="btree_not_null",
        ondelete="cascade",
    )
    rebase_id = fields.Many2one(
        comodel_name="mrp.eco",
        index="btree_not_null",
        ondelete="cascade",
    )
    change_type = fields.Selection(
        selection=[("add", "Add"), ("remove", "Remove"), ("update", "Update")],
        string="Type",
        required=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
    )
    old_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Previous Product UoM",
    )
    new_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="New Product UoM",
    )
    old_product_qty = fields.Float(
        string="Previous revision quantity",
        default=0,
    )
    new_product_qty = fields.Float(
        string="New revision quantity",
        default=0,
    )
    old_operation_id = fields.Many2one(
        comodel_name="mrp.routing.workcenter",
        string="Previous Consumed in Operation",
    )
    new_operation_id = fields.Many2one(
        comodel_name="mrp.routing.workcenter",
        string="New Consumed in Operation",
    )
    upd_product_qty = fields.Float(
        string="Quantity",
        digits="Product Unit",
        compute="_compute_upd_product_qty",
        store=True,
    )
    uom_change = fields.Char(
        string="Unit",
        compute="_compute_change",
        compute_sudo=True,
    )
    operation_change = fields.Char(
        string="Consumed in Operation",
        compute="_compute_change",
        compute_sudo=True,
    )
    conflict = fields.Boolean()
    bom_line_id = fields.Many2one(
        comodel_name="mrp.bom.line",
        string="BoM Line",
        check_company=True,
    )
    byproduct_id = fields.Many2one(
        comodel_name="mrp.bom.byproduct",
        string="BoM By-Product",
        check_company=True,
    )

    @api.depends("new_product_qty", "old_product_qty")
    def _compute_upd_product_qty(self) -> None:
        for rec in self:
            rec.upd_product_qty = rec.new_product_qty - rec.old_product_qty

    @api.depends("old_operation_id", "new_operation_id", "old_uom_id", "new_uom_id")
    def _compute_change(self) -> None:
        for rec in self:
            rec.operation_change = (
                rec.new_operation_id.name
                if rec.change_type == "add"
                else rec.old_operation_id.name
            )
            rec.uom_change = False
            if (rec.old_uom_id and rec.new_uom_id) and rec.old_uom_id != rec.new_uom_id:
                rec.uom_change = rec.old_uom_id.name + " -> " + rec.new_uom_id.name
            if (
                rec.old_operation_id._get_sync_values()
                != rec.new_operation_id._get_sync_values()
            ) and rec.change_type == "update":
                rec.operation_change = (
                    (rec.old_operation_id.name or "")
                    + " -> "
                    + (rec.new_operation_id.name or "")
                )

    def action_view_component_change(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.bom",
            "res_id": self.bom_line_id.bom_id.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "mrp_plm.mrp_bom_view_form_inherit_plm_components"
            ).id,
        }

    def action_view_byproduct_change(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.bom",
            "res_id": self.byproduct_id.bom_id.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "mrp_plm.mrp_bom_view_form_inherit_plm_byproducts"
            ).id,
        }


class MrpEcoRoutingChange(models.Model):
    _name = "mrp.eco.routing.change"
    _description = "Eco Routing changes"

    eco_id = fields.Many2one(
        comodel_name="mrp.eco",
        string="Engineering Change",
        index=True,
        required=True,
        ondelete="cascade",
    )
    change_type = fields.Selection(
        selection=[("add", "Add"), ("remove", "Remove"), ("update", "Update")],
        string="Type",
        required=True,
    )
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Work Center",
    )
    upd_time_mode = fields.Char(string="Mode Change")
    upd_time_mode_batch = fields.Integer(string="Batch count Change")
    upd_time_cycle_manual = fields.Float(string="Manual Duration Change")

    operation_id = fields.Many2one(
        comodel_name="mrp.routing.workcenter",
        string="Operation Id",
    )
    operation_name = fields.Char(
        related="operation_id.name",
        string="Operation",
    )

    def action_view_routing_change_operation(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.routing.workcenter",
            "res_id": self.operation_id.id,
            "view_mode": "form",
        }


class MrpEcoTag(models.Model):
    _name = "mrp.eco.tag"
    _description = "ECO Tags"
    _inherit = ["mixin.tag"]
