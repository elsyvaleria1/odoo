import re
from collections import defaultdict
from itertools import batched

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools import pdf
from odoo.tools.misc import file_open

from odoo.addons.stock_barcode.models.epc_encoder import EpcScheme

_debug = DebugLog(__name__)

LABELS_PER_RENDER = 112


class StockBarcodeController(http.Controller):
    @http.route("/stock_barcode/scan_from_main_menu", type="jsonrpc", auth="user")
    def main_menu(self, barcode):
        """Receive a barcode scanned from the main menu and return the appropriate
        action (open an existing / new picking) or warning.
        """
        _debug.pipeline("barcode_main_menu_enter", barcode=barcode)
        # The main menu opens with no company in its context, so the request would read the
        # user's default company: its nomenclature, and every company's records.
        request.update_context(allowed_company_ids=self._get_allowed_company_ids())
        barcode_type = None
        nomenclature = request.env.company.sudo().barcodes_config_id.nomenclature_id
        parsed_results = nomenclature.parse_barcode(barcode)
        if parsed_results and nomenclature.is_gs1_nomenclature:
            # search with the last feasible rule
            for result in parsed_results[::-1]:
                if result["type"] in (
                    "product",
                    "package",
                    "location",
                    "location_dest",
                ):
                    barcode_type = result["type"]
                    break

        # Alias support
        elif parsed_results:
            first_result = (
                parsed_results[0]
                if isinstance(parsed_results, list)
                else parsed_results
            )
            if first_result.get("type") in ("price", "weight"):
                # A price or weight embedded in the barcode: the product's own barcode is
                # the scanned one with those digits zeroed.
                barcode = first_result["base_code"]
                barcode_type = "product"
            else:
                barcode = first_result.get("code", barcode)

        if not barcode_type:
            ret_open_picking = self._try_open_picking(barcode)
            if ret_open_picking:
                return ret_open_picking

            ret_open_picking_type = self._try_open_picking_type(barcode)
            if ret_open_picking_type:
                return ret_open_picking_type

        if request.env.user.has_group("stock.group_stock_multi_locations") and (
            not barcode_type or barcode_type in ("location", "location_dest")
        ):
            ret_new_internal_picking = self._try_new_internal_picking(barcode)
            if ret_new_internal_picking:
                return ret_new_internal_picking

        if not barcode_type or barcode_type == "product":
            ret_open_product_location = self._try_open_product_location(barcode)
            if ret_open_product_location:
                return ret_open_product_location

        # The GS1 classification above never yields "lot": a lot-only barcode stays
        # unclassified and reaches here through `product.trace._search`'s GS1 unwrapping.
        if not barcode_type and request.env.user.has_group(
            "stock.group_production_lot"
        ):
            ret_open_lot = self._try_open_lot(barcode)
            if ret_open_lot:
                return ret_open_lot

        if request.env.user.has_group("stock.group_tracking_lot") and (
            not barcode_type or barcode_type == "package"
        ):
            ret_open_package = self._try_open_package(barcode)
            if ret_open_package:
                return ret_open_package

        if request.env.user.has_group("stock.group_stock_multi_locations"):
            return {
                "warning": request.env._(
                    "No picking or location or product corresponding to barcode %(barcode)s",
                    barcode=barcode,
                )
            }
        else:
            return {
                "warning": request.env._(
                    "No picking or product corresponding to barcode %(barcode)s",
                    barcode=barcode,
                )
            }

    def _get_barcode_models(self):
        """The models the barcode client action may be asked for data about.

        `model` arrives from the client on every data route, so it is checked
        against this set rather than trusted: an unknown name reaches the ORM as
        a KeyError and a known-but-unsupported one dies on a missing
        `_get_stock_barcode_data`, both as a 500 with a traceback.

        This is a hook, not a literal, because the client action is registered
        for further models by the modules that add them -- `stock.picking.batch`
        and `mrp.production` today. A closed list here answers the data route of
        every one of those with "not a barcode operation model", which is not a
        degraded mode: their client action mounts with no data at all.
        """
        return ("stock.picking", "stock.quant")

    def _get_barcode_records(self, model):
        """The empty recordset of a barcode operation model, in the companies the switcher
        selected: reading and saving an operation must see the same company."""
        self._check_barcode_model(model)
        return request.env[model].with_context(
            allowed_company_ids=self._get_allowed_company_ids()
        )

    def _check_barcode_draft(self, records):
        if not hasattr(records, "_create_from_barcode_draft"):
            raise UserError(
                request.env._(
                    "%s cannot be opened before it is created.", records._description
                )
            )
        return records

    def _check_barcode_model(self, model):
        _debug.logic("barcode_model_check", model=model)
        if model not in self._get_barcode_models():
            raise UserError(
                request.env._("%s is not a barcode operation model.", model)
            )
        return model

    @http.route("/stock_barcode/save_barcode_data", type="jsonrpc", auth="user")
    def save_barcode_data(self, model, res_id, write_field, write_vals, draft=None):
        _debug.pipeline("barcode_save", model=model, res_id=res_id)
        records = self._get_barcode_records(model)
        if not res_id and draft:
            res_id = (
                self._check_barcode_draft(records)._create_from_barcode_draft(draft).id
            )
        if not res_id:
            return records.barcode_write(write_vals)
        target_record = records.browse(res_id)
        if not write_vals:
            return target_record._get_stock_barcode_data()
        if write_field not in records._fields:
            raise UserError(
                request.env._(
                    "%(field)s is not a field of %(model)s.",
                    field=write_field,
                    model=model,
                )
            )
        target_record.with_context(avoid_putaway_rules=True).write(
            {write_field: write_vals}
        )
        return target_record._get_stock_barcode_data()

    @http.route("/stock_barcode/get_barcode_data", type="jsonrpc", auth="user")
    def get_barcode_data(self, model, res_id, draft=None):
        """Returns a dict with values used by the barcode client:
        {
            "data": <data used by the stock barcode> {'records' : {'model': [{<record>}, ... ]}, 'other_infos':...}, _get_stock_barcode_data
            "groups": <security group>, self._get_groups_data
        }
        """
        _debug.pipeline("barcode_data_read", model=model, res_id=res_id)
        target_record = self._get_barcode_records(model)
        if res_id:
            data = target_record.browse(res_id)._get_stock_barcode_data()
        elif draft:
            data = self._check_barcode_draft(
                target_record
            )._get_stock_barcode_draft_data(draft)
        else:
            data = target_record._get_stock_barcode_data()
        data["records"].update(self._get_barcode_nomenclature())
        data["precision"] = request.env["decimal.precision"].get_precision(
            "Product Unit"
        )
        params = request.env["ir.config_parameter"].sudo()
        config = data.setdefault("config", {})
        config["play_sound"] = self._get_play_sound()
        config["barcode_separator_regex"] = params.get_param(
            "stock_barcode.barcode_separator_regex", ".^"
        )
        config["barcode_rfid_batch_time"] = params.get_param_int(
            "stock_barcode.barcode_rfid_batch_time", 1000
        )
        delay_between_scan = params.get_param_int(
            "stock_barcode.delay_between_scan", None
        )
        if delay_between_scan is not None:
            config["delay_between_scan"] = delay_between_scan
        return {
            "data": data,
            "groups": self._get_groups_data(),
        }

    def _get_play_sound(self):
        return not (
            request.env.registry.settings.get_bool(
                request.env, "stock_barcode.mute_sound_notifications"
            )
        )

    @http.route("/stock_barcode/get_main_menu_data", type="jsonrpc", auth="user")
    def get_main_menu_data(self):
        _debug.perf.count("barcode_main_menu_data")
        user = request.env.user
        groups = {
            "locations": user.has_group("stock.group_stock_multi_locations"),
            "package": user.has_group("stock.group_tracking_lot"),
            "tracking": user.has_group("stock.group_production_lot"),
        }
        quant_count = request.env["stock.quant"].search_count(
            [
                "|",
                ("user_id", "=", user.id),
                ("user_id", "=", False),
                ("company_id", "=", self._get_allowed_company_ids()[0]),
                ("location_id.usage", "in", ["internal", "transit"]),
                ("inventory_date", "<=", fields.Date.context_today(user)),
                ("inventory_quantity_set", "=", False),
            ]
        )
        return {
            "groups": groups,
            "play_sound": self._get_play_sound(),
            "quant_count": quant_count,
        }

    @http.route("/stock_barcode/get_specific_barcode_data", type="jsonrpc", auth="user")
    def get_specific_barcode_data(self, **kwargs):
        """This method gets multiple records data from different models for the given barcode(s).
        The goal is to do one search by model (plus the additional record, e.g. the UOM records when
        fetching product's records.)
        :param kwargs:
            ''barcode'': a single barcode (string), used when not knowing which model is linked.
            ''barcodes_by_model'': a dict of model_name -> barcode list
            ''context''
            ''barcodes'': several barcodes, used like ''barcode''
            ''domains_by_model'': a dict of model_name -> domain, ''all'' applying to every model
            ''fetch_quants'': Fetch extra quants based on products (used in inventory)
        :return: ``{"records": {model: [record, ...]}, "products_with_all_quants": [id, ...]}``,
            the latter naming the products whose every internal quant ``records`` carries, so
            the client knows it has them all rather than guessing it from barcodes.
        """
        _debug.perf.count("barcode_specific_data")
        context = kwargs.get("context", {})
        context.update(request.env.context)
        context["display_default_code"] = False
        request.update_env(context=context)
        barcodes_by_model = kwargs.get("barcodes_by_model")
        domains_by_model = kwargs.get("domains_by_model", {})
        universal_domain = Domain(domains_by_model.get("all") or Domain.TRUE)
        fetch_quant = kwargs.get("fetch_quants")
        result = defaultdict(list)

        # If a barcode was given but no model was specified, search for it for all relevant models.
        if not barcodes_by_model:
            barcode_field_by_model = self._get_barcode_field_by_model()
            barcodes = kwargs.get("barcodes") or [kwargs.get("barcode")]
            barcodes_by_model = dict.fromkeys(barcode_field_by_model.keys(), barcodes)

        for model_name, barcodes in barcodes_by_model.items():
            if not barcodes:
                continue
            barcode_field = self._get_barcode_field(model_name)
            # GS1 zero-padding is stripped by `_preprocess_gs1_search_args` inside each model's
            # `_search` override (`barcodes_gs1_nomenclature`), for every operator this domain
            # can use. This controller used to redo it by hand — `str(int(barcode))` plus an
            # `ilike` — which produced exactly the same rows while hiding where the unpadding
            # actually happens. Measured: with the GS1 nomenclature active, `('barcode', 'in',
            # ['0000000012345'])` already matches the record stored as `12345`.
            domain = Domain(barcode_field, "in", barcodes)
            # Adds additionnal domain if applicable.
            domain_for_this_model = domains_by_model.get(model_name)
            if domain_for_this_model:
                domain &= Domain(domain_for_this_model)
            domain &= universal_domain
            # Search for barcodes' records.
            records = request.env[model_name].search(domain)
            fetched_data = self._get_records_fields_stock_barcode(records)
            for f_model_name in fetched_data:
                result[f_model_name] += fetched_data[f_model_name]

        # Counting needs every internal quant of a product it may count: those of each product
        # the answer carries, whichever record brought it (a packaging, a package's content).
        product_ids = (
            sorted({product["id"] for product in result["product.product"]})
            if fetch_quant
            else []
        )
        if product_ids:
            quants = request.env["stock.quant"]._get_barcode_counting_quants(
                request.env["product.product"].browse(product_ids)
            )
            fetched_data = self._get_records_fields_stock_barcode(quants)

            for f_model_name in fetched_data:
                result[f_model_name] += fetched_data[f_model_name]
        return {
            "records": result,
            "products_with_all_quants": product_ids,
        }

    def _get_barcode_field(self, model_name):
        """`model_name` arrives from the client: a name that is no model, or a model this
        module does not scan, is refused rather than dying as a KeyError/AttributeError 500."""
        barcode_field = model_name in request.env and getattr(
            request.env[model_name], "_barcode_field", None
        )
        if not barcode_field:
            raise UserError(
                request.env._("%s is not a barcode operation model.", model_name)
            )
        return barcode_field

    def _get_records_fields_stock_barcode(self, records):
        result = defaultdict(list)
        result[records._name] = records.read(
            records._get_fields_stock_barcode(), load=False
        )
        if hasattr(records, "_get_stock_barcode_specific_data"):
            records_data_by_model = records._get_stock_barcode_specific_data()
            for res_model in records_data_by_model:
                result[res_model] += records_data_by_model[res_model]
        return result

    @http.route("/stock_barcode/get_quants", type="jsonrpc", auth="user")
    def get_existing_quant_and_related_data(self, product_ids):
        """Every internal quant of the products, which the answer states it completes. It
        took a domain from the client, whose completeness only the client could assume."""
        products = request.env["product.product"].browse(product_ids).exists()
        Quant = request.env["stock.quant"]
        data = Quant._get_barcode_counting_quants(
            products
        ).get_stock_barcode_data_records()
        data["products_with_all_quants"] = products.ids
        return data

    @http.route(
        "/stock_barcode/rid_of_message_demo_barcodes", type="jsonrpc", auth="user"
    )
    def rid_of_message_demo_barcodes(self, **kw):
        """Edit the main_menu client action so that it doesn't display the 'print demo barcodes sheet' message"""
        if not request.env["stock.picking.type"].has_access("print_barcode_sheet"):
            raise request.prepare_not_found_error()
        request.env.ref("stock_barcode.stock_barcode_action_main_menu").sudo().write(
            {"params": {"message_demo_barcodes": False}}
        )

    @http.route("/stock_barcode/print_inventory_commands", type="http", auth="user")
    def print_inventory_commands(self, barcode_type=""):
        if not request.env["stock.picking.type"].has_access("print_barcode_sheet"):
            raise request.prepare_not_found_error()
        # The default used to be `False`, which the body then fed to `'operation_types' in
        # barcode_type` — a TypeError, so the route 500'd when hit without its parameter.
        barcode_type = barcode_type or ""

        # make sure we use the selected company if possible
        allowed_company_ids = self._get_allowed_company_ids()

        # same domain conditions for picking types and locations
        domain = self._get_domain_picking_type(barcode_type, allowed_company_ids)

        # get fixed command barcodes
        barcode_pdfs = self._get_barcode_pdfs(barcode_type, domain)

        if not barcode_pdfs:
            raise UserError(request.env._("Barcodes are not available."))
        merged_pdf = pdf.merge_pdf(barcode_pdfs)

        pdfhttpheaders = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(merged_pdf)),
        ]

        return request.prepare_response(merged_pdf, headers=pdfhttpheaders)

    def _try_open_lot(self, barcode):
        """If barcode represent a lot, open a form view to show all
        the details of this lot.
        """
        _debug.logic("barcode_try", kind="lot", barcode=barcode)
        result = request.env["product.trace"].search_read(
            [
                ("name", "=", barcode),
            ],
            ["id", "display_name"],
            limit=1,
        )
        if result:
            return {
                "action": {
                    "name": request.env._("Open lot"),
                    "res_model": "product.trace",
                    "views": [
                        (request.env.ref("stock.view_product_trace_form").id, "form")
                    ],
                    "type": "ir.actions.act_window",
                    "res_id": result[0]["id"],
                }
            }
        return False

    def _try_open_product_location(self, barcode):
        """If the barcode represents a product or its UoM, open a list/kanban view
        to show all the locations of this product.
        """
        _debug.logic("barcode_try", kind="product_location", barcode=barcode)
        if result := request.env["product.product"].search_read(
            [("barcode", "=", barcode)], ["id", "display_name"], limit=1
        ):
            product_id, product_display_name = (
                result[0]["id"],
                result[0]["display_name"],
            )
        # Ignore UoM barcode if the UoM setting is toggled off.
        elif result := self.env.user.has_group("base.group_uom") and request.env[
            "product.uom"
        ].search_read([("barcode", "=", barcode)], ["product_id"], limit=1):
            product_id, product_display_name = result[0]["product_id"]
        if result:
            tree_view_id = request.env.ref("stock.view_stock_quant_list").id
            kanban_view_id = request.env.ref(
                "stock_barcode.stock_quant_barcode_kanban_2"
            ).id
            return {
                "action": {
                    "name": product_display_name,
                    "res_model": "stock.quant",
                    "views": [(tree_view_id, "list"), (kanban_view_id, "kanban")],
                    "type": "ir.actions.act_window",
                    "domain": [("product_id", "=", product_id)],
                    "context": {
                        "search_default_internal_loc": True,
                    },
                    "mobile_view_mode": "kanban",
                }
            }
        return False

    def _try_open_picking_type(self, barcode):
        """If barcode represent a picking type, open a new
        picking with this type
        """
        _debug.logic("barcode_try", kind="picking_type", barcode=barcode)
        picking_type = request.env["stock.picking.type"].search(
            [
                ("barcode", "=", barcode),
                ("company_id", "in", self._get_allowed_company_ids()),
            ],
            limit=1,
        )
        if picking_type:
            Picking = request.env["stock.picking"]
            action = Picking._action_open_barcode_draft(
                Picking._prepare_barcode_draft_vals(picking_type)
            )
            return {"action": action}
        return False

    def _try_open_picking(self, barcode):
        """If barcode represents a picking, open it"""
        _debug.logic("barcode_try", kind="picking", barcode=barcode)
        corresponding_picking = request.env["stock.picking"].search(
            [
                ("name", "=", barcode),
            ],
            limit=1,
        )
        if corresponding_picking:
            action = corresponding_picking.action_view_picking_client_action()
            return {"action": action}
        return False

    def _try_open_package(self, barcode):
        """If barcode represents a package, open it."""
        _debug.logic("barcode_try", kind="package", barcode=barcode)
        package = request.env["stock.package"].search([("name", "=", barcode)], limit=1)
        if package:
            view_id = request.env.ref("stock.view_stock_package_form").id
            return {
                "action": {
                    "name": request.env._("Open package"),
                    "res_model": "stock.package",
                    "views": [(view_id, "form")],
                    "type": "ir.actions.act_window",
                    "res_id": package.id,
                    "context": {"active_id": package.id},
                }
            }
        return False

    def _try_new_internal_picking(self, barcode):
        """If barcode represents a location, open a new picking from this location"""
        corresponding_location = request.env["stock.location"].search(
            [
                ("barcode", "=", barcode),
                ("usage", "=", "internal"),
                ("company_id", "=", self._get_allowed_company_ids()[0]),
            ],
            limit=1,
        )
        if corresponding_location:
            internal_picking_type_domain = Domain("code", "=", "internal")
            if warehouse := corresponding_location.warehouse_id:
                internal_picking_type_domain &= Domain(
                    "warehouse_id", "=", warehouse.id
                )
            internal_picking_type = request.env["stock.picking.type"].search(
                internal_picking_type_domain, limit=1
            )
            dest_loc = corresponding_location
            while dest_loc.location_id and dest_loc.location_id.usage == "internal":
                dest_loc = dest_loc.location_id
            if internal_picking_type:
                action = request.env["stock.picking"]._action_open_barcode_draft(
                    {
                        "picking_type_id": internal_picking_type.id,
                        "user_id": False,
                        "location_id": corresponding_location.id,
                        "location_dest_id": dest_loc.id,
                    },
                    confirm=True,
                )
                return {"action": action}
            else:
                return {
                    "warning": request.env._(
                        "No internal operation type. Please configure one in warehouse settings."
                    )
                }
        return False

    def _get_allowed_company_ids(self):
        """Return the allowed_company_ids based on cookies.

        Currently request.env.company returns the current user's company when called within a controller
        rather than the selected company in the company switcher and request.env.companies lists the
        current user's allowed companies rather than the selected companies.

        :returns: List of active companies. The first company id in the returned list is the selected company.
        """
        # The cookie is client-controlled text: it is parsed defensively (a malformed one used
        # to raise ValueError and 500 the route) and intersected with the companies the user is
        # actually allowed, so a forged value cannot widen the scope of the searches built on it.
        default = request.env.user.company_id.ids
        allowed_ids = request.env.user.company_ids.ids
        cids = [
            cid
            for cid in request.env["ir.http"]._get_cookie_company_ids()
            if cid in allowed_ids
        ]
        return cids or default

    def _get_domain_picking_type(self, barcode_type, allowed_company_ids):
        return [
            ("barcode", "!=", ""),
            ("company_id", "in", allowed_company_ids),
        ]

    def _get_barcode_pdfs(self, barcode_type, domain):
        barcode_pdfs = []
        if barcode_type == "barcode_commands_and_operation_types":
            with file_open(
                "stock_barcode/static/img/barcodes_actions.pdf", "rb"
            ) as commands_file:
                barcode_pdfs.append(commands_file.read())

        if "operation_types" in barcode_type:
            # get picking types barcodes
            picking_type_ids = request.env["stock.picking.type"].search(domain)
            for picking_type_batch in batched(
                picking_type_ids.ids, LABELS_PER_RENDER, strict=False
            ):
                picking_types_pdf, _content_type = request.env[
                    "ir.actions.report"
                ]._render_qweb_pdf(
                    "stock.action_report_picking_type_label", picking_type_batch
                )
                if picking_types_pdf:
                    barcode_pdfs.append(picking_types_pdf)

        # get locations barcodes
        if barcode_type == "locations" and request.env.user.has_group(
            "stock.group_stock_multi_locations"
        ):
            locations_ids = request.env["stock.location"].search(domain)
            for location_ids_batch in batched(
                locations_ids.ids, LABELS_PER_RENDER, strict=False
            ):
                locations_pdf, _content_type = request.env[
                    "ir.actions.report"
                ]._render_qweb_pdf(
                    "stock.action_report_location_barcode", location_ids_batch
                )
                if locations_pdf:
                    barcode_pdfs.append(locations_pdf)
        return barcode_pdfs

    def _get_groups_data(self):
        return {
            "group_stock_multi_locations": request.env.user.has_group(
                "stock.group_stock_multi_locations"
            ),
            "group_tracking_owner": request.env.user.has_group(
                "stock.group_tracking_owner"
            ),
            "group_tracking_lot": request.env.user.has_group(
                "stock.group_tracking_lot"
            ),
            "group_production_lot": request.env.user.has_group(
                "stock.group_production_lot"
            ),
            "group_uom": request.env.user.has_group("base.group_uom"),
            "group_stock_sign_delivery": request.env.user.has_group(
                "stock.group_stock_sign_delivery"
            ),
        }

    def _get_barcode_nomenclature(self):
        company = request.env["res.company"].browse(self._get_allowed_company_ids()[0])
        nomenclature = company.barcodes_config_id.nomenclature_id
        return {
            "barcode.nomenclature": nomenclature.read(load=False),
            "barcode.rule": nomenclature.rule_ids.read(load=False),
        }

    def _get_barcode_field_by_model(self):
        list_model = [
            "stock.location",
            "product.product",
            "uom.uom",
            "product.uom",
            "stock.picking",
            "product.trace",
            "stock.package",
            "stock.package.type",
        ]
        return {
            model: request.env[model]._barcode_field
            for model in list_model
            if hasattr(request.env[model], "_barcode_field")
        }

    @http.route("/stock_barcode/get_epc", type="jsonrpc", auth="user")
    def get_epc(
        self,
        scheme_name,
        element_string_list,
        company_prefix_length=None,
        filter_value=None,
    ):
        scheme = EpcScheme(self.env, scheme_name)
        return {
            element_string: scheme.encode(
                element_string, filter_value, company_prefix_length
            )
            for element_string in element_string_list
        }

    @http.route("/stock_barcode/get_epc_sgtin", type="jsonrpc", auth="user")
    def get_epc_sgtin(
        self,
        gtin,
        tracking_number_list,
        filter_value,
        company_prefix_length,
        alphanumeric_tracking=False,
    ):
        """Get a batch of SGTIN EPC for a defined product with a list of tracking numbers
        :param gtin: GTIN of the product
        :param tracking_number_list: List of tracking numbers
        :param alphanumeric_tracking: True if any tracking number is alphanumeric
        :param filter_value: Filter value for SGTIN EPC as defined in [TDS2.1]§10.2
        :param company_prefix_length: Length of the company prefix
        """
        if not re.match(r"^\d+$", gtin or ""):
            raise UserError(request.env._("A GTIN can only contain digits."))
        if not tracking_number_list:
            raise UserError(
                request.env._(
                    "At least one tracking number is required to build an EPC."
                )
            )

        scheme_name, field_name = (
            ("sgtin-198", "serial_string")
            if alphanumeric_tracking
            else ("sgtin-96", "serial_integer")
        )
        scheme = EpcScheme(self.env, scheme_name)
        results = {}
        element_string = f"(01) {gtin} (21) {tracking_number_list[0]}"
        # First call to encode may raise an exception if technical fields (header, partition, filter...) are invalid
        results[tracking_number_list[0]] = scheme.encode(
            element_string, filter_value, company_prefix_length
        )
        # Since we operate on a single product, we can reuse the base encoding for all the tracking numbers to fasten the process
        for tracking_number in tracking_number_list[1:]:
            results[tracking_number] = scheme.encode_partial(
                field_name, tracking_number
            )
        return results
