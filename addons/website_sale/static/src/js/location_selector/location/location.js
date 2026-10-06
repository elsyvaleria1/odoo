/** @odoo-module native */
import { Location } from "@delivery/js/location_selector/location/location";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(Location.prototype, {
    get openingHoursLabel() {
        return _t("Opening hours");
    },
});
