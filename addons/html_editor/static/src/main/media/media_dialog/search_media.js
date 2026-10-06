/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useDebounced } from "@web/core/utils/timing";

export class SearchMedia extends Component {
    static template = "html_editor.SearchMedia";
    static props = { searchPlaceholder: t.any(), search: t.any(), needle: t.any() };
    props = useProps(this.constructor.props);
    setup() {
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef, mobile: true });
        this.debouncedSearch = useDebounced(this.props.search, 1000);

        this.state = proxy({
            input: this.props.needle || "",
        });

        useLayoutEffect(
            (input) => {
                if (this.hasRendered) {
                    this.debouncedSearch(input);
                } else {
                    this.hasRendered = true;
                }
            },
            () => [this.state.input],
        );
    }
}
