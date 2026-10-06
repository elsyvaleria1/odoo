/** @odoo-module native */
import { OrderTabs } from "@point_of_sale/app/components/order_tabs/order_tabs";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/ui/dialog";

patch(OrderTabs.prototype, {
    newFloatingOrder() {
        if (this.pos.getOrder()?.tyroPaymentInProgress()) {
            this.dialog.add(AlertDialog, {
                title: _t("Payment in progress"),
                body: _t(
                    "Please complete or cancel the payment before navigatating away.",
                ),
            });
        } else {
            return super.newFloatingOrder(...arguments);
        }
    },
});
