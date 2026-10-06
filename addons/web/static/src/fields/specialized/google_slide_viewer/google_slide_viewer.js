// @ts-check
/** @odoo-module native */

import { _t } from "@web/core/translation";
import { registerField } from "@web/fields/_registry";
import { CharField, charField } from "@web/fields/basic/char/char_field";

/**
 * @param {string | false} value
 * @param {string | number} page
 */
export function getGoogleSlideUrl(value, page) {
    /** @type {string | false} */
    let url = false;
    const googleRegExp =
        /(^https:\/\/docs\.google\.com).*(\/d\/e\/|\/d\/)([A-Za-z0-9-_]+)/;
    const google = /** @type {string} */ (value).match(googleRegExp);
    if (google && google[3]) {
        url = `https://docs.google.com/presentation${google[2]}${google[3]}/preview?slide=${encodeURIComponent(page)}`;
    }
    return url;
}

export class GoogleSlideViewer extends CharField {
    static template = "web.GoogleSlideViewer";

    /** @returns {string | number} */
    get page() {
        return this.props.record.data[`${this.props.name}_page`] || 1;
    }

    get url() {
        const value = this.field.value;
        return value ? getGoogleSlideUrl(value, this.page) : false;
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
const googleSlideViewer = {
    ...charField,
    component: GoogleSlideViewer,
    displayName: _t("Google Slide Viewer"),
    fieldDependencies: ({ name }) => [
        { name: `${name}_page`, optional: true, readonly: true },
    ],
};

registerField("google_slide_viewer", googleSlideViewer);
