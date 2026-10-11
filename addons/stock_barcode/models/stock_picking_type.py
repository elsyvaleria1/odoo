from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"
    _access_verbs = {"print_barcode_sheet": models.Verb(requires="read")}

    barcode_allow_extra_product = fields.Boolean(
        string="Allow extra products",
        default=True,
        tracking=True,
        help="For planned transfers, allow adding non-reserved products",
    )
    barcode_validation_after_dest_location = fields.Boolean(
        string="Force a destination for all products",
        tracking=True,
    )
    barcode_validation_all_product_packed = fields.Boolean(
        string="Force all products to be packed",
        tracking=True,
    )
    barcode_validation_full = fields.Boolean(
        string="Allow full picking validation",
        default=True,
        tracking=True,
        help="Allow validating a picking even if nothing has been scanned yet, i.e. do an immediate transfer",
    )
    restrict_scan_product = fields.Boolean(
        string="Force Product scan?",
        tracking=True,
        help="A line's product must be scanned before the line can be edited",
    )
    restrict_put_in_pack = fields.Selection(
        selection=[
            ("mandatory", "After each product"),
            ("optional", "After group of products"),
            ("no", "No"),
        ],
        string="Force put in pack?",
        default="optional",
        required=True,
        tracking=True,
        help="Does the picker have to put the scanned products in a package? If yes, when?",
    )
    restrict_scan_tracking_number = fields.Selection(
        selection=[
            ("mandatory", "Mandatory Scan"),
            ("optional", "Optional Scan"),
        ],
        string="Force Lot/Serial scan?",
        default="optional",
        required=True,
        tracking=True,
    )
    restrict_scan_source_location = fields.Selection(
        selection=[
            ("no", "No Scan"),
            ("mandatory", "Mandatory Scan"),
        ],
        string="Force Source Location scan?",
        default="no",
        required=True,
        tracking=True,
    )
    restrict_scan_dest_location = fields.Selection(
        selection=[
            ("mandatory", "After each product"),
            ("optional", "After group of products"),
            ("no", "No"),
        ],
        string="Force Destination Location scan?",
        default="optional",
        required=True,
        tracking=True,
        help="Does the picker have to scan the destination? If yes, when?",
    )
    show_barcode_validation = fields.Boolean(
        compute="_compute_show_barcode_validation",
        help='Technical field used to compute whether the "Final Validation" group should be displayed, to support combined groups/invisible complexity.',
    )
    show_reserved_sns = fields.Boolean(
        string="Show reserved lots/SN",
        tracking=True,
        help="Display reserved lots/serial numbers. When not active, the picker can pick lots/serials as they want.",
    )
    is_barcode_picking_type = fields.Boolean(
        compute="_compute_is_barcode_picking_type",
        help="Technical field indicating if type should be used in barcode app and used to control visibility in the related UI.",
    )

    @api.depends(
        "code",
        "restrict_scan_product",
        "restrict_put_in_pack",
        "restrict_scan_dest_location",
    )
    def _compute_show_barcode_validation(self) -> None:
        for picking_type in self:
            hide_full = picking_type.restrict_scan_product
            hide_all_product_packed = (
                not self.env.user.has_group("stock.group_tracking_lot")
                or picking_type.restrict_put_in_pack != "optional"
            )
            hide_dest_location = not self.env.user.has_group(
                "stock.group_stock_multi_locations"
            ) or (
                picking_type.code == "outgoing"
                or picking_type.restrict_scan_dest_location != "optional"
            )
            picking_type.show_barcode_validation = not (
                hide_full and hide_all_product_packed and hide_dest_location
            )

    @api.depends("code")
    def _compute_is_barcode_picking_type(self) -> None:
        _debug.perf.count("barcode_picking_type_compute", picking_types=self)
        for picking_type in self:
            picking_type.is_barcode_picking_type = picking_type.code in (
                "incoming",
                "outgoing",
                "internal",
            )

    @api.constrains("restrict_scan_source_location", "restrict_scan_dest_location")
    def _check_restrict_scan_locations(self) -> None:
        _debug.logic("barcode_scan_locations_check", picking_types=self)
        for picking_type in self:
            if (
                picking_type.code == "internal"
                and picking_type.restrict_scan_dest_location == "optional"
                and picking_type.restrict_scan_source_location == "mandatory"
            ):
                raise UserError(
                    self.env._(
                        "If the source location must be scanned, then the destination location must either be scanned after each product or not scanned at all."
                    )
                )

    def action_view_pickings_ready_kanban(self):
        return self._prepare_action_by_xml_id(
            "stock_barcode.stock_picking_action_kanban"
        )

    def _get_barcode_config(self):
        _debug.logic("barcode_config_read", picking_types=self)
        self.check_singleton()
        locations_enable = self.env.user.has_group("stock.group_stock_multi_locations")
        lines_need_to_be_packed = self.env.user.has_group(
            "stock.group_tracking_lot"
        ) and (
            self.restrict_put_in_pack == "mandatory"
            or (
                self.restrict_put_in_pack == "optional"
                and self.barcode_validation_all_product_packed
            )
        )
        lines_need_destination_location = locations_enable and (
            self.restrict_scan_dest_location == "mandatory"
            or (
                self.restrict_scan_dest_location == "optional"
                and self.barcode_validation_after_dest_location
            )
        )
        return {
            "barcode_allow_extra_product": self.barcode_allow_extra_product,
            "barcode_validation_after_dest_location": self.barcode_validation_after_dest_location,
            "barcode_validation_all_product_packed": self.barcode_validation_all_product_packed,
            "barcode_validation_full": not self.restrict_scan_product
            and self.barcode_validation_full,
            "create_backorder": self.create_backorder,
            "restrict_scan_product": self.restrict_scan_product,
            "restrict_scan_tracking_number": self.restrict_scan_tracking_number
            == "mandatory",
            "restrict_scan_source_location": locations_enable
            and self.restrict_scan_source_location == "mandatory",
            "restrict_put_in_pack": self.restrict_put_in_pack,
            "restrict_scan_dest_location": self.restrict_scan_dest_location
            if locations_enable
            else "no",
            "lines_need_to_be_packed": lines_need_to_be_packed,
            "lines_need_destination_location": lines_need_destination_location,
        }

    def _get_fields_stock_barcode(self):
        return [
            "default_location_dest_id",
            "default_location_src_id",
            "use_create_lots",
            "use_existing_lots",
            "show_reserved_sns",
        ]
