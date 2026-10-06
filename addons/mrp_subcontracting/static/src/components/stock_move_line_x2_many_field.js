/** @odoo-module native */
import { SMLX2ManyField } from "@stock/fields/stock_move_line_x2_many_field";
import { patch } from "@web/core/utils/patch";

patch(SMLX2ManyField.prototype, {
    get quantListViewShowOnHandOnly() {
        return this.props.context.mrp_subcontracting
            ? false
            : super.quantListViewShowOnHandOnly;
    },
});
