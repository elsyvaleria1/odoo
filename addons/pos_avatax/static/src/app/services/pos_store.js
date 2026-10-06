/** @odoo-module native */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/ui/dialog";

patch(PosStore.prototype, {
    async getAvataxTaxesRpc() {
        if (!this.config.module_pos_avatax) {
            return;
        }

        try {
            const order = this.getOrder();
            if (this.ui.isBlocked || !order.partner_id) {
                return;
            } else {
                this.ui.block({ message: _t("Updating Avatax taxes...") });
            }

            const serialized = order.serializeForORM();
            const data = await this.data.call("pos.order", "get_order_tax_details", [
                [serialized],
            ]);
            const modelToAdd = {};
            for (const [model, records] of Object.entries(data)) {
                const modelKey = this.data.opts.databaseTable[model]?.key;

                if (!modelKey) {
                    modelToAdd[model] = records;
                    continue;
                }
            }

            this.models.connectNewData(modelToAdd);
        } catch {
            this.dialog.add(AlertDialog, {
                title: _t("Error while loading Avatax taxes"),
                body: _t(
                    "Enable to load Avatax taxes, please verify partner information and Avatax API configuration.",
                ),
            });
        } finally {
            this.ui.unblock();
        }
    },
    async selectPartner() {
        const res = await super.selectPartner(...arguments);
        if (res) {
            await this.getAvataxTaxesRpc();
        }
        return res;
    },
});
