/** @odoo-module native */
import { PaymentPostProcessing } from "@payment/interactions/post_processing";
import { patch } from "@web/core/utils/patch";

patch(PaymentPostProcessing, {
    /**
     * @override
     * @param {string} providerCode
     */
    getFinalStates(providerCode) {
        const finalStates = super.getFinalStates(...arguments);
        if (providerCode === "custom") {
            finalStates.add("pending");
        }
        return finalStates;
    },
});
