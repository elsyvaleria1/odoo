/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { isCurrentFocusEditable } from "@voip/utils/utils";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class SearchBar extends Component {
    static template = "voip.SearchBar";
    static props = {
        state: t.object(),
        onInputSearch: t.function(),
        onClickBack: t.function().optional(),
        slots: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.voip = useService("voip");
        this.softphone = this.voip.softphone;
        this.searchInput = elementRef();
        useLayoutEffect(
            (shouldFocus) => {
                if (shouldFocus) {
                    if (
                        this.searchInput.el &&
                        !this.voip.error &&
                        this.softphone.mayTakeFocus(isCurrentFocusEditable())
                    ) {
                        this.searchInput.el.focus();
                        this.softphone.focusGranted = false;
                    }
                    this.softphone.shouldFocus = false;
                }
            },
            () => [this.softphone.shouldFocus],
        );
    }

    /**
     * When an RPC is pending, the search icon is replaced with a spinner.
     *
     * @returns {string}
     */
    get searchBarIcon() {
        if (this.voip.hasPendingRequest) {
            return "fa-solid fa-circle-notch fa-spin";
        }
        return "oi oi-search";
    }
}
