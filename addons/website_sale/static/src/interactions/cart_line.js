/** @odoo-module native */
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class CartLine extends Interaction {
    static selector = ".o_cart_product";
    dynamicContent = {
        ".css_quantity > input.js_quantity": {
            "t-on-change.withTarget": this.locked(
                this.debounced(this.changeQuantity, 500),
            ),
        },
        ".css_quantity > a": {
            "t-on-click.prevent.withTarget": this.locked(this.incOrDecQuantity),
        },
        ".js_delete_product": { "t-on-click.prevent": this.locked(this.deleteProduct) },
    };

    /**
     * @param {Event} ev
     * @param {HTMLElement} currentTargetEl
     */
    async changeQuantity(ev, currentTargetEl) {
        await this._changeQuantity(currentTargetEl);
    }

    /**
     * @param {Event} ev
     * @param {HTMLElement} currentTargetEl
     */
    async incOrDecQuantity(ev, currentTargetEl) {
        const input = currentTargetEl
            .closest(".css_quantity")
            .querySelector("input.js_quantity");
        const maxQuantity = parseFloat(input.dataset.max || Infinity);
        const oldQuantity = parseFloat(input.value || 0);
        const newQuantity = currentTargetEl
            .querySelector("i")
            .classList.contains("oi-minus")
            ? Math.min(Math.max(oldQuantity - 1, 0), maxQuantity)
            : Math.min(oldQuantity + 1, maxQuantity);
        if (oldQuantity !== newQuantity) {
            input.value = newQuantity;
            await this._changeQuantity(input);
        }
    }

    /**
     * @param {Event} ev
     */
    async deleteProduct(ev) {
        const input = ev.currentTarget
            .closest(".o_cart_product")
            .querySelector(".css_quantity > input.js_quantity");
        input.value = 0;
        await this._changeQuantity(input);
    }

    async _changeQuantity(input) {
        let quantity = parseInt(input.value || 0);
        if (isNaN(quantity)) {
            quantity = 1;
        }
        const lineId = parseInt(input.dataset.lineId);
        const response = await this.waitFor(
            rpc("/shop/cart/update", {
                line_id: lineId,
                product_id: parseInt(input.dataset.productId),
                quantity: quantity,
            }),
        );
        if (!response.redirect) {
            // the morph leaves a focused field as typed: the server's quantity goes in first
            this.el
                .querySelectorAll(`.js_quantity[data-line-id="${lineId}"]`)
                .forEach((input) => (input.value = response.data.quantity));
            input.value = response.data.quantity;
        }
        this.swapFragments(response);
    }
}

registry.category("public.interactions").add("website_sale.cart_line", CartLine);
