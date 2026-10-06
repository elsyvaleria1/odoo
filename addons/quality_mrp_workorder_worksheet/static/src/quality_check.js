/** @odoo-module native */
import { QualityCheck } from "@mrp_workorder/mrp_display/mrp_record_line/quality_check";
import { patch } from "@web/core/utils/patch";

patch(QualityCheck.prototype, {
    get icon() {
        return this.type === "worksheet" ? "fa-solid fa-file-lines" : super.icon;
    },
    get passFailTypes() {
        return [...super.passFailTypes, "worksheet"];
    },
    clicked() {
        return this.type === "worksheet"
            ? this.doActionAndNext("action_view_quality_check_wizard", "none")
            : super.clicked();
    },
});
