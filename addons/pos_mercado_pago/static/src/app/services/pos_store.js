/** @odoo-module native */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
patch(PosStore.prototype, {
    // Override
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("MERCADO_PAGO_LATEST_MESSAGE", (payload) => {
            if (payload.config_id !== this.config.id) {
                return;
            }
            for (const line of this.models["pos.payment"].getAll()) {
                if (
                    line.payment_method_id?.use_payment_terminal === "mercado_pago" &&
                    line.uiState?.mercadoPagoIntentId &&
                    !line.isDone()
                ) {
                    line.payment_method_id.payment_terminal?.handleMercadoPagoWebhook(
                        line,
                    );
                }
            }
        });
    },
});
