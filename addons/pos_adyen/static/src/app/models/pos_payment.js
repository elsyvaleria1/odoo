/** @odoo-module native */
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { patch } from "@web/core/utils/patch";
patch(PosPayment.prototype, {
    initState() {
        super.initState();
        this.uiState = { ...this.uiState, adyenServiceId: null };
    },
    get terminalServiceId() {
        return this.uiState?.adyenServiceId ?? null;
    },
    setTerminalServiceId(id) {
        this.uiState = { ...this.uiState, adyenServiceId: id, adyenUnconfirmed: false };
    },
    handlePaymentResponse(isPaymentSuccessful) {
        if (!isPaymentSuccessful && this.uiState?.adyenUnconfirmed) {
            return false;
        }
        return super.handlePaymentResponse(...arguments);
    },
});
