from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.approval.models.approval_category import CATEGORY_SELECTION

if TYPE_CHECKING:
    from .stock_inventory_adjustment import StockInventoryAdjustment

_debug = DebugLog(__name__)


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[
            ("stock", "Stock Transfer"),
            ("stock_inventory", "Inventory Adjustment"),
            ("asset_log", "Create Asset Log"),
        ],
        ondelete={
            "stock": "cascade",
            "stock_inventory": "cascade",
            "asset_log": "cascade",
        },
    )
    target_model = fields.Selection(
        selection_add=[("stock.picking", "Stock Picking")],
        ondelete={"stock.picking": "cascade"},
    )

    stock_approval_mode = fields.Selection(
        selection=[
            ("picking_type", "Based on Operation Type"),
            ("location", "Based on Locations"),
            ("product", "Based on Product Category"),
            ("combined", "Combined Rules"),
        ],
        default="combined",
        help="What triggers this approval category to be used for stock operations",
    )
    picking_type_ids = fields.Many2many(
        comodel_name="stock.picking.type",
        relation="approval_category_picking_type_rel",
        column1="category_id",
        column2="picking_type_id",
        help="If set, this category applies only to these operation types",
    )
    location_ids = fields.Many2many(
        comodel_name="stock.location",
        relation="approval_category_location_rel",
        column1="category_id",
        column2="location_id",
        help="If set, this category applies when transfer involves these locations (source or destination)",
    )
    stock_product_categ_ids = fields.Many2many(
        comodel_name="product.category",
        relation="approval_category_stock_product_categ_rel",
        column1="category_id",
        column2="product_categ_id",
        help="If set, this category applies when transfer contains these product categories",
    )

    has_asset = fields.Selection(
        selection=CATEGORY_SELECTION,
        string="Vehicle",
        default="no",
        required=True,
        tracking=True,
        help="Specify if an asset must be selected for this type of approval.",
    )
    has_odometer = fields.Selection(
        selection=CATEGORY_SELECTION,
        string="Odometer",
        default="no",
        required=True,
        tracking=True,
        help="Specify if an odometer reading must be provided for this type of approval.",
    )

    @api.onchange("approval_type")
    def _onchange_approval_type(self) -> None:
        if self.approval_type == "asset_log":
            self.has_date = "required"
            self.has_asset = "required"
            self.has_odometer = "required"
            return

        self.has_asset = "no"
        self.has_odometer = "no"
        if self.approval_type == "stock":
            self.has_date = "optional"
            self.has_reference = "optional"
        elif self.approval_type == "stock_inventory":
            self.has_reference = "optional"

    def _get_approval_mode_field(self) -> str:
        if self.approval_type == "stock":
            return "stock_approval_mode"
        return super()._get_approval_mode_field()

    def _get_approval_mode_criteria(self) -> dict[str, tuple[str, ...]]:
        _debug.logic("approval_mode_criteria", categories=self)
        if self.approval_type != "stock":
            return super()._get_approval_mode_criteria()
        return {
            "picking_type": ("picking_type_ids",),
            "location": ("location_ids",),
            "product": ("stock_product_categ_ids",),
        }

    @api.onchange("stock_approval_mode")
    def _onchange_stock_approval_mode(self) -> None:
        self._clear_approval_mode_hidden_criteria()

    def _is_applicable_for(self, document: models.BaseModel) -> bool:
        _debug.logic("approval_applicable_check", categories=self)
        self.check_singleton()
        if document._name == "stock.inventory.adjustment":
            return self._is_applicable_for_inventory_adjustment(document)
        if document._name != "stock.picking":
            return super()._is_applicable_for(document)

        if (
            self.approval_type != "stock"
            or self.target_model
            or not (
                self.picking_type_ids
                or self.location_ids
                or self.stock_product_categ_ids
            )
        ):
            return False

        if self.picking_type_ids:
            if document.picking_type_id not in self.picking_type_ids:
                return False

        if self.location_ids:
            if (
                document.location_id not in self.location_ids
                and document.location_dest_id not in self.location_ids
            ):
                return False

        if self.stock_product_categ_ids:
            picking_categs = document.move_ids.mapped("product_id.categ_id")
            if not any(
                categ in self.stock_product_categ_ids for categ in picking_categs
            ):
                return False

        return True

    def _is_applicable_for_inventory_adjustment(
        self, adjustment: StockInventoryAdjustment
    ) -> bool:
        _debug.logic("approval_applicable_inventory", categories=self)
        self.check_singleton()
        if (
            self.approval_type != "stock_inventory"
            or self.target_model
            or not (self.location_ids or self.stock_product_categ_ids)
        ):
            return False
        lines = adjustment.line_ids
        if self.location_ids and not lines.location_id & self.location_ids:
            return False
        return not (
            self.stock_product_categ_ids
            and not lines.product_id.categ_id & self.stock_product_categ_ids
        )
