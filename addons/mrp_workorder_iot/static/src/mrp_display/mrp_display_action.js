/** @odoo-module native */
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";
import { patch } from "@web/core/utils/patch";

patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        const result = super.fieldsStructure;
        result["quality.check"].push("ip");
        result["quality.check"].push("identifier");
        result["quality.check"].push("iot_box_id");
        result["quality.check"].push("boxes");
        return result;
    },
});
