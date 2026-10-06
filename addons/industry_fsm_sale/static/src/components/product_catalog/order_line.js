/** @odoo-module native */
import { useFsmContext } from "@industry_fsm_sale/fsm_context";
import { onWillStart } from "@odoo/owl";
import { ProductCatalogOrderLine } from "@product/product_catalog/order_line/order_line";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(ProductCatalogOrderLine.prototype, {
    setup() {
        super.setup();
        this.fsmContext = useFsmContext();
        this.orm = useService("orm");
        this.isSalesman = true;
        onWillStart(async () => {
            if (this.fsmContext.fsm_task_id) {
                this.isSalesman = await user.hasGroup("sale.group_sale_salesman");
            }
        });
    },

    get showPrice() {
        let showPrice = super.showPrice;
        if (this.fsmContext.fsm_task_id) {
            showPrice = showPrice && this.isSalesman;
        }
        return showPrice;
    },
});
