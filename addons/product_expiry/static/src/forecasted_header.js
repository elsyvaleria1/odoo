/** @odoo-module native */
import { ForecastedHeader } from "@stock/stock_forecasted/forecasted_header";
import { patch } from "@web/core/utils/patch";

patch(ForecastedHeader.prototype, {
    get to_remove_qty() {
        return Object.values(this.props.docs.product).reduce(
            (sum, p) => sum + (p.to_remove_qty || 0),
            0,
        );
    },
});
