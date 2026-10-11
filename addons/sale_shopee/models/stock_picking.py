import logging
from datetime import timedelta

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_shopee import const, utils

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    shopee_order_ref = fields.Char(related="sale_id.shopee_order_ref")
    shopee_delivery_status = fields.Selection(related="sale_id.shopee_delivery_status")
    shopee_label_status = fields.Selection(
        selection=[
            ("not available", "Not Available"),
            ("processing", "Processing"),
            ("ready", "Ready"),
            ("stored", "Stored"),
            ("failed", "Failed"),
        ],
        string="Label Status",
        default="not available",
        readonly=True,
        help="The status of the shipping label:\n"
        "- Not Available: The shipping label is not available yet.\n"
        "- Processing: The shipping label is being processed.\n"
        "- Ready: The shipping label is ready to be downloaded.\n"
        "- Stored: The shipping label has been downloaded and stored.\n"
        "- Failed: The shipping label creation failed.",
    )
    last_picking_sync_date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        help="The last time the picking was synchronized with Shopee.",
    )


    def action_shopee_sync_pickings(self):
        return self._sync_shopee_pickings()


    def _sync_shopee_pickings(self, shop_ids=(), auto_commit=True) -> dict | None:
        pickings_by_shop = self._get_pickings_by_shop(shop_ids)
        _debug.pipeline(
            "pickings_sync_started",
            shops=len(pickings_by_shop),
            pickings=sum(len(p) for p in pickings_by_shop.values()),
        )

        for shop, shop_pickings in pickings_by_shop.items():
            try:
                shop._update_shop_information()
                if shop.status != "active":
                    _debug.logic("shop_skipped", shop=shop, status=shop.status)
                    continue
                shop_pickings._update_shipment_label(auto_commit)
            except utils.ShopeeRateLimitError as error:
                _debug.logic("sync_interrupted", shop=shop, op=error.operation)
                _logger.info(
                    "Rate limit reached while synchronizing pickings for Shopee account with"
                    " id %(account)d. Operation: %(error_operation)s",
                    {"account": shop.account_id.id, "error_operation": error.operation},
                )
                continue

        all_pickings = self.env["stock.picking"].concat(*pickings_by_shop.values())
        processing_pickings = all_pickings.filtered(
            lambda p: p.shopee_label_status == "processing"
        )
        _debug.logic("labels_still_processing", pickings=processing_pickings)
        if processing_pickings:
            self.env["ir.cron"]._trigger_ref(
                "sale_shopee.ir_cron_sync_shopee_pickings_retry",
                fields.Datetime.now() + timedelta(minutes=1),
            )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Shipping Label Not Ready"),
                    "message": self.env._(
                        "Shopee is processing the shipping label. Odoo will try fetching the"
                        " shipping label again later."
                    ),
                    "type": "warning",
                },
            }
        return None

    def _get_pickings_by_shop(self, shop_ids=()):
        pickings_by_shop = {}
        domain = [
            ("sale_id.shopee_shop_id", "!=", False),
            ("shopee_order_ref", "!=", False),
            ("shopee_delivery_status", "in", ["draft", "confirmed"]),
            ("shopee_label_status", "!=", "stored"),
            ("state", "not in", ["done", "cancel"]),
        ]
        if self:
            domain.append(["id", "in", self.ids])
        if shop_ids:
            domain.append(("sale_id.shopee_shop_id", "in", shop_ids))

        for picking in self.search(domain):
            shop = picking.sale_id.shopee_shop_id
            if not shop:
                _debug.logic("picking_excluded", picking=picking, reason="no_shop")
                continue
            pickings_by_shop.setdefault(shop, self.env["stock.picking"])
            pickings_by_shop[shop] += picking

        return pickings_by_shop

    def _update_shipment_label(self, auto_commit=True) -> None:
        shop = self[0].sale_id.shopee_shop_id
        shop.check_singleton()

        error_messages = []
        current_datetime = fields.Datetime.now()
        picking_sorted = self.filtered(
            lambda p: (
                p.state not in ["cancel", "done"]
                and p.shopee_label_status != "stored"
                and p.shopee_delivery_status in ["draft", "confirmed"]
            )
        ).sorted(lambda p: (p.last_picking_sync_date, p.id))

        batch_size = min(
            const.ORDER_DETAIL_SIZE_LIMIT, const.SHIPPING_DOCUMENT_SIZE_LIMIT
        )
        picking_batches = [
            picking_sorted[i : i + batch_size]
            for i in range(0, len(picking_sorted), batch_size)
        ]
        _debug.pipeline(
            "label_sync_batched",
            shop=shop,
            pickings=len(picking_sorted),
            batches=len(picking_batches),
        )
        for picking_batch in picking_batches:
            try:
                orders_detail = shop._get_orders_detail(
                    picking_batch.sale_id.mapped("shopee_order_ref")
                )
                orders_by_ref = picking_batch.sale_id.grouped("shopee_order_ref")
                for order_detail in orders_detail:
                    new_delivery_status = const.DELIVERY_STATUS_MAPPING.get(
                        order_detail["order_status"], "error"
                    )
                    order = orders_by_ref.get(
                        order_detail["order_sn"], picking_batch.sale_id.browse()
                    )
                    if order and order.shopee_delivery_status != new_delivery_status:
                        _debug.lifecycle(
                            "delivery_status_changed",
                            order=order,
                            was=order.shopee_delivery_status,
                            now=new_delivery_status,
                        )
                        order.shopee_delivery_status = new_delivery_status

                picking_batch = picking_batch.filtered(
                    lambda p: p.shopee_delivery_status in {"draft", "confirmed"}
                )

                picking_batch._set_tracking_number(shop)
                pickings = picking_batch.filtered(lambda p: p.carrier_tracking_ref)

                pickings_no_label_requested = pickings.filtered(
                    lambda p: p.shopee_label_status in ["not available", "failed"]
                )
                pickings_no_label_requested._update_shipping_label(shop)

                pickings_label_requested = pickings.filtered(
                    lambda p: p.shopee_label_status == "processing"
                )
                pickings_label_requested._update_shipping_label_status(shop)

                pickings_label_ready_to_print = pickings.filtered(
                    lambda p: p.shopee_label_status == "ready"
                )
                _debug.pipeline(
                    "label_stages",
                    batch=len(picking_batch),
                    tracked=len(pickings),
                    requested=len(pickings_no_label_requested),
                    processing=len(pickings_label_requested),
                    ready=len(pickings_label_ready_to_print),
                )
                pickings_label_ready_to_print._download_shipping_label(shop)
            except utils.ShopeeRateLimitError:
                raise
            except Exception as error:
                _logger.warning("_update_shipment_label failed", exc_info=True)
                _debug.logic(
                    "label_batch_failed",
                    shop=shop,
                    pickings=picking_batch,
                    error=type(error).__name__,
                )
                error_messages.append(
                    {
                        "batch_picking_refs": ", ".join(picking_batch.mapped("name")),
                        "message": str(error),
                    }
                )
                continue
            finally:
                picking_batch.write({"last_picking_sync_date": current_datetime})
                if auto_commit:
                    self.env["ir.cron"]._commit_progress(processed=len(picking_batch))

        if error_messages:
            shop._handle_sync_failure(
                flow="picking_sync", error_messages=error_messages
            )

    def _set_tracking_number(self, shop) -> None:
        for picking in self.filtered(lambda p: not p.carrier_tracking_ref):
            tracking_number = utils.send_shopee_api_request(
                shop, "get_tracking_number", {"order_sn": picking.shopee_order_ref}
            ).get("tracking_number")
            _debug.logic(
                "tracking_number_fetched",
                picking=picking,
                found=bool(tracking_number),
            )
            if tracking_number:
                picking.carrier_tracking_ref = tracking_number

    def _update_shipping_label(self, shop) -> None:

        for i in range(0, len(self), const.SHIPPING_DOCUMENT_SIZE_LIMIT):
            pickings = self[i : i + const.SHIPPING_DOCUMENT_SIZE_LIMIT]
            order_list = [
                {
                    "order_sn": pick.shopee_order_ref,
                    "tracking_number": pick.carrier_tracking_ref,
                }
                for pick in pickings
            ]
            response = utils.send_shopee_api_request(
                shop,
                "create_shipping_document",
                body={"order_list": order_list},
                method="POST",
            )
            failed_orders = {
                result["order_sn"]
                for result in response["result_list"]
                if result.get("fail_error")
            }

            failed_pickings = pickings.browse(
                [
                    picking.id
                    for picking in pickings
                    if picking.shopee_order_ref in failed_orders
                ]
            )
            failed_pickings.shopee_label_status = "failed"

            successful_pickings = pickings - failed_pickings
            successful_pickings.shopee_label_status = "processing"

    def _update_shipping_label_status(self, shop) -> None:
        for i in range(0, len(self), const.SHIPPING_DOCUMENT_SIZE_LIMIT):
            pickings = self[i : i + const.SHIPPING_DOCUMENT_SIZE_LIMIT]
            order_list = [
                {"order_sn": picking.shopee_order_ref} for picking in pickings
            ]
            response = utils.send_shopee_api_request(
                shop,
                "get_shipping_document_result",
                body={"order_list": order_list},
                method="POST",
            )
            order_sn_status = {
                res["order_sn"]: res["status"] for res in response["result_list"]
            }
            for picking in pickings:
                status = order_sn_status.get(picking.shopee_order_ref)
                if status:
                    picking.shopee_label_status = (
                        const.LOWER_SHIPPING_LABEL_MAPPING.get(status, "failed")
                    )

    def _download_shipping_label(self, shop) -> None:
        for picking in self:
            order_sn = picking.shopee_order_ref
            content = utils.send_shopee_api_request(
                shop,
                "download_shipping_document",
                body={
                    "order_list": [{"order_sn": order_sn}],
                },
                method="POST",
            )
            attachment_name = f"Shopee_Label_{picking.name.replace(' ', '_')}.pdf"
            existing_attachment = self.env["ir.attachment"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("name", "=", attachment_name),
                    ("res_model", "=", "stock.picking"),
                    ("res_id", "=", picking.id),
                ],
                limit=1,
            )
            if not existing_attachment:
                picking.message_post(
                    subject=self.env._("Shopee Label"),
                    attachments=[(attachment_name, content)],
                )
            picking.shopee_label_status = "stored"

    def _sync_processing_pickings(self):
        processing_pickings = self.search([("shopee_label_status", "=", "processing")])
        if processing_pickings:
            return processing_pickings._sync_shopee_pickings()
        return None
