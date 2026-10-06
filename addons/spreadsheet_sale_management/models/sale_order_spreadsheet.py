from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)

SALE_ORDER_LINE_FIELDS = [
    "product_id",
    "product_uom_qty",
    "qty_transferred",
    "qty_invoiced",
    "qty_to_invoice",
    "product_uom_id",
    "price_unit",
    "price_tax",
    "price_subtotal",
]


class SaleOrderSpreadsheet(models.Model):
    _name = "sale.order.spreadsheet"
    _inherit = ["mixin.spreadsheet"]
    _description = "Quotation Spreadsheet"
    _access_anchors = frozendict(
        {
            "owner": models.Anchor("order_id.user_id", shared=True),
        }
    )

    name = fields.Char(
        default=lambda self: self.env._("Untitled spreadsheet"),
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    order_id = fields.Many2one(
        comodel_name="sale.order",
        index="btree_not_null",
        ondelete="cascade",
    )

    def get_formview_action(self, access_uid=None):
        return self.action_view_spreadsheet()

    @api.model_create_multi
    def create(self, vals_list):
        spreadsheets = super().create(vals_list)
        for spreadsheet, vals in zip(spreadsheets, vals_list, strict=True):
            needs_list = not spreadsheet.order_id and not (
                "spreadsheet_binary_data" in vals or "spreadsheet_data" in vals
            )
            _debug.lifecycle(
                "quotation_spreadsheet_created",
                records=spreadsheet,
                order=spreadsheet.order_id or None,
                insert_list=needs_list,
            )
            if needs_list:
                spreadsheet._dispatch_insert_list_revision()
        return spreadsheets

    def action_view_spreadsheet(self):
        return {
            "type": "ir.actions.client",
            "tag": "action_sale_order_spreadsheet",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

    def _get_spreadsheet_metadata(self, access_token=None):
        data = super()._get_spreadsheet_metadata(access_token)
        data["order_id"] = self.order_id.id
        data["order_display_name"] = self.order_id.display_name
        return data

    def _empty_spreadsheet_data(self):
        data = super()._empty_spreadsheet_data()
        data["lists"] = {
            "1": {
                "columns": SALE_ORDER_LINE_FIELDS,
                "domain": [("display_type", "=", False)],
                "model": "sale.order.line",
                "context": {},
                "orderBy": [],
                "id": "1",
                "name": self.env._("Sale order lines"),
                "fieldMatching": {
                    "order_filter_id": {"chain": "order_id", "type": "many2one"}
                },
            }
        }
        data["globalFilters"] = [
            {
                "id": "order_filter_id",
                "type": "relation",
                "label": self.env._("Quote"),
                "modelName": "sale.order",
            }
        ]
        return data

    def _dispatch_insert_list_revision(self) -> None:
        command = {
            "sheetId": "sheet1",
            "col": 0,
            "row": 0,
            "id": "1",
            "linesNumber": 100,
            "columns": [
                {
                    "name": field_name,
                    "type": self.env["sale.order.line"]._fields[field_name].type,
                }
                for field_name in SALE_ORDER_LINE_FIELDS
            ],
            "type": "RE_INSERT_ODOO_LIST",
        }
        table_command = {
            "type": "CREATE_TABLE",
            "sheetId": "sheet1",
            "tableType": "static",
            "ranges": [
                {
                    "_sheetId": "sheet1",
                    "_zone": {
                        "top": 0,
                        "bottom": 100,
                        "left": 0,
                        "right": len(SALE_ORDER_LINE_FIELDS) - 1,
                    },
                }
            ],
            "config": {
                "firstColumn": False,
                "hasFilters": False,
                "totalRow": False,
                "lastColumn": False,
                "numberOfHeaders": 1,
                "bandedRows": True,
                "bandedColumns": False,
                "styleId": "TableStyleMedium5",
            },
        }
        self._dispatch_commands([command, table_command])

    @api.readonly
    @api.model
    def get_spreadsheets(self, domain=(), offset=0, limit=None) -> dict:
        domain = Domain.AND([domain, [("order_id", "=", False)]])
        return super().get_spreadsheets(domain, offset, limit)

    @api.model
    def _get_spreadsheet_selector(self) -> dict | None:
        return {
            "model": self._name,
            "display_name": self.env._("Quotation templates"),
            "sequence": 20,
            "allow_create": False,
        }
