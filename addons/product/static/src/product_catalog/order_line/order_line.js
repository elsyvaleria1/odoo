/** @odoo-module native */
import { Component, Portal, t, useProps } from "@odoo/owl";
import { useProductCatalogContext } from "@product/product_catalog/product_catalog_context";
import { formatFieldFloat, formatMonetary } from "@web/core/formatters";

export const productCatalogOrderLineProps = {
    isSample: t.boolean().optional(),
    productId: t.number(),
    quantity: t.number(),
    price: t.number(),
    productType: t.string(),
    uomDisplayName: t.string(),
    uomFactor: t.number().optional(),
    code: t.string().optional(),
    readOnly: t.boolean().optional(),
    warning: t.string().optional(),
};

export class ProductCatalogOrderLine extends Component {
    static template = "product.ProductCatalogOrderLine";
    static components = { Portal };
    static props = productCatalogOrderLineProps;
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.catalogContext = useProductCatalogContext();
    }

    /**
     * Focus input text when clicked
     * @param {Event} ev
     */
    _onFocus(ev) {
        ev.target.select();
    }

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    isInOrder() {
        return this.props.quantity !== 0;
    }

    get disableRemove() {
        return false;
    }

    get disabledButtonTooltip() {
        return "";
    }

    get price() {
        const { currencyId, digits } = this.catalogContext;
        return formatMonetary(this.props.price, { currencyId, digits });
    }

    get quantity() {
        const digits = [false, this.catalogContext.precision];
        const options = { digits, decimalPoint: ".", thousandsSep: "" };
        return parseFloat(formatFieldFloat(this.props.quantity, options));
    }

    get showPrice() {
        return true;
    }
}
