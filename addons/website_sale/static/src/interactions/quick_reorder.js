/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class QuickReorder extends Interaction {
    static selector = "#quick_reorder_sidebar";
    dynamicContent = {
        _document: {
            "t-on-website_sale:cart_updated": this.focusNextQuantityInput,
        },
        ".o_wsale_quick_reorder_line": {
            "t-on-submit": this.rememberLine,
        },
        ".o_wsale_quick_reorder_qty_input": {
            "t-on-input": this.updateQuantityAndPrice,
        },
    };

    setup() {
        this.submittedLineIndex = null;
    }

    /**
     * @param {Event} ev
     * @return {void}
     */
    updateQuantityAndPrice(ev) {
        const qtyInput = ev.currentTarget;
        const priceUnit = parseFloat(qtyInput.dataset.priceUnit);
        const digits = parseInt(qtyInput.dataset.currencyDigits, 10);
        const qty = parseInt(qtyInput.value, 10) || 0;
        qtyInput
            .closest(".o_wsale_quick_reorder_line")
            .querySelector(".o_wsale_quick_reorder_product_button").disabled = qty <= 0;
        if (qty > 0) {
            this._updateTotalPrice(qtyInput, qty, priceUnit, digits);
        }
    }

    /**
     * @private
     * @param {Element} qtyInput
     * @param {number} qty
     * @param {number} priceUnit
     * @param {number} digits
     * @return {void}
     */
    _updateTotalPrice(qtyInput, qty, priceUnit, digits) {
        const priceEl = qtyInput
            .closest(".o_wsale_quick_reorder_line")
            .querySelector(".o_wsale_quick_reorder_product_price .oe_currency_value");
        if (priceEl) {
            priceEl.textContent = (qty * priceUnit).toFixed(digits);
        }
    }

    /** @param {SubmitEvent} ev */
    rememberLine(ev) {
        this.submittedLineIndex = [
            ...this.el.querySelectorAll(".o_wsale_quick_reorder_line"),
        ].indexOf(/** @type {HTMLFormElement} */ (ev.currentTarget));
    }

    /** @param {CustomEvent<{ quick_reorder?: boolean }>} ev */
    focusNextQuantityInput(ev) {
        if (!ev.detail?.quick_reorder || this.submittedLineIndex === null) {
            return;
        }
        const nextInput = this.el.querySelectorAll(".o_wsale_quick_reorder_qty_input")[
            this.submittedLineIndex
        ];
        this.submittedLineIndex = null;
        if (nextInput) {
            nextInput.focus();
            nextInput.select();
        }
    }
}

registry
    .category("public.interactions")
    .add("website_sale.quick_reorder", QuickReorder);
