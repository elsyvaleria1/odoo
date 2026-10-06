/** @odoo-module native */
import { PosCategory } from "@point_of_sale/app/models/pos_category";
import { patch } from "@web/core/utils/patch";

patch(PosCategory.prototype, {
    get states() {
        // pos.prep.state is only loaded in a preparation-display context; guard so
        // this patch (pulled into the shared POS unit-test bundle) does not crash
        // community POS tests that never load prep-display data.
        return (
            this.models["pos.prep.state"]?.filter((state) =>
                state.categories.some((categ) => categ.id === this.id),
            ) ?? []
        );
    },
});
