/** @odoo-module native */
import { Component, proxy, t, useListener, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
const log = makeLogger("pos.screen.ticket.search");
/**
 * @prop {{
 * config: {
 * searchFields: Map<string, string>,
 * filter: { show: boolean, options: Map<string, { text: string, indented: boolean? }> }
 * },
 * placeholder: string,
 * }}
 */
export class SearchBar extends Component {
    static template = "point_of_sale.SearchBar";
    static props = {
        config: t.object(),
        placeholder: t.string(),
        onSearch: t.function(),
        onFilterSelected: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.ui = useService("ui");
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
        useListener(window, "click", this._hideOptions.bind(this));
        this.filterOptionsList = [...this.props.config.filter.options.keys()];
        this.searchFieldsList = [...this.props.config.searchFields.keys()];
        const defaultSearchFieldId = this.searchFieldsList.indexOf(
            this.props.config.defaultSearchDetails.fieldName,
        );
        this.state = proxy({
            searchInput: this.props.config.defaultSearchDetails.searchTerm || "",
            selectedSearchFieldId:
                defaultSearchFieldId === -1 ? 0 : defaultSearchFieldId,
            showSearchFields: false,
            showFilterOptions: false,
            selectedFilter:
                this.props.config.defaultFilter || this.filterOptionsList[0],
        });
        useLayoutEffect(
            () => {
                this.state.selectedFilter =
                    this.props.config.defaultFilter || this.filterOptionsList[0];
            },
            () => [this.props.config.defaultFilter],
        );
    }
    _onSelectFilter(key) {
        log.logic("onSelectFilter", () => ({
            from: this.state.selectedFilter,
            to: key,
        }));
        this.state.selectedFilter = key;
        this.props.onFilterSelected(this.state.selectedFilter);
    }
    onSearchInputKeydown(event) {
        if (["ArrowUp", "ArrowDown"].includes(event.key)) {
            event.preventDefault();
        }
    }
    onSearchInputKeyup(event) {
        if (["ArrowUp", "ArrowDown"].includes(event.key)) {
            this.state.selectedSearchFieldId = this._fieldIdToSelect(event.key);
        } else if (event.key === "Enter" || this.state.searchInput === "") {
            this._onClickSearchField(
                this.searchFieldsList[this.state.selectedSearchFieldId],
            );
        } else {
            if (
                this.state.selectedSearchFieldId === -1 &&
                this.searchFieldsList.length
            ) {
                this.state.selectedSearchFieldId = 0;
            }
            this.state.showSearchFields = true;
        }
    }
    _onClickSearchField(fieldName) {
        this.state.showSearchFields = false;
        log.logic("onClickSearchField", () => ({
            fieldName,
            searchTerm: this.state.searchInput,
        }));
        this.props.onSearch({ fieldName, searchTerm: this.state.searchInput });
    }
    /**
     * @param {string} key
     */
    _fieldIdToSelect(key) {
        const length = this.searchFieldsList.length;
        if (!length) {
            return null;
        }
        if (this.state.selectedSearchFieldId === -1) {
            return 0;
        }
        const current = this.state.selectedSearchFieldId || length;
        return (current + (key === "ArrowDown" ? 1 : -1)) % length;
    }
    _hideOptions() {
        this.state.showFilterOptions = false;
        this.state.showSearchFields = false;
    }
}
