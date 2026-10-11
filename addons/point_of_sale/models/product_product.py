from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductProduct(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "mixin.pos.load"]

    def _get_inactive_ids(self, config):
        removed = super()._get_inactive_ids(config)
        kept = self - self.browse(removed)
        templates = kept.product_tmpl_id
        removed_templates = templates.browse(templates._get_inactive_ids(config))
        return (
            removed
            + kept.filtered(
                lambda product: product.product_tmpl_id in removed_templates
            ).ids
        )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("product_tmpl_id", "in", [p["id"] for p in data["product.template"]])]

    @api.model
    def _load_pos_data_fields(self, config):
        return sorted(
            config._get_tax_product_field_names().union(
                {
                    "id",
                    "lst_price",
                    "display_name",
                    "product_tmpl_id",
                    "product_template_variant_value_ids",
                    "currency_id",
                    "product_template_attribute_value_ids",
                    "barcode",
                    "product_tag_ids",
                    "default_code",
                    "standard_price",
                }
            )
        )

    @api.model
    @_debug.perf.timed
    def get_pos_stock_quantities(self, product_ids, config_id):
        config = self.env["pos.config"].browse(config_id)
        config.check_access("read")
        products = (
            self.browse(product_ids)
            .exists()
            .with_context(**config._prepare_stock_quantity_context())
        )
        quantities = dict.fromkeys(product_ids, 0.0)
        for product in products:
            quantities[product.id] = product.qty_available
        _debug.logic(
            "stock_quantities",
            config=config_id,
            requested=len(product_ids),
            scope=config._get_stock_scope(),
            found=len(products),
        )
        return quantities

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active_pos_session(self) -> None:
        product_ctx = dict(self.env.context or {}, active_test=False)
        if (
            self.env["pos.session"]
            .sudo()
            .search_count([("state", "!=", "closed")], limit=1)
        ):
            if self.with_context(product_ctx).search_count(
                [
                    ("id", "in", self.ids),
                    ("product_tmpl_id.available_in_pos", "=", True),
                ],
                limit=1,
            ):
                raise UserError(
                    self.env._(
                        "To delete a product, make sure all point of sale sessions are closed.\n\n"
                        "Deleting a product available in a session would be like attempting to snatch a hamburger from a customer’s hand mid-bite; chaos will ensue as ketchup and mayo go flying everywhere!",
                    )
                )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_special_product(self) -> None:
        self.product_tmpl_id._check_is_special_product()

    @api.model
    @_debug.perf.timed
    def _load_pos_data_read(self, records, config):
        records = records._with_pos_company(config)
        rows = super()._load_pos_data_read(records, config)
        if not rows:
            return rows

        company = config.company_id
        target = config.currency_id
        today = fields.Date.today()
        cost_currency_by_id = {
            product.id: product.cost_currency_id
            for product in self.browse([row["id"] for row in rows]).with_company(
                company
            )
        }
        list_currency_by_id = {
            currency.id: currency
            for currency in self.env["res.currency"].browse(
                {row["currency_id"] for row in rows if row["currency_id"]}
            )
        }
        for row in rows:
            list_currency = list_currency_by_id.get(row["currency_id"])
            if list_currency and list_currency != target:
                row["lst_price"] = list_currency._convert(
                    row["lst_price"], target, company, today
                )
            cost_currency = cost_currency_by_id[row["id"]]
            if cost_currency and cost_currency != target:
                row["standard_price"] = cost_currency._convert(
                    row["standard_price"], target, company, today
                )
        return rows

    def write(self, vals):
        if "active" in vals and not vals["active"]:
            self.product_tmpl_id._check_is_special_product()
        return super().write(vals)

    def _can_return_content(self, field_name=None, access_token=None) -> bool:
        if field_name == "image_128" and self.sudo().available_in_pos:
            return True
        return super()._can_return_content(field_name, access_token)
