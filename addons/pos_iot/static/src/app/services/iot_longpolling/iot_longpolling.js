/** @odoo-module native */

import { IoTLongpolling, iotLongpollingService } from "@iot/network_utils/longpolling";
import { iotBoxDisconnectedDialog } from "@pos_iot/app/components/popups/iot_box_disconnected_dialog/iot_box_disconnected_dialog";
import { patch } from "@web/core/utils/patch";

patch(iotLongpollingService, {
    dependencies: ["dialog", ...iotLongpollingService.dependencies],
});
patch(IoTLongpolling.prototype, {
    setup({ dialog }) {
        super.setup(...arguments);
        this.dialog = dialog;
    },
    _doWarnFail(url) {
        this.dialog.add(iotBoxDisconnectedDialog, { url });
        const order = posmodel.getOrder();
        if (
            order &&
            order.getSelectedPaymentline() &&
            order.getSelectedPaymentline().payment_method_id.use_payment_terminal ===
                "worldline" &&
            ["waiting", "waitingCard", "waitingCancel"].includes(
                order.getSelectedPaymentline().payment_status,
            )
        ) {
            order.getSelectedPaymentline().setPaymentStatus("force_done");
        }
    },
});
