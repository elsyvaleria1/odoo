/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";

import { displayValues } from "../record_values.js";

export class FeaturesList extends Component {
    static template = "geoengine.FeaturesList";
    static props = {
        records: t.array().optional([]),
        onZoomToRecord: t.function().optional(() => () => {}),
        onZoomToRecords: t.function().optional(() => () => {}),
        displayField: t.string().optional("display_name"),
        groupByField: t.or([t.string(), t.literal(null)]).optional(null),
    };
    props = useProps(this.constructor.props);

    get ungroupedLabel() {
        return _t("Ungrouped");
    }

    setup() {
        this._groupCache = {
            records: null,
            searchTerm: null,
            groupByField: null,
            value: null,
        };
        this.state = proxy({
            searchTerm: "",
            isExpanded: true,
            selectedId: null,
            expandedStates: {},
        });
    }

    /**
     * @returns {Object}
     */
    get groupedRecords() {
        const cache = this._groupCache;
        if (
            cache.records === this.props.records &&
            cache.searchTerm === this.state.searchTerm &&
            cache.groupByField === this.props.groupByField
        ) {
            return cache.value;
        }

        const records = this.props.records || [];
        const searchTerm = this.state.searchTerm.toLowerCase().trim();

        let filteredRecords = records;
        if (searchTerm) {
            filteredRecords = records.filter((record) => {
                const name = this._getRecordName(record);
                const group = this._getRecordGroup(record);
                return (
                    name.toLowerCase().includes(searchTerm) ||
                    group.toLowerCase().includes(searchTerm)
                );
            });
        }

        const grouped = {};
        for (const record of filteredRecords) {
            const group = this._getRecordGroup(record) || this.ungroupedLabel;
            if (!grouped[group]) {
                grouped[group] = [];
            }
            grouped[group].push(record);
        }

        this._groupCache = {
            records: this.props.records,
            searchTerm: this.state.searchTerm,
            groupByField: this.props.groupByField,
            value: grouped,
        };
        return grouped;
    }

    /**
     * @returns {Array}
     */
    get sortedStates() {
        const grouped = this.groupedRecords;
        const ungrouped = this.ungroupedLabel;
        return Object.keys(grouped).sort((a, b) => {
            if (a === ungrouped) {
                return 1;
            }
            if (b === ungrouped) {
                return -1;
            }
            return a.localeCompare(b);
        });
    }

    /**
     * @param {string} state
     * @returns {Array}
     */
    getRecordsForState(state) {
        const grouped = this.groupedRecords;
        return grouped[state] || [];
    }

    /**
     * @param {string} state
     * @returns {number}
     */
    getStateCount(state) {
        return this.getRecordsForState(state).length;
    }

    /**
     * @returns {number}
     */
    get totalCount() {
        return (this.props.records || []).length;
    }

    /**
     * @returns {number}
     */
    get filteredCount() {
        const grouped = this.groupedRecords;
        let count = 0;
        for (const state of Object.keys(grouped)) {
            count += grouped[state].length;
        }
        return count;
    }

    /**
     * @param {string} state
     * @returns {boolean}
     */
    isStateExpanded(state) {
        return this.state.expandedStates[state] === true;
    }

    /**
     * @param {string} state
     */
    toggleState(state) {
        this.state.expandedStates[state] = !this.isStateExpanded(state);
    }

    _getRecordName(record) {
        const values = displayValues(record);
        return (
            values[this.props.displayField] ||
            values.name ||
            values.display_name ||
            `Record ${this._getRecordId(record)}`
        );
    }

    /**
     * @param {Object} record
     * @returns {string}
     */
    _getRecordGroup(record) {
        if (!this.props.groupByField) {
            return "";
        }
        const value = displayValues(record)[this.props.groupByField];
        if (!value) {
            return "";
        }
        if (Array.isArray(value)) {
            return value.length > 1 ? String(value[1]) : "";
        }
        if (typeof value === "object") {
            return String(value.display_name || value.name || "");
        }
        return String(value);
    }

    _getRecordId(record) {
        return record.resId || record.id;
    }

    onSearchInput(event) {
        this.state.searchTerm = event.target.value;
        if (this.state.searchTerm) {
            for (const state of this.sortedStates) {
                this.state.expandedStates[state] = true;
            }
        }
    }

    onClearSearch() {
        this.state.searchTerm = "";
    }

    onToggleExpand() {
        this.state.isExpanded = !this.state.isExpanded;
    }

    onFeatureSelect(record) {
        this.state.selectedId = this._getRecordId(record);

        this.props.onZoomToRecord(record);
    }

    isSelected(record) {
        return this._getRecordId(record) === this.state.selectedId;
    }

    onZoomToState(state, event) {
        event.stopPropagation();
        const records = this.getRecordsForState(state);
        if (records.length > 0) {
            this.props.onZoomToRecords(records);
        }
    }
}
