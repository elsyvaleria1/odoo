import logging
from urllib.parse import urlencode

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

from .envia_request import Envia

_logger = logging.getLogger(__name__)

ENVIA_STOCK_TYPE = [
    ("PAPER_4X6", "PAPER_4X6"),
    ("PAPER_4X8", "PAPER_4X8"),
    ("PAPER_7X4.75", "PAPER_7X4.75"),
    ("PAPER_8.27X11.67", "PAPER_8.27X11.67"),
    ("PAPER_8.5X11_BOTTOM_HALF_LABEL", "PAPER_8.5X11_BOTTOM_HALF_LABEL"),
    ("PAPER_8.5X11", "PAPER_8.5X11"),
    ("STOCK_2.4X6", "STOCK_2.4X6"),
    ("STOCK_2.9X5", "STOCK_2.9X5"),
    ("STOCK_3.8X4.2", "STOCK_3.8X4.2"),
    ("STOCK_3.9X7", "STOCK_3.9X7"),
    ("STOCK_4X4", "STOCK_4X4"),
    ("STOCK_4X6", "STOCK_4X6"),
    ("STOCK_4X6.5", "STOCK_4X6.5"),
    ("STOCK_4X6.75_LEADING_DOC_TAB", "STOCK_4X6.75_LEADING_DOC_TAB"),
    ("STOCK_4X7.5", "STOCK_4X7.5"),
    ("STOCK_4X8", "STOCK_4X8"),
]


_debug = DebugLog(__name__)


class DeliverCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("envia", "Envia")],
        ondelete={
            "envia": lambda recs: recs.write(
                {"delivery_type": "fixed", "fixed_price": 0}
            )
        },
    )

    _CREDENTIAL_FIELDS = {
        "envia_production_api_key": "envia_production_api_key",
        "envia_sandbox_api_key": "envia_sandbox_api_key",
    }

    envia_production_api_key = fields.Text(
        string="Envia Production Access Token",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=False,
        classification="secret.credential",
        groups="base.group_system",
        help="Generate an Access Token from within the Production Portal of Envia",
    )

    envia_sandbox_api_key = fields.Text(
        string="Envia Sandbox Access Token",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=False,
        classification="secret.credential",
        groups="base.group_system",
        help="Generate an Access Token from within the Sandbox Portal of Envia",
    )

    envia_default_package_type_id = fields.Many2one(
        comodel_name="stock.package.type",
        string="Envia Default Package",
        domain="[('package_carrier_type', '=', 'envia')]",
        help="Envia requires package dimensions for getting accurate rate, "
        "you can define these in a package type that you set as default",
    )

    envia_mail_type = fields.Selection(
        related="envia_default_package_type_id.envia_mail_type"
    )

    envia_carrier_code = fields.Char(
        string="Envia.com Carrier Code",
        compute="_compute_services",
        store=True,
        help="The carrier on Envia.com used by this carrier. The service code belongs to it.",
    )

    envia_service_code = fields.Char(
        string="Envia.com Service Code",
        compute="_compute_services",
        store=True,
        help="The service that will be used for this carrier. This is set when you select a carrier from the wizard.",
    )

    envia_service_name = fields.Char(
        string="Envia.com Service Name",
        compute="_compute_services",
        store=True,
        help="The service that will be used for this carrier. This is set when you select a carrier from the wizard.",
    )

    envia_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Envia Account Main Currency",
        default=lambda self: self.env.company.currency_id,
        copy=False,
        help="Currency set in Envia",
    )

    envia_label_stock_type = fields.Selection(
        selection=ENVIA_STOCK_TYPE,
        string="Envia Label Type",
        default="PAPER_8.5X11",
        help="Select the size of the label",
    )

    envia_label_file_type = fields.Selection(
        selection=[
            ("PNG", "PNG"),
            ("ZPLII", "ZPLII"),
            ("EPL", "EPL"),
            ("PDF", "PDF"),
            ("ZPL", "ZPL"),
        ],
        default="PDF",
        help="Select the printing format of the label",
    )

    country_id = fields.Many2one(
        comodel_name="res.country",
        string="Ship From",
        default=lambda self: self.env.company.country_id,
        help="Select the country to be used by this delivery method",
    )

    envia_return_at_senders_expense = fields.Boolean(
        string="Returned at Shippers Expense",
        default=False,
        help="If the carrier is unable to deliver the package, the package can be returned to the shipper or abandoned at the door. (Canada only)",
    )

    envia_lift_pickup = fields.Boolean(
        string="Lift Assistance on Pickup",
        default=False,
        help="Provide liftgate assitance if the supplier doesn't have a dock or forklift to load the shipment. (United States and Mexico Only)",
    )

    envia_lift_delivery = fields.Boolean(
        string="Lift Assistance on Delivery",
        default=False,
        help="Provide liftgate assistance if the recipient doesn't have a dock or forklift to unload the shipment. (United States and Mexico Only)",
    )

    envia_residential_delivery = fields.Boolean(
        string="Delivery Residential Zone",
        default=False,
        help="Certain carriers like UPS will charge an extra fee to deliver to a residential zone (United States Only)",
    )

    envia_residential_pickup = fields.Boolean(
        string="Pickup Residential Zone",
        default=False,
        help="Certain carriers like UPS will charge an extra fee to pickup from residential zones (United States Only)",
    )

    @api.depends(
        "country_id",
        "envia_default_package_type_id.envia_mail_type",
        "prod_environment",
    )
    def _compute_services(self):
        for carrier in self:
            if carrier.delivery_type == "envia":
                carrier.envia_carrier_code = ""
                carrier.envia_service_code = ""
                carrier.envia_service_name = ""

    def _compute_supports_shipping_insurance(self):
        super()._compute_supports_shipping_insurance()
        for carrier in self:
            if carrier.delivery_type == "envia":
                carrier.supports_shipping_insurance = True

    def _envia_convert_size(self, size):
        self.check_singleton()
        size_uom_id = self.env["product.template"]._get_uom_from_setting("length")
        return size_uom_id._get_quantity_in_unit(
            size, self.env.ref("base.product_uom_cm"), round=False
        )

    def action_view_envia_wizard(self) -> dict:
        self.check_singleton()
        if self.delivery_type != "envia":
            raise ValidationError(
                self.env._("This action requires an Envia.com carrier.")
            )

        envia = Envia(self, self.prod_environment, self.log_xml)
        carriers_data = envia._get_envia_carriers()

        if errors_found := carriers_data.get("error"):
            raise ValidationError(errors_found)
        carriers_list = carriers_data.get("carriers")
        if not carriers_list:
            raise ValidationError(
                self.env._("Failed to fetch Envia Carriers, Please try again later.")
            )

        return {
            "name": self.env._("Choose an Envia.com Shipping Service"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.delivery.carrier.update.envia.service",
            "target": "new",
            "context": {
                "default_carrier_id": self.id,
                "default_available_services": carriers_list,
                "default_selected_service_code": self.envia_service_code,
                "default_selected_carrier_code": self.envia_carrier_code,
            },
        }

    def envia_rate_shipment(self, order) -> dict:
        _debug.pipeline(
            "carrier_rate_request", provider="envia", carrier=self.id, order=order.id
        )
        if not self.envia_carrier_code or not self.envia_service_code:
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._(
                    'No carrier is set on "%(delivery_method)s". To use Envia.com, you\'ll need to sync your carriers with your account.',
                    delivery_method=self.name,
                ),
                "warning_message": False,
            }

        order_weight = self.env.context.get("order_weight", None)
        envia = Envia(self, self.prod_environment, self.log_xml)
        result = envia._rate_request(
            order.partner_shipping_id,
            order.warehouse_id.partner_id or order.warehouse_id.company_id.partner_id,
            order,
            order_weight=order_weight,
        )

        if result.get("error_found"):
            return {
                "success": False,
                "price": 0.0,
                "error_message": result["error_found"],
                "warning_message": False,
            }

        price = float(result["price"])
        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": result.get("warning_message"),
        }

    def envia_send_shipping(self, pickings):
        _debug.pipeline(
            "carrier_ship_request", provider="envia", carrier=self.id, pickings=pickings
        )
        if not self.envia_carrier_code or not self.envia_service_code:
            raise UserError(
                self.env._(
                    'No carrier is set on "%(delivery_method)s". To use Envia.com, you\'ll need to sync your carriers with your account.',
                    delivery_method=self.name,
                )
            )
        res = []
        envia = Envia(self, self.prod_environment, self.log_xml)
        for pick in pickings:
            shipment = envia._send_shipping(pick)

            res.append(
                {
                    "tracking_number": shipment.get("tracking_number"),
                    "exact_price": shipment.get("exact_price"),
                }
            )
        return res

    def envia_get_tracking_link(self, picking):
        _debug.logic(
            "carrier_tracking_link",
            provider="envia",
            carrier=self.id,
            picking=picking.id,
        )
        if self.prod_environment:
            root_url = "https://envia.com"
        else:
            root_url = "https://dev.envia.com"

        params = {"label": picking.carrier_tracking_ref}
        return f"{root_url}/tracking?{urlencode(params)}"

    def envia_cancel_shipment(self, pickings):
        _debug.lifecycle(
            "carrier_cancel_request",
            provider="envia",
            carrier=self.id,
            pickings=pickings,
        )
        envia = Envia(self, self.prod_environment, self.log_xml)
        for pick in pickings:
            if (
                pick.carrier_id.delivery_type != "envia"
                or not pick.carrier_tracking_ref
            ):
                pick.message_post(
                    body=pick.env._("Envia order(s) not found to cancel shipment!")
                )
                continue

            invalid_trackings = envia._cancel_picking(pick)
            if invalid_trackings:
                pick.message_post(
                    body=pick.env._(
                        "Unable to cancel order: %(order_number)s",
                        order_number=invalid_trackings,
                    )
                )
            else:
                pick.write(
                    {
                        "carrier_tracking_ref": "",
                        "carrier_price": 0.00,
                    }
                )
