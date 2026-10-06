// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { highlightText } from "@web/core/utils/dom/html";
import { useSettingsSearchContext } from "@web/views/settings/settings_search_context";
export class HighlightText extends Component {
    static template = "web.HighlightText";
    static props = { originalText: t.string() };
    props = useProps(this.constructor.props);
    /** @type {any} */
    searchState;

    setup() {
        this.settingsContext = useSettingsSearchContext();
        /** @type {{ value: string }} */
        this.searchState = proxy(this.settingsContext.searchState);
    }

    /** @returns {string | import("@odoo/owl").Markup} */
    get text() {
        return highlightText(
            this.searchState.value,
            this.props.originalText,
            "highlighter",
        );
    }
}
