/** @odoo-module native */
import {
    LocationSelectorDialog,
    locationSelectorDialogProps,
} from "@delivery/js/location_selector/location_selector_dialog/location_selector_dialog";
import { t } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { patch } from "@web/core/utils/patch";

Object.assign(locationSelectorDialogProps, {
    productId: t.number().optional(),
    isProductPage: t.boolean().optional(),
});

patch(LocationSelectorDialog.prototype, {
    async _getLocations(zip) {
        if (this.props.isProductPage) {
            return rpc(this.getLocationUrl, {
                zip_code: zip,
                product_id: this.props.productId,
            });
        } else {
            return super._getLocations(...arguments);
        }
    },
});
