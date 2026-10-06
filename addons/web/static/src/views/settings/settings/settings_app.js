// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useSettingsSearchContext } from "@web/views/settings/settings_search_context";

export class SettingsApp extends Component {
    static template = "web.SettingsApp";
    static props = {
        string: t.string(),
        imgurl: t.string(),
        key: t.string(),
        selectedTab: t.string().optional(),
        slots: t.object(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.settingsContext = useSettingsSearchContext();
        /** @type {{ search: { value: string } }} */
        this.state = proxy({
            search: this.settingsContext.searchState,
        });
        this.settingsAppRef = elementRef();
        useLayoutEffect(
            () => {
                if (this.settingsAppRef.el) {
                    const force =
                        this.state.search.value &&
                        !this.settingsAppRef.el.querySelector(
                            ".o_settings_container:not(.d-none)",
                        ) &&
                        !this.settingsAppRef.el.querySelector(
                            ".o_setting_box.o_searchable_setting",
                        );
                    this.settingsAppRef.el.classList.toggle("d-none", force);
                }
            },
            () => [this.state.search.value],
        );
    }
}
