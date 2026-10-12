from typing import TYPE_CHECKING, Any, Literal

from odoo.exceptions import UserError
from odoo.http import Controller, request, route
from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from odoo.addons.product.models.mixin_product_catalog import (
        CatalogSection,
        MixinProductCatalog,
    )

_debug = DebugLog(__name__)


class ProductCatalogController(Controller):
    @staticmethod
    def _get_order(
        res_model: str,
        order_id: int | str | Literal[False] | None,
        allow_unsaved: bool = False,
        for_write: bool = False,
    ) -> MixinProductCatalog:
        env = request.env
        if res_model not in env.registry or not isinstance(
            env[res_model], env.registry["mixin.product.catalog"]
        ):
            raise UserError(
                request.env._("The product catalog cannot be used on this model.")
            )
        if allow_unsaved and not order_id:
            return env[res_model]
        try:
            order_id = int(order_id)
        except ValueError, TypeError:
            raise UserError(
                request.env._("The requested record does not exist.")
            ) from None
        order = env[res_model].browse(order_id).exists()
        if not order:
            raise UserError(request.env._("The requested record does not exist."))
        if for_write and order._is_readonly():
            raise UserError(
                request.env._("You cannot edit the products of a read-only record.")
            )
        return order

    @route(
        "/product/catalog/order_lines_info", auth="user", type="jsonrpc", readonly=True
    )
    def product_catalog_get_order_lines_info(
        self, res_model, order_id, product_ids, **kwargs: Any
    ) -> dict[int, dict[str, Any]]:
        order = self._get_order(res_model, order_id, allow_unsaved=True)
        return order.with_company(
            order.company_id
        )._get_product_catalog_order_line_info(
            product_ids,
            **kwargs,
        )

    @route("/product/catalog/update_order_line_info", auth="user", type="jsonrpc")
    def product_catalog_update_order_line_info(
        self, res_model, order_id, product_id, quantity=0, **kwargs: Any
    ):
        order = self._get_order(res_model, order_id, for_write=True)
        return order.with_company(order.company_id)._update_order_line_info(
            product_id,
            quantity,
            **kwargs,
        )

    @route("/product/catalog/get_sections", auth="user", type="jsonrpc", readonly=True)
    def product_catalog_get_sections(
        self, res_model, order_id, child_field, **kwargs: Any
    ) -> list[CatalogSection]:
        _debug.pipeline(
            "route",
            handler="ProductCatalogController.product_catalog_get_sections",
        )
        order = self._get_order(res_model, order_id)
        return order.with_company(order.company_id)._get_sections(child_field, **kwargs)

    @route("/product/catalog/create_section", auth="user", type="jsonrpc")
    def product_catalog_create_section(
        self,
        res_model,
        order_id,
        child_field,
        name,
        position,
        **kwargs: Any,
    ) -> dict[str, int]:
        _debug.pipeline(
            "route",
            handler="ProductCatalogController.product_catalog_create_section",
        )
        order = self._get_order(res_model, order_id, for_write=True)
        return order.with_company(order.company_id)._create_section(
            child_field,
            name,
            position,
            **kwargs,
        )

    @route("/product/catalog/resequence_sections", auth="user", type="jsonrpc")
    def product_catalog_resequence_sections(
        self,
        res_model,
        order_id,
        sections,
        child_field,
        **kwargs: Any,
    ) -> dict[int, int]:
        _debug.pipeline(
            "route",
            handler="ProductCatalogController.product_catalog_resequence_sections",
        )
        order = self._get_order(res_model, order_id, for_write=True)
        return order.with_company(order.company_id)._resequence_sections(
            sections,
            child_field,
            **kwargs,
        )
