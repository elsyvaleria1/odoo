/** @odoo-module native */
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { patch } from "@web/core/utils/patch";

patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        const res = super.fieldsStructure;
        res["mrp.production"].push("quality_check_todo");
        return res;
    },
});
