from typing import TYPE_CHECKING, Literal, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import frozendict

from odoo.addons.approval.models.approval_utils import is_approval_manager

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_request import ApprovalRequest


class ApprovalRequestLine(models.Model):
    _name = "approval.request.line"
    _description = "Request Line"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "approval_request_approver_delegate": models.Anchor(
                "approval_request_id.approver_ids.delegate_id", kind="owner"
            ),
            "approval_request_approver_user": models.Anchor(
                "approval_request_id.approver_ids.user_id", kind="owner"
            ),
            "approval_request_category_allowed_group_all_user": models.Anchor(
                "approval_request_id.category_id.allowed_group_ids.all_user_ids",
                kind="owner",
            ),
            "approval_request_category_allowed_user": models.Anchor(
                "approval_request_id.category_id.allowed_user_ids", kind="owner"
            ),
            "company": models.Anchor("company_id", shared=False),
            "owner": "approval_request_id.request_owner_id",
        }
    )

    approval_request_id = fields.Many2one(
        comodel_name="approval.request",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="approval_request_id.company_id",
        string="Company",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        check_company=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Products",
        index=True,
        required=True,
        check_company=True,
    )
    product_template_id = fields.Many2one(
        comodel_name="product.template",
        related="product_id.product_tmpl_id",
    )
    allowed_product_ids = fields.Many2many(
        comodel_name="product.product",
        compute="_compute_allowed_product_ids",
        help="Products selectable on this line, mirroring the category's "
        "allowed products. Empty means the category sets no restriction and "
        "every product is selectable — the views drop the domain in that case "
        "rather than listing the whole catalogue here.",
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_product_uom_id",
        precompute=True,
        store=True,
        readonly=False,
    )
    quantity = fields.Float(default=1.0)
    price_unit = fields.Float(
        string="Price",
        default=1.0,
    )
    price_subtotal = fields.Float(
        string="Total",
        compute="_compute_price_subtotal",
        store=True,
    )
    description = fields.Char(
        compute="_compute_description",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        request_ids = {vals.get("approval_request_id") for vals in vals_list}
        request_ids.discard(False)
        requests = self.env["approval.request"].sudo().browse(request_ids)
        self._check_access_request(requests)
        self._check_business_rules_request(requests)
        return super().create(vals_list)

    _LINE_SYSTEM_FIELDS: frozenset[str] = frozenset()

    def _get_fields_line_system(self) -> frozenset[str]:
        return self._LINE_SYSTEM_FIELDS

    def write(self, vals: ValuesType) -> Literal[True]:
        if vals and self.env.su and set(vals) <= self._get_fields_line_system():
            return super().write(vals)
        requests = self.approval_request_id
        if "approval_request_id" in vals:
            target = (
                self.env["approval.request"]
                .sudo()
                .browse(
                    vals["approval_request_id"],
                )
            )
            requests |= target
        self._check_access_request(requests)
        self._check_business_rules_request(requests)
        return super().write(vals)

    def unlink(self) -> Literal[True]:
        self._check_access_request(self.approval_request_id)
        self._check_business_rules_request(self.approval_request_id)
        return super().unlink()

    def _check_access_request(self, requests: ApprovalRequest) -> None:
        if self.env.su or is_approval_manager(self.env):
            return
        current_user = self.env.user
        for request in requests:
            if request.request_owner_id != current_user:
                raise AccessError(
                    self.env._(
                        "You can only modify product lines on your own "
                        "approval requests.\n\n"
                        "Request: %(name)s\nOwner: %(owner)s",
                        name=request.name or request.category_id.name,
                        owner=request.request_owner_id.name,
                    ),
                )

    def _check_business_rules_request(self, requests: ApprovalRequest) -> None:
        for request in requests:
            if request.state != "new":
                raise ValidationError(
                    self.env._(
                        "Cannot modify product lines after the request "
                        "has been submitted — approvers decide on these "
                        "values.\n\n"
                        "Request: %(name)s\nCurrent state: %(state)s",
                        name=request.name or request.category_id.name,
                        state=request.state,
                    ),
                )

    @api.constrains("quantity")
    def _check_quantity(self) -> None:
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(
                    self.env._(
                        "Quantity must be positive. "
                        "Got: %(qty)s for product %(product)s",
                        qty=line.quantity,
                        product=line.product_id.display_name,
                    ),
                )

    @api.constrains("price_unit")
    def _check_price_unit(self) -> None:
        for line in self:
            if line.price_unit < 0:
                raise ValidationError(
                    self.env._(
                        "Price cannot be negative. "
                        "Got: %(price)s for product %(product)s",
                        price=line.price_unit,
                        product=line.product_id.display_name,
                    ),
                )

    @api.onchange("approval_request_id")
    def _onchange_approval_request_id(self) -> None:
        if self.approval_request_id and not self.partner_id:
            self.partner_id = self.approval_request_id.partner_id

    @api.depends("product_id")
    def _compute_description(self) -> None:
        for line in self:
            line.description = (
                line.product_id.description_purchase or line.product_id.display_name
            )

    @api.depends("approval_request_id.category_id.product_ids")
    def _compute_allowed_product_ids(self) -> None:
        for line in self:
            line.allowed_product_ids = line.approval_request_id.category_id.product_ids

    @api.depends("product_id")
    def _compute_product_uom_id(self) -> None:
        for line in self:
            line.product_uom_id = line.product_id.uom_id

    @api.depends("quantity", "price_unit")
    def _compute_price_subtotal(self) -> None:
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit
