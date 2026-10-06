/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";

import { Product } from "../product/product.js";

export class ProductList extends Component {
    static components = { Product };
    static template = "sale.ProductList";
    static props = {
        products: t.array(),
        areProductsOptional: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.optionalProductsTitle = _t("Add optional products");
    }
}
