/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { elementRef } from "@web/core/utils/element_ref";

const log = makeLogger("website.backend.hierarchy_navbar");

export class HierarchyNavbar extends Component {
    static template = "website.hierarchy_navbar";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = {
        toggleInactive: t.function(),
        websites: t.object(),
        selectWebsite: t.function(),
        searchView: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.searchInput = elementRef();
        this.websiteNamesState = proxy(Array.from(this.props.websites.names));
    }

    get websiteNames() {
        return this.websiteNamesState.map((websiteName) => ({
            label: websiteName,
            onSelected: () => this.props.selectWebsite(websiteName),
        }));
    }

    /**
     * @param {Event} event
     */
    onInputKeydown(event) {
        if (event.key === "Enter" || event.key === "Tab") {
            log.logic("onInputKeydown: search", () => ({
                key: event.key,
                keyword: event.target.value,
                forward: !event.shiftKey,
            }));
            event.preventDefault();
            this.props.searchView(event.target.value, !event.shiftKey);
        }
    }

    /**
     * @param {Event} event
     */
    onInputClick(event) {
        log.logic("onInputClick: search", () => ({ forward: !event.shiftKey }));
        this.props.searchView(this.searchInput.el.value, !event.shiftKey);
    }
}
