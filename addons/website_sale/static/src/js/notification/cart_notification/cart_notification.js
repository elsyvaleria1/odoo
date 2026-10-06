/** @odoo-module native */
import { Component, onMounted, t, useProps } from "@odoo/owl";

import { AddToCartNotification } from "../add_to_cart_notification/add_to_cart_notification.js";
import { WarningNotification } from "../warning_notification/warning_notification.js";

const AUTOCLOSE_DELAY = 4000;

export class CartNotification extends Component {
    static components = { AddToCartNotification, WarningNotification };
    static template = "website_sale.cartNotification";
    static props = {
        message: t.or([t.string(), t.any()]),
        warning: t.or([t.string(), t.any()]).optional(),
        lines: t
            .array(
                t.object({
                    id: t.number(),
                    linked_line_id: t.number().optional(),
                    image_url: t.string(),
                    quantity: t.number(),
                    uom_name: t.string().optional(),
                    name: t.string(),
                    combination_name: t.string().optional(),
                    description: t.string().optional(),
                    price_total: t.number(),
                }),
            )
            .optional(),
        currency_id: t.number().optional(),
        className: t.string(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        onMounted(() => setTimeout(this.props.close, AUTOCLOSE_DELAY));
    }

    get positionOffset() {
        return (
            (document.querySelector("header.o_top_fixed_element")?.offsetHeight || 0) +
            "px"
        );
    }
}
