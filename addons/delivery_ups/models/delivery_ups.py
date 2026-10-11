from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import pdf

from .ups_request import UPSRequest

_debug = DebugLog(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    def _get_ups_service_types(self) -> list:
        return [
            ("03", "UPS Ground"),
            ("11", "UPS Standard"),
            ("01", "UPS Next Day"),
            ("14", "UPS Next Day AM"),
            ("13", "UPS Next Day Air Saver"),
            ("02", "UPS 2nd Day"),
            ("59", "UPS 2nd Day AM"),
            ("12", "UPS 3-day Select"),
            ("65", "UPS Saver"),
            ("07", "UPS Worldwide Express"),
            ("08", "UPS Worldwide Expedited"),
            ("54", "UPS Worldwide Express Plus"),
            ("96", "UPS Worldwide Express Freight"),
        ]

    delivery_type = fields.Selection(
        selection_add=[("ups", "UPS Legacy")],
        ondelete={
            "ups": lambda recs: recs.write({"delivery_type": "fixed", "fixed_price": 0})
        },
    )

    ups_username = fields.Char(
        string="UPS Username",
        groups="base.group_system",
    )
    ups_passwd = fields.Char(
        string="UPS Password",
        classification="secret.credential",
        groups="base.group_system",
    )
    ups_shipper_number = fields.Char(
        string="UPS Shipper Number",
        groups="base.group_system",
    )
    ups_access_number = fields.Char(
        string="UPS Access Key",
        groups="base.group_system",
    )
    ups_default_package_type_id = fields.Many2one(
        comodel_name="stock.package.type",
        string="UPS Legacy Package Type",
    )
    ups_default_service_type = fields.Selection(
        selection=_get_ups_service_types,
        string="UPS Service Type",
        default="03",
    )
    ups_duty_payment = fields.Selection(
        selection=[("SENDER", "Sender"), ("RECIPIENT", "Recipient")],
        default="RECIPIENT",
        required=True,
    )
    ups_package_weight_unit = fields.Selection(
        selection=[("LBS", "Pounds"), ("KGS", "Kilograms")],
        default="LBS",
    )
    ups_package_dimension_unit = fields.Selection(
        selection=[("IN", "Inches"), ("CM", "Centimeters")],
        string="Package Size Unit",
        default="IN",
    )
    ups_label_file_type = fields.Selection(
        selection=[("GIF", "PDF"), ("ZPL", "ZPL"), ("EPL", "EPL"), ("SPL", "SPL")],
        string="UPS Label File Type",
        default="GIF",
    )
    ups_bill_my_account = fields.Boolean(
        string="Bill My Account",
        help="If checked, ecommerce users will be prompted their UPS account number\n"
        "and delivery fees will be charged on it.",
    )
    ups_saturday_delivery = fields.Boolean(
        string="UPS Saturday Delivery",
        help="This value added service will allow you to ship the package on saturday also.",
    )
    ups_cod_funds_code = fields.Selection(
        selection=[
            ("0", "Check, Cashier's Check or MoneyOrder"),
            ("8", "Cashier's Check or MoneyOrder"),
        ],
        string="COD Funding Option",
        default="0",
    )

    def _compute_can_generate_return(self) -> None:
        super()._compute_can_generate_return()
        for carrier in self:
            if carrier.delivery_type == "ups":
                carrier.can_generate_return = True

    def _compute_supports_shipping_insurance(self):
        super()._compute_supports_shipping_insurance()
        for carrier in self:
            if carrier.delivery_type == "ups":
                carrier.supports_shipping_insurance = True

    @api.onchange("ups_default_service_type")
    def on_change_service_type(self) -> None:
        self.allow_cash_on_delivery = False
        self.ups_saturday_delivery = False

    def ups_rate_shipment(self, order) -> dict:
        _debug.pipeline(
            "carrier_rate_request", provider="ups", carrier=self.id, order=order.id
        )
        superself = self.sudo()
        srm = UPSRequest(
            self.log_xml,
            superself.ups_username,
            superself.ups_passwd,
            superself.ups_shipper_number,
            superself.ups_access_number,
            self.prod_environment,
        )
        ResCurrency = self.env["res.currency"]

        packages = self._get_packages_from_order(
            order, self.ups_default_package_type_id
        )

        shipment_info = {
            "total_qty": sum(
                line.product_uom_qty
                for line in order.line_ids.filtered(
                    lambda line: not line.is_delivery and not line.display_type
                )
            )  # required when service type = 'UPS Worldwide Express Freight'
        }

        if self.allow_cash_on_delivery:
            cod_info = {
                "currency": order.partner_id.country_id.currency_id.name,
                "monetary_value": order.amount_total,
                "funds_code": self.ups_cod_funds_code,
            }
        else:
            cod_info = None

        check_value = srm.check_required_value(
            order.company_id.partner_id,
            order.warehouse_id.partner_id,
            order.partner_shipping_id,
            order=order,
        )
        if check_value:
            return {
                "success": False,
                "price": 0.0,
                "error_message": check_value,
                "warning_message": False,
            }

        ups_service_type = self.ups_default_service_type
        result = srm.get_shipping_price(
            carrier=self,
            shipment_info=shipment_info,
            packages=packages,
            shipper=order.company_id.partner_id,
            ship_from=order.warehouse_id.partner_id,
            ship_to=order.partner_shipping_id,
            service_type=ups_service_type,
            saturday_delivery=self.ups_saturday_delivery,
            cod_info=cod_info,
        )

        if result.get("error_message"):
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._("Error:\n%s", result["error_message"]),
                "warning_message": False,
            }

        if order.currency_id.name == result["currency_code"]:
            price = float(result["price"])
        else:
            quote_currency = ResCurrency.search(
                [("name", "=", result["currency_code"])], limit=1
            )
            price = quote_currency._convert(
                float(result["price"]),
                order.currency_id,
                order.company_id,
                order.date_order or fields.Date.today(),
            )

        if self.ups_bill_my_account and order.partner_ups_carrier_account:
            # Don't show delivery amount, if ups bill my account option is true
            price = 0.0

        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

    def ups_send_shipping(self, pickings):
        _debug.pipeline(
            "carrier_ship_request", provider="ups", carrier=self.id, pickings=pickings
        )
        res = []
        superself = self.sudo()
        srm = UPSRequest(
            self.log_xml,
            superself.ups_username,
            superself.ups_passwd,
            superself.ups_shipper_number,
            superself.ups_access_number,
            self.prod_environment,
        )
        ResCurrency = self.env["res.currency"]
        for picking in pickings:
            packages = self._get_packages_from_picking(
                picking, self.ups_default_package_type_id
            )

            terms_of_shipment = picking.company_id.account_config_id.incoterm_id
            if picking.sale_id and picking.sale_id.incoterm_id:
                terms_of_shipment = picking.sale_id.incoterm_id

            shipment_info = {
                "require_invoice": picking._is_commercial_invoice_required(),
                "invoice_date": fields.Date.today().strftime("%Y%m%d"),
                "description": picking.origin or picking.name,
                "total_qty": sum(sml.quantity for sml in picking.move_line_ids),
                "ilt_monetary_value": "%d"
                % sum(sml.sale_price for sml in picking.move_line_ids),
                "itl_currency_code": self.env.company.currency_id.name,
                "phone": picking.partner_id.phone_ids._primary().number
                or picking.sale_id.partner_id.phone_ids._primary().number,
                "terms_of_shipment": terms_of_shipment.code
                if terms_of_shipment
                else None,
                "purchase_order_number": picking.sale_id.name
                if picking.sale_id
                else None,
            }
            if picking.sale_id and picking.sale_id.carrier_id != picking.carrier_id:
                ups_service_type = (
                    picking.carrier_id.ups_default_service_type
                    or self.ups_default_service_type
                )
            else:
                ups_service_type = self.ups_default_service_type
            ups_carrier_account = False
            if self.ups_bill_my_account:
                ups_carrier_account = picking.partner_id.with_company(
                    picking.company_id
                ).property_ups_carrier_account

            if picking.carrier_id.allow_cash_on_delivery:
                cod_info = {
                    "currency": picking.partner_id.country_id.currency_id.name,
                    "monetary_value": picking.sale_id.amount_total,
                    "funds_code": self.ups_cod_funds_code,
                }
            else:
                cod_info = None

            check_value = srm.check_required_value(
                picking.company_id.partner_id,
                picking.picking_type_id.warehouse_id.partner_id,
                picking.partner_id,
                picking=picking,
            )
            if check_value:
                raise UserError(check_value)

            srm.send_shipping(
                carrier=picking.carrier_id,
                shipment_info=shipment_info,
                packages=packages,
                shipper=picking.company_id.partner_id,
                ship_from=picking.picking_type_id.warehouse_id.partner_id,
                ship_to=picking.partner_id,
                service_type=ups_service_type,
                duty_payment=picking.carrier_id.ups_duty_payment,
                label_file_type=self.ups_label_file_type,
                ups_carrier_account=ups_carrier_account,
                saturday_delivery=picking.carrier_id.ups_saturday_delivery,
                cod_info=cod_info,
            )
            result = srm.process_shipment()
            if result.get("error_message"):
                raise UserError(result["error_message"].__str__())

            order = picking.sale_id
            company = order.company_id or picking.company_id or self.env.company
            currency_order = picking.sale_id.currency_id
            if not currency_order:
                currency_order = picking.company_id.currency_id

            if currency_order.name == result["currency_code"]:
                price = float(result["price"])
            else:
                quote_currency = ResCurrency.search(
                    [("name", "=", result["currency_code"])], limit=1
                )
                price = quote_currency._convert(
                    float(result["price"]),
                    currency_order,
                    company,
                    order.date_order or fields.Date.today(),
                )

            package_labels = []
            for track_number, label_binary_data in result.get(
                "label_binary_data"
            ).items():
                package_labels.append((track_number, label_binary_data))

            carrier_tracking_ref = "+".join([pl[0] for pl in package_labels])
            logmessage = (
                self.env._("Shipment created into UPS")
                + Markup("<br/><b>")
                + self.env._("Tracking Numbers:")
                + Markup("</b> ")
                + carrier_tracking_ref
                + Markup("<br/><b>")
                + self.env._("Packages:")
                + Markup("</b> ")
                + ",".join([p.name for p in packages if p.name])
            )
            if self.ups_label_file_type != "GIF":
                attachments = [
                    (
                        "%s-%s.%s"
                        % (
                            self._get_delivery_label_prefix(),
                            pl[0],
                            self.ups_label_file_type,
                        ),
                        pl[1],
                    )
                    for pl in package_labels
                ]
            if self.ups_label_file_type == "GIF":
                attachments = [
                    (
                        "%s.pdf" % (self._get_delivery_label_prefix()),
                        pdf.merge_pdf([pl[1] for pl in package_labels]),
                    )
                ]
            if "invoice_binary_data" in result:
                attachments.append(
                    (
                        "%s-CommercialInvoice.pdf" % (self._get_delivery_doc_prefix()),
                        result["invoice_binary_data"],
                    )
                )
            if picking.sale_id:
                for pick in picking.sale_id.picking_ids:
                    pick.message_post(body=logmessage, attachments=attachments)
            else:
                picking.message_post(body=logmessage, attachments=attachments)
            shipping_data = {
                "exact_price": price,
                "tracking_number": carrier_tracking_ref,
            }
            res.append(shipping_data)
            if self.return_label_on_delivery:
                self.ups_get_return_label(picking)
        return res

    def ups_get_return_label(self, picking, tracking_number=None, origin_date=None):
        res = []
        superself = self.sudo()
        srm = UPSRequest(
            self.log_xml,
            superself.ups_username,
            superself.ups_passwd,
            superself.ups_shipper_number,
            superself.ups_access_number,
            self.prod_environment,
        )
        ResCurrency = self.env["res.currency"]

        packages = self._get_packages_from_picking(
            picking, self.ups_default_package_type_id
        )

        invoice_line_total = 0
        for move in picking.move_ids:
            invoice_line_total += picking.company_id.currency_id.round(
                move.product_id.lst_price * move.product_qty
            )

        shipment_info = {
            "is_return": True,
            "invoice_date": fields.Date.today().strftime("%Y%m%d"),
            "description": picking.origin or picking.name,
            "total_qty": sum(sml.quantity for sml in picking.move_line_ids),
            "ilt_monetary_value": "%d" % invoice_line_total,
            "itl_currency_code": self.env.company.currency_id.name,
            "phone": picking.partner_id.phone_ids._primary().number
            or picking.sale_id.partner_id.phone_ids._primary().number,
        }
        if picking.sale_id and picking.sale_id.carrier_id != picking.carrier_id:
            ups_service_type = (
                picking.carrier_id.ups_default_service_type
                or self.ups_default_service_type
            )
        else:
            ups_service_type = self.ups_default_service_type
        ups_carrier_account = False
        if self.ups_bill_my_account:
            ups_carrier_account = picking.partner_id.with_company(
                picking.company_id
            ).property_ups_carrier_account

        if picking.carrier_id.allow_cash_on_delivery:
            cod_info = {
                "currency": picking.partner_id.country_id.currency_id.name,
                "monetary_value": picking.sale_id.amount_total,
                "funds_code": self.ups_cod_funds_code,
            }
        else:
            cod_info = None

        check_value = srm.check_required_value(
            picking.partner_id,
            picking.partner_id,
            picking.picking_type_id.warehouse_id.partner_id,
        )
        if check_value:
            raise UserError(check_value)

        srm.send_shipping(
            carrier=picking.carrier_id,
            shipment_info=shipment_info,
            packages=packages,
            shipper=picking.company_id.partner_id,
            ship_from=picking.partner_id,
            ship_to=picking.picking_type_id.warehouse_id.partner_id,
            service_type=ups_service_type,
            duty_payment="RECIPIENT",
            label_file_type=self.ups_label_file_type,
            ups_carrier_account=ups_carrier_account,
            saturday_delivery=picking.carrier_id.ups_saturday_delivery,
            cod_info=cod_info,
        )
        srm.return_label()
        result = srm.process_shipment()
        if result.get("error_message"):
            raise UserError(result["error_message"].__str__())

        order = picking.sale_id
        company = order.company_id or picking.company_id or self.env.company
        currency_order = picking.sale_id.currency_id
        if not currency_order:
            currency_order = picking.company_id.currency_id

        if currency_order.name == result["currency_code"]:
            price = float(result["price"])
        else:
            quote_currency = ResCurrency.search(
                [("name", "=", result["currency_code"])], limit=1
            )
            price = quote_currency._convert(
                float(result["price"]),
                currency_order,
                company,
                order.date_order or fields.Date.today(),
            )

        package_labels = []
        for track_number, label_binary_data in result.get("label_binary_data").items():
            package_labels.append((track_number, label_binary_data))

        carrier_tracking_ref = "+".join([pl[0] for pl in package_labels])
        logmessage = (
            self.env._("Return label generated")
            + Markup("<br/><b>")
            + self.env._("Tracking Numbers:")
            + Markup("</b> ")
            + carrier_tracking_ref
            + Markup("<br/><b>")
            + self.env._("Packages:")
            + Markup("</b> ")
            + ",".join([p.name for p in packages if p.name])
        )
        if self.ups_label_file_type != "GIF":
            attachments = [
                (
                    "%s-%s-%s.%s"
                    % (
                        self.get_return_label_prefix(),
                        pl[0],
                        index,
                        self.ups_label_file_type,
                    ),
                    pl[1],
                )
                for index, pl in enumerate(package_labels)
            ]
        if self.ups_label_file_type == "GIF":
            attachments = [
                (
                    "%s-%s-%s.%s"
                    % (self.get_return_label_prefix(), package_labels[0][0], 1, "pdf"),
                    pdf.merge_pdf([pl[1] for pl in package_labels]),
                )
            ]
        picking.message_post(body=logmessage, attachments=attachments)
        shipping_data = {"exact_price": price, "tracking_number": carrier_tracking_ref}
        return res + [shipping_data]

    def ups_get_tracking_link(self, picking) -> str:
        _debug.logic(
            "carrier_tracking_link", provider="ups", carrier=self.id, picking=picking.id
        )
        return (
            "http://wwwapps.ups.com/WebTracking/track?track=yes&trackNums=%s"
            % picking.carrier_tracking_ref.replace("+", "%0D%0A")
        )

    def ups_cancel_shipment(self, picking) -> None:
        _debug.lifecycle(
            "carrier_cancel_request",
            provider="ups",
            carrier=self.id,
            picking=picking.id,
        )
        tracking_ref = picking.carrier_tracking_ref
        if not self.prod_environment:
            tracking_ref = "1ZISDE016691676846"  # used for testing purpose

        superself = self.sudo()
        srm = UPSRequest(
            self.log_xml,
            superself.ups_username,
            superself.ups_passwd,
            superself.ups_shipper_number,
            superself.ups_access_number,
            self.prod_environment,
        )
        result = srm.cancel_shipment(tracking_ref.partition("+")[0])

        if result.get("error_message"):
            raise UserError(result["error_message"].__str__())
        picking.message_post(
            body=self.env._(
                "Shipment #%s has been cancelled", picking.carrier_tracking_ref
            )
        )
        picking.write({"carrier_tracking_ref": "", "carrier_price": 0.0})

    def _ups_get_default_custom_package_code(self) -> str:
        return "02"

    def _ups_convert_weight(self, weight, unit="KGS"):
        weight_uom_id = self.env["product.template"]._get_uom_from_setting("weight")
        if unit == "KGS":
            return weight_uom_id._get_quantity_in_unit(
                weight, self.env.ref("base.product_uom_kgm"), round=False
            )
        elif unit == "LBS":
            return weight_uom_id._get_quantity_in_unit(
                weight, self.env.ref("base.product_uom_lb"), round=False
            )
        else:
            raise ValueError
