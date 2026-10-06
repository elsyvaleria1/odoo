/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

export class QuantityButtons extends Component {
    static template = "sale.QuantityButtons";
    static props = {
        quantity: t.number(),
        setQuantity: t.function(),
        isMinusButtonDisabled: t.boolean().optional(),
        isPlusButtonDisabled: t.boolean().optional(),
        btnClasses: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    increaseQuantity() {
        this.props.setQuantity(this.props.quantity + 1);
    }

    decreaseQuantity() {
        this.props.setQuantity(this.props.quantity - 1);
    }

    /** @param {Event} event */
    async setQuantity(event) {
        const quantity = parseFloat(event.target.value);
        const didUpdateQuantity = await this.props.setQuantity(
            isNaN(quantity) ? 0 : quantity,
        );
        if (!didUpdateQuantity) {
            event.target.value = this.props.quantity;
        }
    }
}
