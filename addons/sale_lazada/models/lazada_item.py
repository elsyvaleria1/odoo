from itertools import batched

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.json import dumps as json_dumps

from odoo.addons.sale_lazada import const, utils


class LazadaItem(models.Model):
    _name = "lazada.item"
    _description = "Lazada Item"
    _check_company_auto = True

    shop_id = fields.Many2one(
        comodel_name="lazada.shop",
        index=True,
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
        ondelete="cascade",
        check_company=True,
    )
    product_tmpl_id = fields.Many2one(
        related="product_id.product_tmpl_id",
        string="Product Template",
    )
    company_id = fields.Many2one(related="shop_id.company_id")
    lazada_sku = fields.Char(
        string="Lazada SKU",
        readonly=True,
        help="The SKU of the item in Lazada. Odoo can match the product when the Lazada SKU is "
        "equivalent to the default code of the product.",
    )
    lazada_item_extern_id = fields.Char(
        string="Lazada Item ID",
        readonly=True,
        required=True,
        help="The unique identifier for an item in Lazada. An item in Lazada is equivalent "
        "to a product variant in Odoo.",
    )
    last_inventory_sync_date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
    )
    sync_lazada_inventory = fields.Boolean(
        string="Synchronize Inventory to Lazada",
        compute="_compute_sync_lazada_inventory",
        precompute=True,
        store=True,
        readonly=False,
        help="Enable this to allow pushing the product inventory quantities from Odoo to Lazada.",
    )
    fulfillment_type = fields.Selection(
        selection=[
            ("fbm", "Fulfillment by Merchant"),
            ("fbl", "Fulfillment by Lazada"),
        ],
        default="fbm",
        readonly=True,
    )

    _unique_lazada_item_extern_id = models.Constraint(
        "UNIQUE(shop_id, lazada_item_extern_id)",
        "Item External IDs must be unique for a given shop.",
    )

    @api.constrains("sync_lazada_inventory", "fulfillment_type", "product_id")
    def _check_sync_to_lazada(self) -> None:
        default_sale_product = self.env.ref("sale_lazada.default_sale_product")
        for item in self.filtered(lambda item: item.product_id != default_sale_product):
            if not item.product_id.type == "consu" or not item.product_id.is_storable:
                raise ValidationError(
                    self.env._(
                        "We do not support syncing services or combo products to Lazada. "
                        "Only storable products are supported."
                    )
                )

            if item.fulfillment_type != "fbm" and item.sync_lazada_inventory:
                raise ValidationError(
                    self.env._("Only FBM items can be synced to Lazada.")
                )

    @api.depends("fulfillment_type", "product_id.is_storable")
    def _compute_sync_lazada_inventory(self) -> None:
        for item in self:
            item.sync_lazada_inventory = (
                item.fulfillment_type == "fbm" and item.product_id.is_storable
            )

    def _sync_inventory(self, auto_commit=True) -> None:
        error_messages = []
        valid_items = self.filtered("sync_lazada_inventory").sorted(
            "last_inventory_sync_date"
        )
        for shop, items in valid_items.grouped("shop_id").items():
            try:
                shop = shop.with_prefetch()
                items = items.with_prefetch()
                self._update_inventory(shop, items)
                if auto_commit:
                    self.env["ir.cron"]._commit_progress(processed=len(items))
            except utils.LazadaApiError as error:
                error_messages.append(
                    {
                        "default_codes": items.mapped("product_id.default_code"),
                        "message": str(error),
                    }
                )
        if error_messages:
            self.shop_id._handle_sync_failure(
                flow="inventory_sync", error_messages=error_messages
            )

    @api.model
    def _prepare_sync_inventory_payload(self, shop, items):
        vals = []
        warehouse_id = shop.fbm_warehouse_id.id
        is_same_warehouse = shop.fbl_location_id.warehouse_id.id == warehouse_id
        for item in items:
            fbm_item = item.with_context(warehouse_id=warehouse_id).with_company(
                shop.company_id
            )
            fbm_qty = fbm_item.product_id.qty_free
            if not shop.manage_fbl_inventory and is_same_warehouse:
                fbl_item = item.with_context(
                    location=shop.fbl_location_id.id
                ).with_company(shop.company_id)
                fbm_qty -= fbl_item.product_id.qty_free
            fbm_qty = int(max(fbm_qty, 0))
            vals.append(
                {
                    "SkuId": item.lazada_item_extern_id,
                    "SellerSku": item.lazada_sku,
                    "SellableQuantity": fbm_qty,
                }
            )
        return json_dumps({"Request": {"Product": {"Skus": {"Sku": vals}}}})

    def _update_inventory(self, shop, items) -> None:
        shop.check_singleton()
        for batch_items in (
            items.browse(b)
            for b in batched(items.ids, const.SYNC_INVENTORY_SIZE_LIMIT, strict=False)
        ):
            current_datetime = fields.Datetime.now()
            payload = self._prepare_sync_inventory_payload(shop, batch_items)
            utils.send_lazada_api_request(
                "UpdateSellableQuantity",
                shop,
                params={"payload": payload},
                method="POST",
            )

            batch_items.last_inventory_sync_date = current_datetime
