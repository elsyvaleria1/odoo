from datetime import timedelta
from typing import Any

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict
from odoo.tools.misc import clean_context

_debug = DebugLog(__name__)


class ApprovalRequest(models.Model):
    _inherit = "approval.request"
    _access_anchors = frozendict(
        {
            "approver_delegate": models.Anchor(
                "approver_ids.delegate_id", kind="owner"
            ),
            "approver_user": models.Anchor("approver_ids.user_id", kind="owner"),
            "category_allowed_group_all_user": models.Anchor(
                "category_id.allowed_group_ids.all_user_ids", kind="owner"
            ),
            "category_allowed_user": models.Anchor(
                "category_id.allowed_user_ids", kind="owner"
            ),
            "owner": "request_owner_id",
        }
    )

    count_stock_picking = fields.Integer(compute="_compute_count_stock_picking")
    picking_ids = fields.One2many(
        comodel_name="stock.picking",
        inverse_name="approval_request_id",
        readonly=True,
        help="Transfers linked to this request through the approval mixin",
    )

    has_asset = fields.Selection(
        related="category_id.has_asset",
        string="Vehicle Requirement",
        help="Whether this approval category requires vehicle information",
    )
    has_odometer = fields.Selection(
        related="category_id.has_odometer",
        string="Odometer Requirement",
        help="Whether this approval category requires odometer reading",
    )
    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        compute="_compute_asset_id",
        store=True,
        readonly=False,
        domain="[('kind_code', '=', 'vehicle')]",
        help="The vehicle associated with this approval request",
    )
    odometer = fields.Float(help="Current odometer reading of the vehicle")
    asset_log_ids = fields.One2many(
        comodel_name="resource.log",
        inverse_name="approval_request_id",
        readonly=True,
        help="Asset logs booked from this approval request",
    )

    @api.depends("line_ids.stock_move_id", "picking_ids")
    def _compute_count_stock_picking(self) -> None:
        for request in self:
            request.count_stock_picking = len(request._get_all_pickings())

    def _check_withdraw_allowed(self) -> None:
        _debug.logic("approval_withdraw_check", requests=self)
        super()._check_withdraw_allowed()
        self._check_withdraw_blocked_by(
            self._get_all_pickings(),
            self.env._("stock picking"),
        )
        self._check_withdraw_blocked_by_applied_adjustment()

    def _check_withdraw_blocked_by_applied_adjustment(self) -> None:
        _debug.logic("approval_withdraw_blocked", requests=self)
        if self.res_model != "stock.inventory.adjustment":
            return
        adjustment = self.get_source_document()
        if adjustment and adjustment.state == "applied":
            raise UserError(
                self.env._(
                    "%(name)s was applied to the stock: its approval can no longer "
                    "be withdrawn or reset.",
                    name=adjustment.display_name,
                )
            )

    @api.depends("request_owner_id", "request_owner_id.employee_id", "has_asset")
    def _compute_asset_id(self) -> None:
        pending = self.browse()
        for request in self:
            if request.has_asset == "no" or not request.has_asset:
                request.asset_id = False
            elif request.asset_id:
                continue
            elif not request.request_owner_id.employee_id:
                request.asset_id = False
            else:
                pending |= request
        if not pending:
            return

        assets_by_operator: dict[int, Any] = {}
        for asset in (
            self.env["resource.asset"]
            .sudo()
            .search(
                [
                    ("kind_code", "=", "vehicle"),
                    (
                        "operator_employee_id",
                        "in",
                        pending.request_owner_id.employee_id.ids,
                    ),
                    (
                        "company_id",
                        "in",
                        [*pending.company_id.ids, False],
                    ),
                ],
                order="id",
            )
        ):
            assets_by_operator.setdefault(asset.operator_employee_id.id, []).append(
                asset
            )

        for request in pending:
            employee = request.request_owner_id.employee_id
            allowed = (request.company_id.id, False)
            request.asset_id = next(
                (
                    asset
                    for asset in assets_by_operator.get(employee.id, ())
                    if asset.company_id.id in allowed
                ),
                False,
            )

    def action_create_asset_log(self) -> dict[str, Any]:
        _debug.pipeline("approval_asset_log_create", requests=self)
        self.check_singleton()

        if self.state != "approved":
            raise UserError(
                self.env._(
                    "Asset logs can only be created from an APPROVED "
                    "request. Request '%(name)s' is in state '%(state)s'.",
                    name=self.display_name,
                    state=self.state,
                ),
            )

        if not self.asset_id:
            raise UserError(
                self.env._("Please select a vehicle before creating the asset log.")
            )

        if self.odometer < 0:
            raise UserError(
                self.env._("The odometer reading cannot be negative."),
            )

        if self.asset_log_ids:
            return self._action_open_asset_log(self.asset_log_ids[0])

        log = self.env["resource.log"].create(self._prepare_asset_log())

        self.message_post(
            body=Markup(
                "Asset log created: <a href='/web#id=%s&model=resource.log'>%s</a>"
            )
            % (log.id, escape(log.display_name)),
        )
        return self._action_open_asset_log(log)

    def _action_open_asset_log(self, log) -> dict[str, Any]:
        return {
            "name": log.display_name,
            "type": "ir.actions.act_window",
            "res_model": "resource.log",
            "res_id": log.id,
            "view_mode": "form",
            "target": "current",
        }

    def _prepare_asset_log(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "asset_id": self.asset_id.id,
            "approval_request_id": self.id,
            "odometer": self.odometer,
            "source": "approval",
            "state": "done",
            "date": fields.Date.context_today(self, self.date or None),
            "notes": self.env._(
                "Created from approval request: %(request)s", request=self.name
            ),
        }

    def action_view_asset_log(self) -> dict[str, Any]:
        self.check_singleton()

        if not self.asset_id:
            raise UserError(self.env._("No vehicle selected for this approval."))

        domain = [
            ("asset_id", "=", self.asset_id.id),
        ]

        if self.date:
            date_from = self.date - timedelta(days=1)
            date_to = self.date + timedelta(days=1)
            domain.extend(
                [
                    ("date", ">=", date_from),
                    ("date", "<=", date_to),
                ],
            )

        return {
            "name": self.env._("Asset Logs for %s", self.asset_id.display_name),
            "type": "ir.actions.act_window",
            "res_model": "resource.log",
            "view_mode": "list,form",
            "context": clean_context(self.env.context),
            "domain": domain,
        }

    def _get_all_pickings(self):
        _debug.logic("approval_pickings_collect", requests=self)
        return self._get_documents_of_model(
            "stock.picking",
            "stock_move_id",
            "picking_id",
        )

    def _is_stock_target(self) -> bool:
        _debug.logic("approval_is_stock_target", requests=self)
        return self.target_model == "stock.picking"

    def _get_target_line_field(self) -> str:
        if self._is_stock_target():
            return "stock_move_id"
        return super()._get_target_line_field()

    def _get_target_line_parent_field(self) -> str:
        if self._is_stock_target():
            return "picking_id"
        return super()._get_target_line_parent_field()

    def _get_target_document_line_field(self) -> str:
        if self._is_stock_target():
            return "move_ids"
        return super()._get_target_document_line_field()

    def _get_target_line_quantity_field(self) -> str:
        if self._is_stock_target():
            return "product_uom_qty"
        return super()._get_target_line_quantity_field()

    def _get_target_document_name(self) -> str:
        if self._is_stock_target():
            return self.env._("Stock Pickings")
        return super()._get_target_document_name()

    def _get_target_document_label(self) -> str:
        if self._is_stock_target():
            return self.env._("stock picking")
        return super()._get_target_document_label()

    def _check_target_prerequisites(self, lines) -> None:
        super()._check_target_prerequisites(lines)
        if self._is_stock_target():
            lines._check_locations()
            lines._check_picking_type()

    def _get_target_group_key(self, line):
        if not self._is_stock_target():
            return super()._get_target_group_key(line)
        return (
            line.picking_type_id.id,
            line.location_id.id,
            line.location_dest_id.id,
        )

    def _prepare_target_document_values(self, key, lines) -> dict[str, Any]:
        if not self._is_stock_target():
            return super()._prepare_target_document_values(key, lines)
        picking_type_id, location_id, location_dest_id = key
        values = {
            "origin": self.name,
            "picking_type_id": picking_type_id,
            "location_id": location_id,
            "location_dest_id": location_dest_id,
            "company_id": self.company_id.id,
            "date_planned": self.date or fields.Datetime.now(),
        }
        if self.partner_id:
            values["partner_id"] = self.partner_id.id
        return values

    def _prepare_target_line_values(self, line, key, document, lines) -> dict[str, Any]:
        if not self._is_stock_target():
            return super()._prepare_target_line_values(line, key, document, lines)
        picking_type_id, location_id, location_dest_id = key
        return {
            "description_picking": line.description or line.product_id.display_name,
            "product_id": line.product_id.id,
            "product_uom_qty": line.quantity,
            "product_uom_id": (line.product_uom_id or line.product_id.uom_id).id,
            "location_id": location_id,
            "location_dest_id": location_dest_id,
            "company_id": self.company_id.id,
            "picking_type_id": picking_type_id,
            "origin": self.name,
        }

    def _log_target_creation_to_chatter(self) -> None:
        pickings = self.line_ids.stock_move_id.picking_id
        if pickings:
            picking_links = (
                Markup("<ul>")
                + Markup().join(
                    Markup(
                        "<li><a href='/web#id=%(id)s&model=stock.picking'>%(name)s</a></li>",
                    )
                    % {"id": picking.id, "name": picking.name}
                    for picking in pickings
                )
                + Markup("</ul>")
            )

            self._message_log(
                body=Markup("<p><strong>%(header)s</strong></p>%(links)s")
                % {
                    "header": self.env._("Stock pickings created:"),
                    "links": picking_links,
                },
            )

    def _check_confirm(self) -> None:
        super()._check_confirm()
        self._check_stock_type_has_product_lines()
        self._check_asset_log_requirements()

    def _check_stock_type_has_product_lines(self) -> None:
        if self.target_model == "stock.picking":
            if not self.line_ids:
                raise UserError(
                    self.env._(
                        "You cannot confirm an empty stock request. Please add product lines.",
                    ),
                )
            if self.has_product == "no":
                raise UserError(
                    self.env._(
                        "This approval category is configured to create stock pickings "
                        "but does not have product lines enabled. Please contact your administrator.",
                    ),
                )

    def _check_asset_log_requirements(self) -> None:
        if self.approval_type == "asset_log":
            if self.odometer < 0:
                raise UserError(
                    self.env._("The odometer reading cannot be negative."),
                )
            if not self.asset_id:
                raise UserError(
                    self.env._(
                        "You cannot create an asset log without selecting a vehicle."
                    ),
                )
