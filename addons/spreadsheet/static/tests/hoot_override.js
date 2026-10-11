import { __debug__ } from "@odoo/hoot";
import { stores } from "@odoo/o-spreadsheet";
import { patch } from "@web/core/utils/patch";

const { RendererStore } = stores;

patch(RendererStore.prototype, {
    drawLayer(ctx, layer) {
        if (__debug__.debug) {
            return super.drawLayer(ctx, layer);
        }
    },
});
