// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("web.search.bar.toggler");

class SearchBarToggler extends Component {
    static template = "web.SearchBar.Toggler";
    static props = {
        isSmall: t.boolean(),
        showSearchBar: t.boolean(),
        toggleSearchBar: t.function(),
    };
    props = useProps(this.constructor.props);
}

/** @returns {{ state: { isToggled: boolean, readonly isSmall: boolean, readonly showSearchBar: boolean }, component: typeof SearchBarToggler, props: Object }} */
export function useSearchBarToggler() {
    const ui = useService("ui");

    const state = proxy({
        isToggled: false,
        get isSmall() {
            return ui.isSmall;
        },
        get showSearchBar() {
            return !ui.isSmall || this.isToggled;
        },
    });

    function toggleSearchBar() {
        state.isToggled = !state.isToggled;
        log.logic("toggle", () => ({
            isSmall: ui.isSmall,
            isToggled: state.isToggled,
        }));
    }

    return {
        state,
        component: SearchBarToggler,
        get props() {
            return {
                isSmall: state.isSmall,
                showSearchBar: state.showSearchBar,
                toggleSearchBar,
            };
        },
    };
}
