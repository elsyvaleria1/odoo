// @ts-check

import { after, onTimeZoneChange } from "@odoo/hoot";
import { dateSettings } from "@web/core/l10n/date_settings";
import { patch } from "@web/core/utils/patch";

onTimeZoneChange(() => {
    patchWithCleanup(dateSettings, { timeZone: Temporal.Now.timeZoneId() });
});

/** @type {typeof patch} */
export function patchWithCleanup(obj, patchValue) {
    const unpatch = patch(obj, patchValue);
    after(unpatch);
    return unpatch;
}

/**
 * @param {{ props: Record<string, any> }} ComponentClass
 * @param {Record<string, any>} defaults
 */
export function patchPropDefaults(ComponentClass, defaults) {
    /** @type {Record<string, any>} */
    const schema = {};
    for (const [key, value] of Object.entries(defaults)) {
        schema[key] = ComponentClass.props[key].optional(
            typeof value === "function" ? () => value : value,
        );
    }
    return patchWithCleanup(ComponentClass.props, schema);
}
