/** @odoo-module native */
import { LocationSchedule } from "@delivery/js/location_selector/location_schedule/location_schedule";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(LocationSchedule.prototype, {
    get closedLabel() {
        return _t("Closed");
    },
});
