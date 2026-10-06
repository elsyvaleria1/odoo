/** @odoo-module native */
import { PosConfig } from "@point_of_sale/app/models/pos_config";
import { patch } from "@web/core/utils/patch";

patch(PosConfig.prototype, {
    get preparationCategories() {
        let set = super.preparationCategories;
        if (this.preparationDisplayCategories.size > 0) {
            set = new Set([...set, ...this.preparationDisplayCategories]);
        }
        return set;
    },

    get preparationDisplayCategories() {
        // pos.prep.display is only part of the loaded data when a preparation
        // display is in play. When it is absent (e.g. the shared POS unit-test
        // bundle, which pulls in this patch without loading prep-display data)
        // there are simply no preparation-display categories.
        const prepDisplays = this.models["pos.prep.display"];
        if (!prepDisplays) {
            return new Set();
        }
        return new Set(
            prepDisplays.flatMap((prepDisplay) =>
                prepDisplay.raw.category_ids.length > 0
                    ? prepDisplay.category_ids.flatMap((cat) => cat.id)
                    : this.models["pos.category"].flatMap((cat) => cat.id),
            ),
        );
    },

    get displayTrackingNumber() {
        return (
            super.displayTrackingNumber ||
            this.models["pos.prep.display"]?.length ||
            this.models["pos.printer"].length
        );
    },
});
