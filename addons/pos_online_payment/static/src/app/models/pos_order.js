/** @odoo-module native */
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";
patch(PosOrder.prototype, {
    serializeForORM(opts) {
        const onlinePaymentUUIDs = this.payment_ids
            .filter(
                (payment) =>
                    !payment.isSynced && payment.payment_method_id?.is_online_payment,
            )
            .map((payment) => payment.uuid);

        const serialized = super.serializeForORM(opts);
        if (onlinePaymentUUIDs.length > 0) {
            serialized.payment_ids = serialized.payment_ids?.filter(
                (p) => !onlinePaymentUUIDs.includes(p.at(-1).uuid),
            );
        }
        return serialized;
    },
});
