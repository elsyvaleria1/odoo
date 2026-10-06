// @ts-check
/** @odoo-module native */

/** @import { Group } from "@web/model/relational_model/group" */
/** @typedef {ReturnType<typeof import("@web/views/kanban/progress_bar_hook").useProgressBar>} ProgressBarState */
/**
 * @typedef RottingProgressBarPatch
 * @property {Record<string | number, Group>} rotIsFiltered
 * @property {(group: Group) => Promise<void>} toggleFilterRotten
 * @property {(group: Group) => Promise<void>} setFilterRotten
 * @property {(group: Group) => Promise<void>} unsetFilterRotten
 */

/** @returns {RottingProgressBarPatch & Partial<ProgressBarState> & ThisType<ProgressBarState & RottingProgressBarPatch>} */
export function rottingProgressBarPatch() {
    return {
        rotIsFiltered: {},
        /** @param {Group} group */
        async toggleFilterRotten(group) {
            if (!this.rotIsFiltered[group.id]) {
                await this.setFilterRotten(group);
            } else {
                await this.unsetFilterRotten(group);
            }
            group.model.notify();
        },
        /** @param {Group} group */
        async setFilterRotten(group) {
            await group.applyFilter([["is_rotting", "=", true]]);
            this.rotIsFiltered[group.id] = group;
            if (this.activeBars[group.serverValue]) {
                delete this.activeBars[group.serverValue];
            }
        },
        /** @param {Group} group */
        async unsetFilterRotten(group) {
            await group.applyFilter(undefined);
            delete this.rotIsFiltered[group.id];
        },
        /**
         * @param {string|number} groupId
         * @param {Object} bar
         */
        async selectBar(groupId, bar) {
            if (this.rotIsFiltered[groupId]) {
                delete this.rotIsFiltered[groupId];
            }
            return super.selectBar(groupId, bar);
        },
        /**
         * @param {Group} group
         * @returns {number}
         */
        getGroupCount(group) {
            if (this.rotIsFiltered[group.id]) {
                return group.list.records.filter((record) => record.data.is_rotting)
                    .length;
            }
            return super.getGroupCount(group);
        },
    };
}
