// @ts-check
/** @odoo-module native */

import { Component, computed, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SelectionBox extends Component {
    static components = {};
    static template = "web.SelectionBox";
    static props = { root: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.ui = useService("ui");
        this.computedSelection = computed(() => this.root.selection);
    }

    /**
     * @returns {import("@web/model/relational_model/dynamic_record_list").DynamicRecordList
     * & import("@web/model/relational_model/dynamic_group_list").DynamicGroupList}
     */
    get root() {
        return this.props.root;
    }
    /** @returns {number} */
    get nbSelected() {
        return this.selectedRecords.length;
    }
    /** @returns {number} */
    get nbTotal() {
        return /** @type {number} */ (
            this.root.isGrouped ? this.root.recordCount : this.root.count
        );
    }
    /** @returns {boolean} */
    get hasLimitedCount() {
        return /** @type {boolean} */ (this.root.hasLimitedCount);
    }
    /** @returns {boolean} */
    get isDomainSelected() {
        return this.root.isDomainSelected;
    }
    /** @returns {boolean} */
    get isPageSelected() {
        const nbSelected = this.nbSelected;
        return (
            nbSelected === this.root.records.length &&
            (!this.isRecordCountTrustable || this.nbTotal > nbSelected)
        );
    }
    /** @returns {boolean} */
    get isRecordCountTrustable() {
        return this.root.isRecordCountTrustable;
    }
    /** @returns {import("@web/model/relational_model/record").RelationalRecord[]} */
    get selectedRecords() {
        return this.computedSelection();
    }
    onUnselectAll() {
        this.selectedRecords.forEach((record) => {
            record.toggleSelection(false);
        });
        this.root.selectDomain(false);
    }
    onSelectDomain() {
        this.root.selectDomain(true);
    }
}
