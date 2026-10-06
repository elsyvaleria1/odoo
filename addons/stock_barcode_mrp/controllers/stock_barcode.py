from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import file_open

from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController

_debug = DebugLog(__name__)


class MRPStockBarcode(StockBarcodeController):
    @http.route()
    def main_menu(self, barcode):
        action = self._try_open_production(barcode)
        by = "open_production" if action else "none"  # debuglog
        if not action:
            action = self._try_create_production(barcode)
            by = "create_production" if action else "fallthrough"  # debuglog
        _debug.logic("barcode_main_menu", by=by, matched=bool(action))
        return action or super().main_menu(barcode)

    @http.route("/stock_barcode_mrp/save_barcode_data", type="jsonrpc", auth="user")
    def save_barcode_mrp_data(self, model_vals):
        """Saves data from the barcode app, allows multiple model saves in the same http call

        :param model_vals: list of list with model name,res_id and a dict of write_vals
        :return: the barcode data from the mrp model passed
        """
        for model, res_id, vals in model_vals:
            if res_id == 0:
                record = (
                    request.env[model]
                    .with_context(newByProduct=vals.pop("byProduct", False))
                    .create(vals)
                )
                # difficult to use precompute as there are lots of depends fields to precompute
                if model == "mrp.production":
                    record._compute_move_finished_ids()
            else:
                record = request.env[model].browse(res_id)
                for key in vals:
                    # check if list of dict is passed for creation (for many2many, trace_producing_ids in case of mrp)
                    if isinstance(vals[key], list) and isinstance(vals[key][0], dict):
                        sub_model = request.env[model]._fields[key].comodel_name
                        vals[key] = request.env[sub_model].create(vals[key]).ids
                record.write(vals)
        target_record = record if model == "mrp.production" else record.production_id
        _debug.pipeline(
            "barcode_mrp_saved",
            writes=len(model_vals),
            production=target_record.id,
            state=target_record.state,
        )
        if target_record.state == "draft":
            target_record.action_confirm()
        return target_record._get_stock_barcode_data()

    def _get_barcode_models(self):
        return (*super()._get_barcode_models(), "mrp.production")

    def _get_groups_data(self):
        group_data = super()._get_groups_data()
        group_data.update(
            {
                "group_mrp_byproducts": request.env.user.has_group(
                    "mrp.group_mrp_byproducts"
                )
            }
        )
        return group_data

    def _try_create_production(self, barcode):
        """If barcode represents a manufacure picking type, create and open a
        new manufacturing order.
        """
        picking_type = request.env["stock.picking.type"].search(
            [
                ("barcode", "=", barcode),
                ("code", "=", "mrp_operation"),
                ("company_id", "in", self._get_allowed_company_ids()),
            ],
            limit=1,
        )
        if picking_type:
            return (
                request.env["mrp.production"]
                .with_context(
                    {
                        "default_company_id": picking_type.company_id.id,
                        "default_picking_type_id": picking_type.id,
                    }
                )
                ._get_new_production_client_action()
            )
        return False

    def _try_open_production(self, barcode):
        """If barcode represents a production order, open it"""
        production = request.env["mrp.production"].search(
            [
                ("name", "=", barcode),
            ],
            limit=1,
        )
        if production:
            action = production.action_view_barcode_client_action()
            return {"action": action}
        return False

    @http.route()
    def print_inventory_commands(self, barcode_type=""):
        if (
            barcode_type == "barcode_mrp_commands_and_operation_types"
            and not request.env["stock.picking.type"].has_access(
                "print_mrp_barcode_sheet"
            )
        ):
            raise request.prepare_not_found_error()
        return super().print_inventory_commands(barcode_type=barcode_type)

    def _get_domain_picking_type(self, barcode_type, allowed_company_ids):
        if barcode_type == "barcode_mrp_commands_and_operation_types":
            return [
                ("code", "=", "mrp_operation"),
                ("barcode", "!=", ""),
                ("company_id", "in", allowed_company_ids),
            ]
        return super()._get_domain_picking_type(barcode_type, allowed_company_ids)

    def _get_barcode_pdfs(self, barcode_type, domain):
        barcode_pdfs = super()._get_barcode_pdfs(barcode_type, domain)
        if barcode_type != "barcode_mrp_commands_and_operation_types":
            return barcode_pdfs
        with file_open(
            "stock_barcode_mrp/static/img/barcodes_mrp_actions.pdf", "rb"
        ) as commands_file:
            barcode_pdfs.insert(0, commands_file.read())
        return barcode_pdfs
