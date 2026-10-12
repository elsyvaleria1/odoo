from itertools import batched
from urllib.parse import urlparse

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_lazada import const, utils

_debug = DebugLog(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    lazada_order_ref = fields.Char(related="sale_id.lazada_order_ref")

    lazada_package_status = fields.Selection(
        selection=[
            ("draft", "Package Pending on Lazada"),
            ("confirmed", "Package Confirmed on Lazada"),
            ("processing", "Ready to Ship on Lazada"),
            ("delivered", "Delivered on Lazada"),
            ("canceled", "Canceled on Lazada"),
            ("manual", "Manual handling required"),
        ],
        compute="_compute_lazada_package_status",
    )

    last_lazada_picking_sync_date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        help="The last time the picking was synchronized with Lazada.",
    )
    package_extern_id = fields.Char(
        string="Lazada Package ID",
        readonly=True,
        help="The package identifier for the picking.",
    )
    lazada_shipping_allocate_type = fields.Char(
        readonly=True,
        help="The shipping allocate type for the picking.",
    )
    lazada_label_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="stock_picking_lazada_label_attachment_rel",
        help="The attachments that are related to the Lazada label.",
    )

    @api.depends("move_ids.lazada_order_item_ids.status")
    def _compute_lazada_package_status(self) -> None:
        for picking in self:
            picking.lazada_package_status = utils.get_lazada_aggregated_status(
                picking.move_ids.lazada_order_item_ids.mapped("status")
            )

    def _pack_lazada_package(self) -> None:
        pickings_by_shop = self._get_lazada_pickings_by_shop()

        for all_pickings in pickings_by_shop.values():
            to_pack_pickings = all_pickings.filtered(
                lambda p: (
                    p.move_ids.lazada_order_item_ids
                    and p.lazada_package_status == "draft"
                    and not p.package_extern_id
                )
            )
            picking_sorted = to_pack_pickings.sorted("last_lazada_picking_sync_date")
            for picking in picking_sorted:
                if not picking.lazada_shipping_allocate_type:
                    picking._update_lazada_shipping_allocation()
                picking._pack_picking()

    def _download_lazada_labels_and_mark_ready_to_ship(self) -> None:
        pickings_by_shop = self._get_lazada_pickings_by_shop()

        error_messages = []
        for shop, all_pickings in pickings_by_shop.items():
            to_download_pickings = all_pickings.filtered(
                lambda p: p.lazada_package_status not in ["canceled", "draft"]
            )
            for picking in to_download_pickings:
                try:
                    picking._download_lazada_shipping_label(shop)
                except utils.LazadaApiError as error:
                    error_messages.append(
                        {"picking_ids": picking.id, "message": str(error)}
                    )
                    continue

            to_update_rts_pickings = all_pickings.filtered(
                lambda p: (
                    p.lazada_package_status == "processing"
                    and p.lazada_label_attachment_ids
                )
            )

            for picking_batch in (
                self.browse(b)
                for b in batched(
                    to_update_rts_pickings.ids, const.SET_RTS_SIZE_LIMIT, strict=False
                )
            ):
                try:
                    picking_batch._set_lazada_rts(shop)
                except utils.LazadaApiError as error:
                    error_messages.append(
                        {"picking_ids": picking_batch.ids, "message": str(error)}
                    )
                    continue
        if error_messages:
            formatted_errors = "\n".join(
                f"- {err['picking_ids']}: {err['message']}" for err in error_messages
            )
            raise UserError(
                self.env._(
                    "Failed to set Ready to Ship status for pickings:\n%(error_msg)s",
                    error_msg=formatted_errors,
                )
            )

    def _get_shipment_provider_data(self, order_id, order_item_ids):
        shop = self.sale_id.lazada_shop_id
        shop.check_singleton()
        response = utils.send_lazada_api_request(
            "GetShipmentProvider",
            shop,
            params={
                "getShipmentProvidersReq": str(
                    {
                        "orders": [
                            {"order_id": order_id, "order_item_ids": order_item_ids}
                        ]
                    }
                )
            },
        )
        if response["result"]["success"]:
            return response["result"]["data"]
        raise UserError(
            self.env._(
                "Failed to get shipment provider for order: %(order_id)s. Error: %(error_msg)s",
                order_id=order_id,
                error_msg=response["error_msg"],
            )
        )

    def _set_lazada_rts(self, shop) -> None:
        for pickings in (
            self.browse(b)
            for b in batched(self.ids, const.SET_RTS_SIZE_LIMIT, strict=False)
        ):
            payload = pickings._prepare_lazada_rts_payload()
            payload = {"readyToShipReq": str(payload)}
            with _debug.perf("lazada_set_rts", shop=shop) as span:
                span.set(pickings=len(pickings))
                content = utils.send_lazada_api_request(
                    "SetReadyToShip", shop, params=payload, method="POST"
                )

            if not content.get("result", {}).get("success"):
                _debug.logic(
                    "lazada_rts_refused",
                    shop=shop,
                    pickings=pickings,
                    code=content.get("result", {}).get("error_code"),
                )
                raise utils.LazadaApiError(
                    shop,
                    "SetReadyToShip",
                    content.get("request_id"),
                    content.get("result", {}).get("error_code"),
                    content.get("result", {}).get("error_msg"),
                )

            _debug.lifecycle(
                "lazada_rts_set", shop=shop, pickings=pickings, status="processing"
            )
            pickings.lazada_package_status = "processing"

    def _download_lazada_shipping_label(self, shop) -> None:
        for picking in self:
            payload = picking._prepare_lazada_shipping_label_payload()
            content = utils.send_lazada_api_request(
                "PrintAWB", shop, params={"getDocumentReq": str(payload)}, method="POST"
            )

            if not content.get("result", {}).get("success"):
                raise utils.LazadaApiError(
                    shop,
                    "PrintAWB",
                    content.get("request_id"),
                    content.get("result", {}).get("error_code"),
                    content.get("result", {}).get("error_msg"),
                )
            attachment_name = f"Lazada_Label_{picking.carrier_tracking_ref}.pdf"

            pdf_url = content["result"]["data"]["pdf_url"]
            parsed = urlparse(pdf_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or not any(
                    parsed.hostname.endswith(domain)
                    for domain in const.ALLOWED_LAZADA_DOC_HOSTS
                )
            ):
                raise UserError(self.env._("Invalid Lazada document URL"))
            response = self.env["ir.egress"].request(
                "GET", pdf_url, purpose="lazada", timeout=10, allow_redirects=False
            )

            if response.status_code != 200:
                raise UserError(
                    self.env._(
                        "Failed to download shipping label for picking %(picking_id)s: "
                        "HTTP Status Code %(error_code)s",
                        picking_id=picking.id,
                        error_msg=str(response.status_code),
                    )
                )

            message = picking.message_post(
                subject=self.env._("Lazada Label"),
                attachments=[(attachment_name, response.content)],
            )
            picking.lazada_label_attachment_ids += message.attachment_ids

            picking.move_ids.lazada_order_item_ids.status = "processing"

    def _pack_picking(self) -> None:
        self.check_singleton()
        try:
            payload = self._prepare_package_payload()
            shop = self.sale_id.lazada_shop_id
            date_now = fields.Datetime.now()
            content = utils.send_lazada_api_request(
                "PackagePack", shop, params={"packReq": str(payload)}, method="POST"
            )

            if not content.get("result", {}).get("success"):
                _debug.logic(
                    "lazada_pack_refused",
                    picking=self,
                    shop=shop,
                    reason="api_failure",
                    code=content.get("result", {}).get("error_code"),
                )
                raise utils.LazadaApiError(
                    shop,
                    "PackagePack",
                    content.get("request_id"),
                    content.get("result", {}).get("error_code"),
                    content.get("result", {}).get("error_msg"),
                )

            for package_data in content["result"]["data"]["pack_order_list"]:
                error_items = []
                valid_items = []
                for item in package_data["order_item_list"]:
                    if int(item.get("item_err_code")):
                        error_items.append(item)
                    else:
                        valid_items.append(item)
                _debug.logic(
                    "lazada_pack_items",
                    picking=self,
                    valid=len(valid_items),
                    errored=len(error_items),
                )
                if error_items:
                    error_msg = "\n".join(
                        [
                            f"Item #{item['order_item_id']} - {item['msg']}"
                            for item in error_items
                        ]
                    )
                    raise utils.LazadaApiError(
                        shop,
                        "PackagePack",
                        content.get("request_id"),
                        content.get("result", {}).get("error_code", "N/A"),
                        error_msg,
                    )
                package_extern_id = next(
                    iter({item["package_id"] for item in valid_items})
                )
                tracking_number = next(
                    iter({item["tracking_number"] for item in valid_items})
                )
                _debug.lifecycle(
                    "lazada_package_packed",
                    picking=self,
                    package=package_extern_id,
                    tracking=tracking_number,
                )
                self.package_extern_id = package_extern_id
                self.carrier_tracking_ref = tracking_number
                self.last_lazada_picking_sync_date = date_now

                order_item_extern_ids = [
                    str(item["order_item_id"]) for item in valid_items
                ]
                self.move_ids.lazada_order_item_ids.filtered_domain(
                    [("order_item_extern_id", "in", order_item_extern_ids)]
                ).write({"status": "confirmed"})
        except utils.LazadaRateLimitError as e:
            _debug.logic("lazada_pack_refused", picking=self, reason="rate_limit")
            raise UserError(
                self.env._("Lazada API rate limit reached. Please try again later.")
            ) from e

    def _update_lazada_shipping_allocation(self) -> None:
        self.check_singleton()
        if not self.lazada_order_ref:
            raise UserError(
                self.env._(
                    "The Lazada order reference is required to get the shipment provider."
                )
            )
        draft_items = self.move_ids.lazada_order_item_ids.filtered(
            lambda i: i.status == "draft"
        )
        order_id = int(self.lazada_order_ref)
        order_item_ids = list(map(int, draft_items.mapped("order_item_extern_id")))
        _debug.pipeline(
            "shipment_provider_requested",
            picking=self,
            order=order_id,
            draft_items=len(draft_items),
        )
        data = self._get_shipment_provider_data(order_id, order_item_ids)
        if not data.get("shipping_allocate_type"):
            _debug.logic(
                "shipment_provider_unresolved", picking=self, reason="no_allocate_type"
            )
            raise UserError(self.env._("Failed to get shipment provider."))

        _debug.lifecycle(
            "shipment_provider_set",
            picking=self,
            allocate_type=data["shipping_allocate_type"],
        )
        self.lazada_shipping_allocate_type = data["shipping_allocate_type"]

    def _get_lazada_pickings_by_shop(self):
        domain = [
            ("id", "in", self.ids),
            ("sale_id.lazada_shop_id", "!=", False),
            ("lazada_order_ref", "!=", False),
            ("state", "not in", ["done", "cancel"]),
        ]
        _debug.perf.count("lazada_pickings_grouped", asked=len(self))
        return self.search(domain).grouped(lambda p: p.sale_id.lazada_shop_id)

    def _prepare_package_payload(self) -> dict:
        self.check_singleton()
        if not self.lazada_order_ref:
            raise ValidationError(self.env._("No Lazada order reference found."))

        result = {
            "shipping_allocate_type": self.lazada_shipping_allocate_type,
            "delivery_type": "dropship",
        }
        draft_order_item_extern_ids = self.move_ids.lazada_order_item_ids.filtered(
            lambda i: i.status == "draft"
        ).mapped("order_item_extern_id")
        if not draft_order_item_extern_ids:
            raise ValidationError(self.env._("No Lazada order item found to pack."))

        return {
            **result,
            "pack_order_list": [
                {
                    "order_id": self.lazada_order_ref,
                    "order_item_list": draft_order_item_extern_ids,
                }
            ],
        }

    def _prepare_lazada_shipping_label_payload(self) -> dict:
        self.check_singleton()
        return {"packages": [{"package_id": self.package_extern_id}], "doc_type": "PDF"}

    def _prepare_lazada_rts_payload(self) -> dict:
        return {
            "packages": [{"package_id": picking.package_extern_id} for picking in self]
        }

    def action_fetch_shipping_label(self) -> None:
        self._download_lazada_labels_and_mark_ready_to_ship()

    def action_pack_lazada_package(self) -> None:
        self._pack_lazada_package()
