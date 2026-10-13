/** @odoo-module native */
import { Component, onMounted, onWillDestroy, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class ControlPanelButtons extends Component {
    static template = "mrp_workorder.ControlPanelButtons";
    static components = { Dropdown, DropdownItem };
    static props = {
        activeWorkcenter: t.or([t.boolean(), t.number()]),
        productionCount: t.number(),
        selectWorkcenter: t.function(),
        toggleWorkcenter: t.function(),
        workcenters: t.array(),
        workorders: t.array(),
        relevantCount: t.number(),
        adminWorkorders: t.array(),
        hideNewWorkcenterButton: t.boolean(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ overflowFrom: null });
        this.workcentersContainer = elementRef();
        this.workcenters = elementRef();
        this.trailingControls = elementRef();
        this.ui = useService("ui");

        /** @type {Map<string, number>} */
        this.buttonWidths = new Map();

        const resizeObserver = new ResizeObserver(() => this.updateOverflow());
        onMounted(() => {
            resizeObserver.observe(this.workcentersContainer.el);
            if (this.ui.isSmall) {
                return;
            }
            this.measureButtons();
            this.updateOverflow();
        });
        onWillDestroy(() => resizeObserver.disconnect());

        useLayoutEffect(
            () => {
                if (!this.ui.isSmall) {
                    this.measureButtons();
                    this.updateOverflow();
                }
            },
            () => [this.workcenterButtons.length],
        );
    }

    get workcenterButtons() {
        const workcenterButtons = {};
        let productionCount = this.props.productionCount;
        let adminCount = 0;
        for (const { id, display_name } of this.props.workcenters) {
            workcenterButtons[id] = { count: 0, name: display_name };
        }
        for (const workorder of this.props.workorders) {
            if (workorder.data.state === "cancel") {
                continue;
            }
            const button = workcenterButtons[workorder.data.workcenter_id.id];
            if (button) {
                button.count++;
            }
            if (this.props.adminWorkorders.includes(workorder.resId)) {
                adminCount++;
            }
        }
        if (
            this.props.activeWorkcenter > 0 &&
            workcenterButtons[this.props.activeWorkcenter]
        ) {
            workcenterButtons[this.props.activeWorkcenter].count =
                this.props.relevantCount;
        } else if (this.props.activeWorkcenter === 0) {
            productionCount = this.props.relevantCount;
        } else if (this.props.activeWorkcenter === -1) {
            adminCount = this.props.relevantCount;
        }
        if (workcenterButtons[0]) {
            workcenterButtons[0].count = productionCount;
        }
        if (workcenterButtons[-1]) {
            workcenterButtons[-1].count = adminCount;
        }
        return this.props.workcenters.map((wc) => [
            String(wc.id),
            workcenterButtons[wc.id],
        ]);
    }

    /**
     * @param {number} index
     * @returns {boolean}
     */
    isInline(index) {
        return this.state.overflowFrom === null || index < this.state.overflowFrom;
    }

    measureButtons() {
        const list = this.workcenters.el;
        if (!list) {
            return;
        }
        for (const el of list.querySelectorAll(".o_work_center_btn")) {
            const width = /** @type {HTMLElement} */ (el).offsetWidth;
            if (width > 0) {
                this.buttonWidths.set(
                    /** @type {HTMLElement} */ (el).dataset.workcenterId,
                    width,
                );
            }
        }
    }

    updateOverflow() {
        const container = this.workcentersContainer.el;
        if (!container) {
            return;
        }
        const buttons = this.workcenterButtons;
        const widthOf = (/** @type {string} */ id) => this.buttonWidths.get(id) ?? 0;
        const available = container.offsetWidth;

        if (buttons.reduce((sum, [id]) => sum + widthOf(id), 0) <= available) {
            this.state.overflowFrom = null;
            return;
        }
        const budget = available - (this.trailingControls.el?.offsetWidth ?? 0);
        let used = 0;
        for (const [index, [id]] of buttons.entries()) {
            used += widthOf(id);
            if (used > budget) {
                this.state.overflowFrom = index;
                return;
            }
        }
        this.state.overflowFrom = null;
    }
}
