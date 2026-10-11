import logging
from datetime import timedelta
from xml.etree import ElementTree as ET

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_amazon import const
from odoo.addons.sale_amazon import utils as amazon_utils

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    amazon_sync_status = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        string="Amazon Synchronization Status",
        readonly=True,
        help="The synchronization status of the delivery order to Amazon:\n"
        "- Pending: The delivery order has been confirmed and will soon be synchronized.\n"
        "- Processing: The delivery details have been sent and are being processed.\n"
        "- Done: The delivery details have been processed.\n"
        "- Error: The synchronization of the delivery order failed.",
    )
    amazon_feed_ref = fields.Char(
        string="Amazon Feed Reference",
        readonly=True,
    )


    def write(self, vals):
        pickings = self
        if "date_done" in vals:
            amazon_pickings = self.sudo().filtered(
                lambda p: p.sale_id and p.sale_id.amazon_order_ref
            )
            amazon_pickings._check_sales_order_line_completion()
            pickings_requiring_amazon_sync = amazon_pickings.filtered(
                lambda p: (
                    p.location_dest_id.usage == "customer"
                    and p.amazon_sync_status != "done"
                )
            )
            _debug.logic(
                "picking_sync_flagged",
                candidates=amazon_pickings,
                flagged=pickings_requiring_amazon_sync,
                skipped=amazon_pickings - pickings_requiring_amazon_sync,
            )
            if _debug.logic.enabled and (
                skipped := amazon_pickings - pickings_requiring_amazon_sync
            ):
                _debug.logic(
                    "picking_sync_skipped",
                    pickings=skipped,
                    usages=",".join(
                        sorted(set(skipped.location_dest_id.mapped("usage")))
                    ),
                    statuses=",".join(
                        sorted({p.amazon_sync_status or "unset" for p in skipped})
                    ),
                )
            super(StockPicking, pickings_requiring_amazon_sync).write(
                dict(amazon_sync_status="pending", **vals)
            )
            pickings -= pickings_requiring_amazon_sync
        return super(StockPicking, pickings).write(vals)

    def _check_sales_order_line_completion(self) -> None:
        for picking in self:
            sales_order_lines_completion = {}
            for move in picking.move_ids.filtered("sale_line_id.amazon_item_ref"):
                completion = sales_order_lines_completion.setdefault(
                    move.sale_line_id, [0, 0]
                )
                completion[0] += move.product_uom_qty
                completion[1] += move.quantity

            for sales_order_line, completion in sales_order_lines_completion.items():
                demand_qty, done_qty = completion
                completion_ratio = done_qty / demand_qty if demand_qty else 0
                _debug.logic(
                    "sale_line_completion",
                    picking=picking,
                    line=sales_order_line,
                    demand=demand_qty,
                    done=done_qty,
                    ratio=completion_ratio,
                    partial=0 < completion_ratio < 1,
                )
                if (
                    0 < completion_ratio < 1
                ):
                    raise UserError(
                        self.env._(
                            "Products delivered to Amazon customers must have their respective parts in"
                            " the same package. Operations related to the product %s were not all "
                            "confirmed at once.",
                            sales_order_line.product_id.display_name,
                        )
                    )

    def _check_carrier_details_compliance(self):
        amazon_pickings_sudo = self.sudo().filtered(
            lambda p: (
                p.sale_id
                and p.sale_id.amazon_order_ref
                and p.location_dest_id.usage == "customer"
                and p.amazon_sync_status != "done"
            )
        )
        _debug.logic(
            "carrier_compliance_checked",
            pickings=self,
            amazon=amazon_pickings_sudo,
        )
        for picking_sudo in amazon_pickings_sudo:
            if not picking_sudo.carrier_id.name:
                _debug.logic(
                    "carrier_compliance_refused",
                    picking=picking_sudo,
                    reason="no_carrier",
                )
                raise UserError(
                    self.env._(
                        "Amazon requires that a tracking reference is provided with each delivery. You "
                        "need to assign a carrier to this delivery."
                    )
                )
            if not picking_sudo.carrier_tracking_ref:
                _debug.logic(
                    "carrier_compliance_refused",
                    picking=picking_sudo,
                    reason="no_tracking_ref",
                )
                raise UserError(
                    self.env._(
                        "Amazon requires that a tracking reference is provided with each delivery. "
                        "Since the current carrier doesn't automatically provide a tracking reference, "
                        "you need to set one manually."
                    )
                )
        return super()._check_carrier_details_compliance()


    def action_retry_amazon_sync(self) -> None:
        self.check_singleton()

        offer = self.sale_id.line_ids[0].amazon_offer_id
        account = offer and offer.account_id
        if not account:
            raise UserError(
                self.env._(
                    "The sales order of this delivery order is not linked to an Amazon account."
                )
            )

        _debug.lifecycle("picking_sync_retry", picking=self, account=account)
        account._sync_order_by_reference(self.sale_id.amazon_order_ref)
        if (
            self.amazon_sync_status == "error"
        ):
            _debug.logic("picking_sync_retry_needed", picking=self, status="error")
            self._confirm_shipment(account)
            self.env["ir.cron"]._trigger_ref(
                "sale_amazon.ir_cron_sync_amazon_feeds"
            )


    @api.model
    def _sync_pickings(self, account_ids=()) -> None:
        pickings_by_account = self._get_pickings_by_account("pending", account_ids)
        _debug.pipeline(
            "pickings_sync_started",
            accounts=len(pickings_by_account),
            pickings=sum(len(p) for p in pickings_by_account.values()),
            restricted_to=len(account_ids),
        )

        for account, pickings in pickings_by_account.items():
            amazon_utils.check_account_is_set_up(account)
            with _debug.perf("picking_confirm_batch", account=account) as span:
                span.set(pickings=len(pickings))
                pickings._confirm_shipment(account)

        next_call = fields.Datetime.now() + timedelta(minutes=10)
        self.env["ir.cron"]._trigger_ref(
            "sale_amazon.ir_cron_sync_amazon_feeds", at=next_call
        )

    def _get_pickings_by_account(self, sync_status, account_ids):
        pickings_by_account = {}

        for picking in self.search([("amazon_sync_status", "=", sync_status)]):
            if picking.sale_id.line_ids:
                offer = picking.sale_id.line_ids[0].amazon_offer_id
                account = (
                    offer and offer.account_id
                )
                if not account or (account_ids and account.id not in account_ids):
                    _debug.logic(
                        "picking_excluded",
                        picking=picking,
                        reason="no_account" if not account else "account_filtered",
                    )
                    continue
                pickings_by_account.setdefault(account, self.env["stock.picking"])
                pickings_by_account[account] += picking

        return pickings_by_account

    def _confirm_shipment(self, account) -> None:

        def add_feed_messages(root_):
            for picking_ in self:
                message_ = ET.SubElement(root_, "Message")
                order_fulfillment_ = ET.SubElement(message_, "OrderFulfillment")
                amazon_order_ref_ = picking_.sale_id.amazon_order_ref
                ET.SubElement(
                    order_fulfillment_, "AmazonOrderID"
                ).text = amazon_order_ref_
                shipping_date_ = fields.Datetime.now().isoformat()
                ET.SubElement(
                    order_fulfillment_, "FulfillmentDate"
                ).text = shipping_date_

                fulfillment_data_ = ET.SubElement(order_fulfillment_, "FulfillmentData")
                carrier_code_ = picking_.with_context(
                    amazon_carrier_name_fallback="Other"
                )._get_formatted_carrier_name()
                ET.SubElement(fulfillment_data_, "CarrierCode").text = carrier_code_
                ET.SubElement(
                    fulfillment_data_, "CarrierName"
                ).text = picking_._get_formatted_carrier_name()
                ET.SubElement(
                    fulfillment_data_, "ShippingMethod"
                ).text = picking_.carrier_id.name
                ET.SubElement(
                    fulfillment_data_, "ShipperTrackingNumber"
                ).text = picking_.carrier_tracking_ref

                confirmed_order_lines_ = picking_._get_confirmed_order_lines()
                items_data_ = confirmed_order_lines_.mapped(
                    lambda l_: (l_.amazon_item_ref, l_.product_qty)
                )
                for amazon_item_ref_, item_quantity_ in items_data_:
                    item_ = ET.SubElement(order_fulfillment_, "Item")
                    ET.SubElement(item_, "AmazonOrderItemCode").text = amazon_item_ref_
                    ET.SubElement(item_, "Quantity").text = str(int(item_quantity_))

                location_ = (
                    account.location_id.warehouse_id.partner_id or self.env.company
                )
                if not (location_.street and location_.country_id.code):
                    _debug.logic(
                        "shipment_refused",
                        picking=picking_,
                        reason="incomplete_ship_from",
                        location=location_,
                    )
                    raise UserError(
                        self.env._(
                            (
                                "Amazon require certain information for the shipping location. Please make"
                                " sure the following information are set on '%(location_name)s' (%(location)s): street, country and"
                                " country code."
                            ),
                            location_name=location_.display_name,
                            location=location_,
                        )
                    )
                ship_from_ = ET.SubElement(order_fulfillment_, "ShipFromAddress")
                ET.SubElement(ship_from_, "Name").text = location_.name[:30]
                ET.SubElement(ship_from_, "AddressFieldOne").text = location_.street[
                    :180
                ]
                ET.SubElement(
                    ship_from_, "CountryCode"
                ).text = location_.country_id.code

        _debug.pipeline("shipment_feed_built", account=account, pickings=self)
        xml_feed = amazon_utils.get_feed(account, "OrderFulfillment", add_feed_messages)
        try:
            with _debug.perf("shipment_feed_submit", account=account) as span:
                feed_ref = amazon_utils.submit_feed(
                    account, xml_feed, "POST_ORDER_FULFILLMENT_DATA"
                )
                span.set(feed_ref=feed_ref)
        except amazon_utils.AmazonRateLimitError:
            _debug.logic("shipment_feed_refused", account=account, reason="rate_limit")
            _logger.info(
                "Rate limit reached while sending picking confirmation notification for Amazon "
                "account with id %s.",
                self.id,
            )
        else:
            _logger.info(
                "Sent delivery confirmation notification (feed_ref %s) to amazon for pickings with "
                "amazon_order_ref %s.",
                feed_ref,
                ", ".join(picking.sale_id.amazon_order_ref for picking in self),
            )
            _debug.lifecycle(
                "shipment_confirmed",
                pickings=self,
                account=account,
                feed_ref=feed_ref,
                status="processing",
            )
            self.write(
                {"amazon_sync_status": "processing", "amazon_feed_ref": feed_ref}
            )

    def _get_formatted_carrier_name(self):
        self.check_singleton()

        shipper_name = None
        if self.carrier_id:
            carrier_key = (
                self.carrier_id._get_delivery_type()
            )
            if carrier_key in (
                "fixed",
                "base_on_rule",
            ):
                carrier_key = self.carrier_id.name
            carrier_key = "".join(
                filter(str.isalnum, carrier_key)
            ).lower()
            fallback = self.env.context.get(
                "amazon_carrier_name_fallback", self.carrier_id.name
            )
            shipper_name = const.AMAZON_CARRIER_NAMES_MAPPING.get(carrier_key, fallback)
            _debug.logic(
                "carrier_name_resolved",
                picking=self,
                key=carrier_key,
                name=shipper_name,
                mapped=carrier_key in const.AMAZON_CARRIER_NAMES_MAPPING,
            )
        return shipper_name

    def _get_confirmed_order_lines(self):
        self.check_singleton()

        _debug.logic(
            "confirmed_lines_requested", picking=self, moves=len(self.move_ids)
        )
        return self.move_ids.filtered(
            lambda m: (
                m.sale_line_id.amazon_item_ref
                and m.quantity > 0
                and m.quantity == m.product_uom_qty
            )
        ).sale_line_id
