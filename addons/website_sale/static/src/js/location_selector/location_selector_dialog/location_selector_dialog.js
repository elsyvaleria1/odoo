/** @odoo-module native */
import {
    LocationSelectorDialog,
    locationSelectorDialogProps,
} from "@delivery/js/location_selector/location_selector_dialog/location_selector_dialog";
import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

Object.assign(locationSelectorDialogProps, {
    orderId: t.number().optional(),
    isFrontend: t.boolean().optional(),
});

patch(LocationSelectorDialog.prototype, {
    setup() {
        super.setup(...arguments);

        if (this.props.isFrontend) {
            this.getLocationUrl = "/website_sale/get_pickup_locations";
        }
    },

    get title() {
        if (this.state.locations.length === 1) {
            return _t("Pickup Location");
        }
        return _t("Choose a pick-up point");
    },

    get validationButtonLabel() {
        return _t("Choose this location");
    },

    get postalCodePlaceholder() {
        return _t("Your postal code");
    },

    get listViewButtonLabel() {
        return _t("List view");
    },

    get mapViewButtonLabel() {
        return _t("Map view");
    },

    get errorMessage() {
        return _t("No result");
    },

    get loadingMessage() {
        return _t("Loading...");
    },
});
