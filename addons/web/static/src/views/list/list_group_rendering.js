// @ts-check
/** @odoo-module native */

import { getAggregateLayout } from "./list_group_layout.js";

export const listGroupRenderingMixin = {
    get canCreateGroup() {
        return this.groupOps.canCreateGroup();
    },

    /** @param {Object} group */
    async addInGroup(group) {
        const left = await this.props.list.leaveEditMode({ canAbandon: false });
        if (left) {
            group.addNewRecord({ position: this.props.editable });
        }
    },

    /** @param {Object} group */
    editGroupRecord(group) {
        const { resId, resModel } = group.record;
        this.actionService.doAction({
            context: { create: false },
            res_model: resModel,
            res_id: resId,
            type: "ir.actions.act_window",
            views: [[false, "form"]],
        });
    },

    /** @param {Object} group */
    getGroupConfigMenuProps(group) {
        return this.groupOps.getGroupConfigMenuProps(group);
    },

    /**
     * @param {Object} group
     * @param {Object} column
     */
    formatGroupAggregate(group, column) {
        return this.agg.formatGroupAggregate(group, column);
    },

    /** @param {Object} group */
    getGroupLevel(group) {
        return this.props.list.groupBy.length - group.list.groupBy.length - 1;
    },

    /**
     * @param {Object} group
     * @returns {import("./list_group_layout.js").AggregateLayout}
     */
    getGroupLayout(group) {
        return getAggregateLayout(
            /** @type {any} */ (this.columns),
            this.fields,
            group.aggregates,
            {
                hasSelectors: this.hasSelectors,
                hasOpenFormViewColumn: this.hasOpenFormViewColumn,
            },
        );
    },

    /** @param {Object} group */
    getGroupPagerProps(group) {
        const list = group.list;
        const total = list.isGrouped ? list.count : group.count;
        return {
            offset: list.offset,
            limit: list.limit,
            total,
            onUpdate: async ({ offset, limit }) => {
                if (await this.props.list.leaveEditMode()) {
                    await list.load({ limit, offset });
                }
            },
            withAccessKey: false,
        };
    },

    /** @param {Object} group */
    showGroupPager(group) {
        return !group.isFolded && group.list.limit < group.list.count;
    },

    /** @param {Object} group */
    showGroupConfigMenu(group) {
        return (
            group.value && ["many2one", "many2many"].includes(group.groupByField.type)
        );
    },

    /**
     * @param {PointerEvent} _ev
     * @param {Object} group
     */
    async onGroupHeaderClicked(_ev, group) {
        const left = await this.props.list.leaveEditMode();
        if (left) {
            this.toggleGroup(group);
        }
    },

    /** @param {string} value */
    addNewGroup(value) {
        this.state.showGroupInput = false;
        this.groupOps.createGroup(value);
    },
};
