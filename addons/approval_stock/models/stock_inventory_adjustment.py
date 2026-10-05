from typing import Any, Self

from markupsafe import Markup

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import frozendict
from odoo.tools.misc import formatLang


class StockInventoryAdjustment(models.Model):
    _name = "stock.inventory.adjustment"
    _description = "Inventory Adjustment"
    _inherit = ["mixin.mail.thread", "mixin.approval.gate"]
    _order = "id desc"
    _check_company_auto = True

    _max_detail_lines = 10
    _access_verbs = {
        "apply": models.Verb(
            methods=("_apply",),
            checkpoints=("_check_apply_allowed",),
        ),
    }
    _access_anchors = frozendict(
        {
            "owner": "approval_pending_user_ids",
        }
    )

    name = fields.Char(
        string="Reference",
        default="/",
        copy=False,
        readonly=True,
        required=True,
    )
    reason = fields.Char(
        string="Inventory Reason",
        default=lambda self: self.env._("Physical Inventory"),
        required=True,
    )
    date_counted = fields.Datetime(
        string="Counting Date",
        default=fields.Datetime.now,
        required=True,
        help="Date the stock moves of this adjustment are dated at once applied.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Counted By",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("applied", "Applied"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        copy=False,
        readonly=True,
        required=True,
        tracking=True,
    )
    date_applied = fields.Datetime(
        copy=False,
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="stock.inventory.adjustment.line",
        inverse_name="adjustment_id",
        string="Counted Quants",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("stock.inventory.adjustment")
                    or "/"
                )
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_applied(self) -> None:
        if applied := self.filtered(lambda adjustment: adjustment.state == "applied"):
            raise UserError(
                self.env._(
                    "%(name)s was applied to the stock and cannot be deleted.",
                    name=applied[:1].display_name,
                )
            )

    @api.model
    def _create_from_quants(self, quants, reason: str, date_counted) -> Self:
        counted = quants.filtered("inventory_quantity_set")
        if not counted:
            raise UserError(self.env._("There is no counted quantity to adjust."))
        if len(counted.company_id) > 1:
            raise UserError(
                self.env._("An inventory adjustment covers the quants of one company.")
            )
        waiting = (
            self.env["stock.inventory.adjustment.line"]
            .sudo()
            .search(
                [
                    ("quant_id", "in", counted.ids),
                    ("adjustment_id.state", "=", "draft"),
                ]
            )
        )
        if waiting:
            raise UserError(
                self.env._(
                    "%(products)s already wait in %(adjustments)s.",
                    products=", ".join(waiting.product_id.mapped("display_name")),
                    adjustments=", ".join(waiting.adjustment_id.mapped("name")),
                )
            )
        return self.create(
            {
                "reason": reason or self.env._("Physical Inventory"),
                "date_counted": date_counted or fields.Datetime.now(),
                "company_id": (counted.company_id or self.env.company).id,
                "line_ids": [
                    Command.create(
                        {
                            "quant_id": quant.id,
                            "product_id": quant.product_id.id,
                            "location_id": quant.location_id.id,
                            "trace_id": quant.trace_id.id,
                            "package_id": quant.package_id.id,
                            "owner_id": quant.owner_id.id,
                            "quantity_counted": quant.inventory_quantity,
                            "quantity_on_hand": quant.quantity,
                        }
                    )
                    for quant in counted
                ],
            }
        )

    def _can_apply_quants(self, quants) -> bool:
        self.check_singleton()
        return (
            self.state == "draft"
            and self.approval_state == "approved"
            and quants <= self.line_ids.quant_id
        )

    def _apply(self) -> None:
        self.check_singleton()
        self._apply_counted()

    def _check_apply_allowed(self) -> None:
        for adjustment in self:
            if adjustment.state != "draft" or adjustment.approval_state != "approved":
                raise UserError(
                    self.env._(
                        "Only a draft inventory adjustment whose approval was granted "
                        "can be applied: %(name)s is not one.",
                        name=adjustment.display_name,
                    )
                )

    def _apply_counted(self) -> None:
        self.check_singleton()
        self._check_apply_allowed()
        for line in self.line_ids:
            line.quant_id.inventory_quantity = line.quantity_counted
        quants = self.line_ids.quant_id
        quants.with_context(
            inventory_name=self.name,
            stock_inventory_adjustment_id=self.id,
        )._apply_inventory(self.date_counted)
        self.write({"state": "applied", "date_applied": fields.Datetime.now()})
        self.message_post(
            body=self.env._(
                "Applied to the stock: %(count)s counted quant(s).", count=len(quants)
            ),
            message_type="notification",
        )

    def _cancel_for_moved_lines(self, moved) -> None:
        self.check_singleton()
        self.state = "cancelled"
        items = Markup("").join(
            Markup("<li>%s</li>")
            % self.env._(
                "%(product)s in %(location)s: %(requested)s on hand when requested, "
                "%(current)s now",
                product=line.product_id.display_name,
                location=line.location_id.display_name,
                requested=formatLang(self.env, line.quantity_on_hand),
                current=formatLang(self.env, line.quant_id.quantity),
            )
            for line in moved
        )
        self.message_post(
            body=Markup("<p>%s</p><ul>%s</ul>")
            % (
                self.env._(
                    "Not applied: these quantities moved after the count was sent "
                    "for approval. Every count stays on its quant for a recount."
                ),
                items,
            ),
            message_type="notification",
        )

    def _get_fields_approval_required(self) -> list[str]:
        return ["line_ids", "date_counted"]

    def _get_fields_approval_protected(self) -> list[str]:
        return ["line_ids", "reason", "date_counted", "company_id"]

    def _get_domain_approval_category(self) -> list[tuple[str, str, Any]]:
        return [
            ("approval_type", "=", "stock_inventory"),
            ("target_model", "=", False),
        ]

    def _get_approval_category_fallback(self, categories):
        self.check_singleton()
        return categories.filtered(
            lambda category: (
                not (category.location_ids or category.stock_product_categ_ids)
                and category.step_ids
                and category._can_be_met_for(self)
            )
        )[:1]

    def _prepare_approval_request_values(self, category: Any) -> dict[str, Any]:
        vals = super()._prepare_approval_request_values(category)
        vals["reference"] = self.name
        return vals

    def _get_approval_reason_html(self) -> str:
        self.check_singleton()
        rows = Markup("").join(
            Markup("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>")
            % (
                line.product_id.display_name,
                line.location_id.display_name,
                formatLang(self.env, line.quantity_on_hand),
                formatLang(self.env, line.quantity_counted),
            )
            for line in self.line_ids[: self._max_detail_lines]
        )
        body = Markup(
            "<p><strong>%s</strong></p><p>%s</p>"
            "<table class='table table-sm'><thead><tr>"
            "<th>%s</th><th>%s</th><th>%s</th><th>%s</th>"
            "</tr></thead><tbody>%s</tbody></table>"
        ) % (
            self.name,
            self.reason,
            self.env._("Product"),
            self.env._("Location"),
            self.env._("On Hand"),
            self.env._("Counted"),
            rows,
        )
        if (hidden := len(self.line_ids) - self._max_detail_lines) > 0:
            body += Markup("<p>%s</p>") % self.env._(
                "and %(count)s more line(s)", count=hidden
            )
        return body

    def _get_approval_snapshot(self, operation: str) -> dict[str, Any]:
        self.check_singleton()
        return {
            "date_counted": fields.Datetime.to_string(self.date_counted),
            "lines": sorted(
                [
                    line.quant_id.id,
                    line.product_id.id,
                    line.location_id.id,
                    line.quantity_counted,
                ]
                for line in self.line_ids
            ),
        }

    def _is_operation_run_on_approval(self, operation: str) -> bool:
        return self.state == "draft"

    def _run_operation_on_approval(self) -> None:
        self.check_singleton()
        if self.state != "draft":
            return
        if moved := self.line_ids.filtered(lambda line: line._has_moved()):
            self._cancel_for_moved_lines(moved)
            return
        super()._run_operation_on_approval()

    def _get_operation_failure_note(self, operation: str) -> str:
        return self.env._(
            "Approval was granted, but the count could not be applied: %(error)s"
        )

    def _on_approval_refused(self) -> None:
        super()._on_approval_refused()
        if self.state == "draft":
            self.state = "cancelled"

    def _on_approval_cancelled(self) -> None:
        super()._on_approval_cancelled()
        if self.state == "draft":
            self.state = "cancelled"

    def _on_approval_reset(self) -> None:
        super()._on_approval_reset()
        if self.state != "cancelled":
            return
        # A count taken against stock that has since moved is recounted into a new
        # adjustment; reopening it would only be cancelled again on approval.
        if not self.line_ids.filtered(lambda line: line._has_moved()):
            self.state = "draft"


class StockInventoryAdjustmentLine(models.Model):
    _name = "stock.inventory.adjustment.line"
    _description = "Inventory Adjustment Line"
    _order = "adjustment_id, id"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    adjustment_id = fields.Many2one(
        comodel_name="stock.inventory.adjustment",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="adjustment_id.company_id",
    )
    quant_id = fields.Many2one(
        comodel_name="stock.quant",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        readonly=True,
        required=True,
    )
    product_uom_id = fields.Many2one(related="product_id.uom_id")
    location_id = fields.Many2one(
        comodel_name="stock.location",
        readonly=True,
        required=True,
    )
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        readonly=True,
    )
    package_id = fields.Many2one(
        comodel_name="stock.package",
        readonly=True,
    )
    owner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
    )
    quantity_on_hand = fields.Float(
        string="On Hand When Requested",
        digits="Product Unit",
        readonly=True,
    )
    quantity_counted = fields.Float(
        string="Counted",
        digits="Product Unit",
        required=True,
    )
    quantity_difference = fields.Float(
        string="Difference",
        digits="Product Unit",
        compute="_compute_quantity_difference",
        store=True,
    )

    @api.depends("quantity_counted", "quantity_on_hand")
    def _compute_quantity_difference(self) -> None:
        for line in self:
            line.quantity_difference = line.quantity_counted - line.quantity_on_hand

    def _has_moved(self) -> bool:
        self.check_singleton()
        if not self.quant_id:
            return True
        return bool(
            self.product_uom_id.compare(self.quant_id.quantity, self.quantity_on_hand)
        )

    def _check_adjustment_editable(self) -> None:
        if self.env.su:
            return
        locked = self.adjustment_id.filtered(
            lambda adjustment: (
                adjustment.state != "draft" or adjustment.approval_state == "pending"
            )
        )
        if locked:
            raise UserError(
                self.env._(
                    "The counted lines of %(name)s cannot change while its approval "
                    "is pending or once it is applied or cancelled.",
                    name=locked[:1].display_name,
                )
            )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]):
        lines = super().create(vals_list)
        lines._check_adjustment_editable()
        return lines

    def write(self, vals: dict[str, Any]) -> bool:
        self._check_adjustment_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked_adjustment(self) -> None:
        self._check_adjustment_editable()
