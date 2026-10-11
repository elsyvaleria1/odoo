/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { FilterValue } from "@spreadsheet/global_filters/components/filter_value/filter_value";
import {
    getDefaultValue,
    getEmptyFilterValue,
    getFilterTypeOperators,
} from "@spreadsheet/global_filters/helpers";
import { _t } from "@web/core/translation";
import { getOperatorLabel } from "@web/core/tree";
import { deepEqual } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";

import { isEmptyFilterValue } from "../../helpers.js";

export class FilterValuesList extends Component {
    static template = "spreadsheet_dashboard.FilterValuesList";
    static components = { FilterValue };

    static props = {
        close: t.function(),
        model: t.object(),
        openFiltersEditor: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.state = proxy({
            filtersAndValues: this.globalFilters.map((globalFilter) => {
                const value = this.props.model.getters.getGlobalFilterValue(
                    globalFilter.id,
                );
                return {
                    globalFilter,
                    value: value ? { ...value } : getDefaultValue(globalFilter.type),
                };
            }),
        });
        onWillStart(async () => {
            this.searchableParentRelations = await this.fetchSearchableParentRelation();
        });
    }

    get globalFilters() {
        return this.props.model.getters.getGlobalFilters();
    }

    setGlobalFilterValue(node, value) {
        if (value == null && node.globalFilter.type !== "date") {
            node.value = {
                ...node.value,
                ...getEmptyFilterValue(node.globalFilter, node.value.operator),
            };
        } else {
            node.value = value;
        }
    }

    getTranslatedFilterLabel(filter) {
        return _t(filter.label);
    }

    getOperators(filter) {
        const operators = getFilterTypeOperators(filter.type);
        if (
            filter.type === "relation" &&
            !this.searchableParentRelations[filter.modelName]
        ) {
            return operators.filter((op) => op !== "child_of");
        }
        return filter.type === "boolean" ? [undefined, ...operators] : operators;
    }

    filterHasClearButton(node) {
        return !isEmptyFilterValue(node.globalFilter, node.value);
    }

    getOperatorLabel(operator) {
        return operator ? getOperatorLabel(operator) : "";
    }

    updateOperator(node, operator) {
        if (!operator) {
            node.value = undefined;
            return;
        }
        if (!node.value) {
            node.value = {};
        }
        node.value.operator = operator;
        const defaultValue = getEmptyFilterValue(node.globalFilter, operator);
        for (const key of Object.keys(defaultValue ?? {})) {
            if (!(key in node.value)) {
                node.value[key] = defaultValue[key];
            }
        }
    }

    clearFilter(filterId) {
        const node = this.state.filtersAndValues.find(
            (node) => node.globalFilter.id === filterId,
        );
        if (node && node.value) {
            const emptyValue = getEmptyFilterValue(
                node.globalFilter,
                node.value.operator,
            );
            node.value =
                typeof emptyValue === "object"
                    ? { ...emptyValue, operator: node.value.operator }
                    : emptyValue;
        }
    }

    onConfirm() {
        for (const node of this.state.filtersAndValues) {
            const { globalFilter, value } = node;
            const originalValue = this.props.model.getters.getGlobalFilterValue(
                globalFilter.id,
            );

            if (deepEqual(originalValue, value)) {
                continue;
            }
            this.props.model.dispatch("SET_GLOBAL_FILTER_VALUE", {
                id: globalFilter.id,
                value: isEmptyFilterValue(globalFilter, value) ? undefined : value,
            });
        }
        this.props.close();
    }

    onDiscard() {
        this.props.close();
    }

    fetchSearchableParentRelation() {
        const models = this.globalFilters
            .filter((filter) => filter.type === "relation")
            .map((filter) => filter.modelName);
        return this.orm
            .cache({ type: "disk" })
            .call("ir.model", "get_parent_searchability", [models]);
    }
}
