from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    intercompany_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Warehouse",
        compute="_compute_intercompany_stock_fields",
        store=True,
        readonly=False,
        help="Default value to set on Purchase(Sales) Orders that will be created based on Sale(Purchase) Orders made to this company",
    )
    intercompany_sync_delivery_receipt = fields.Boolean(
        string="Synchronize Deliveries to your Receipts",
        default=lambda self: self.env["res.groups"]._is_feature_enabled(
            "stock.group_production_lot"
        ),
    )
    intercompany_receipt_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        string="Receipt Operation Type",
        compute="_compute_intercompany_stock_fields",
        store=True,
        readonly=False,
        help="Default Operation type to set on Receipts that will be created for inter-company transfers",
    )

    @api.depends(
        "intercompany_generate_sales_orders", "intercompany_generate_purchase_orders"
    )
    def _compute_intercompany_stock_fields(self) -> None:
        stock_warehouse = dict(
            self.env["stock.warehouse"]._read_group(
                domain=[], groupby=["company_id"], aggregates=["id:recordset"]
            )
        )
        stock_picking_type = dict(
            self.env["stock.picking.type"]._read_group(
                domain=[("code", "=", "incoming")],
                groupby=["company_id"],
                aggregates=["id:recordset"],
            )
        )
        for company in self:
            if not (
                company.intercompany_generate_sales_orders
                or company.intercompany_generate_purchase_orders
            ):
                _debug.logic(
                    "intercompany_stock_fields_cleared",
                    company=company,
                    reason="no_generate_flag",
                )
                company.intercompany_warehouse_id = False
                company.intercompany_receipt_type_id = False
            else:
                if not company.intercompany_warehouse_id:
                    company.intercompany_warehouse_id = stock_warehouse.get(
                        company, [False]
                    )[0]
                if not company.intercompany_receipt_type_id:
                    candidate_types = stock_picking_type.get(
                        company, self.env["stock.picking.type"]
                    )
                    matching_types = candidate_types.filtered_domain(
                        [("warehouse_id", "=", company.intercompany_warehouse_id.id)]
                    )
                    _debug.logic(
                        "intercompany_receipt_type_defaulted",
                        company=company,
                        candidates=len(candidate_types),
                        by="warehouse_match" if matching_types else "first_candidate",
                    )
                    company.intercompany_receipt_type_id = (
                        matching_types or candidate_types
                    )[:1]

    @api.constrains("intercompany_warehouse_id", "intercompany_receipt_type_id")
    def _check_intercompany_receipt_type_matches_warehouse(self) -> None:
        for company in self:
            if (
                company.intercompany_warehouse_id
                and company.intercompany_receipt_type_id
                and company.intercompany_receipt_type_id.warehouse_id
                != company.intercompany_warehouse_id
            ):
                _debug.logic(
                    "intercompany_receipt_type_refused",
                    company=company,
                    warehouse=company.intercompany_warehouse_id,
                    picking_type=company.intercompany_receipt_type_id,
                )
                raise ValidationError(
                    self.env._(
                        "The intercompany receipt operation type must belong to "
                        "the intercompany warehouse (%(warehouse)s).",
                        warehouse=company.intercompany_warehouse_id.display_name,
                    )
                )
