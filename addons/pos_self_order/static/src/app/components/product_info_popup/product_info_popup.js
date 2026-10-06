/** @odoo-module native */
import { Component, proxy, t, useListener, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import { useScrollShadow } from "../../utils/scroll_shadow_hook.js";
export class ProductInfoPopup extends Component {
    static template = "pos_self_order.ProductInfoPopup";
    static props = { productTemplate: t.object(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.scrollContainerRef = elementRef();
        this.scrollShadow = useScrollShadow(this.scrollContainerRef);
        useListener(window, "click", this.props.close.bind(this));
        this.state = proxy({
            qty: 1,
        });
    }
}
