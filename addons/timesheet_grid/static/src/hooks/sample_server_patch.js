/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { SampleServer } from "@web/model/sample_server";

patch(SampleServer.prototype, {
    _generateFieldValue(modelName, fieldName, id) {
        if (fieldName === "is_timer_running") {
            return false;
        }
        return super._generateFieldValue(...arguments);
    },
});
