// @ts-check
/** @odoo-module native */

import { proxy } from "@odoo/owl";
import { useFieldDirtyOwners } from "@web/views/view_hook";

/**
 * @param {{ bus: import("@odoo/owl").EventBus, root: Record<string, any> }} model
 * @returns {() => boolean}
 */
export function useFieldIsDirty(model) {
    const state = proxy({ fieldIsDirty: false });
    useFieldDirtyOwners(model, (fieldIsDirty) => {
        state.fieldIsDirty = fieldIsDirty;
    });
    return () => model.root.dirty || state.fieldIsDirty;
}
