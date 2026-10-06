/** @odoo-module native */
import { Component, t, useListener, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import { useScrollShadow } from "../../utils/scroll_shadow_hook.js";

export class CategoryListPopup extends Component {
    static template = "pos_self_order.CategoryListPopup";
    static props = {
        close: t.function(),
        categories: t.object(),
        onCategorySelected: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.scrollContainerRef = elementRef();
        this.scrollShadow = useScrollShadow(this.scrollContainerRef);
        useListener(window, "click", this.props.close.bind(this));
    }

    selectCategory(cat) {
        this.props.close();
        this.props.onCategorySelected(cat);
    }
}
