/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { formatCurrency } from "@web/core/currency";
import { useBus, useService } from "@web/core/utils/hooks";
import { SIZES } from "@web/ui/viewport";
import { ViewButton } from "@web/views/view_button";

import { ProjectMilestone } from "./components/project_milestone.js";
import { ProjectProfitability } from "./components/project_profitability.js";
import { ProjectRightSidePanelSection } from "./components/project_right_side_panel_section.js";

export class ProjectRightSidePanel extends Component {
    static components = {
        ProjectRightSidePanelSection,
        ProjectMilestone,
        ViewButton,
        ProjectProfitability,
    };
    static template = "project.ProjectRightSidePanel";
    static props = { context: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.dialog = useService("dialog");
        useBus(this.ui.bus, "resize", this.updateGridTemplateColumns.bind(this));
        this.state = proxy({
            data: {
                milestones: {
                    data: [],
                },
                profitability_items: {
                    costs: { data: [], total: { billed: 0.0, to_bill: 0.0 } },
                    revenues: { data: [], total: { invoiced: 0.0, to_invoice: 0.0 } },
                },
                currency_id: false,
            },
            gridTemplateColumns: this._getGridTemplateColumns(),
        });

        onWillStart(() => this.loadData());
    }

    _getGridTemplateColumns() {
        switch (this.ui.size) {
            case SIZES.XS:
                return 2;
            case SIZES.SM:
                return 3;
            case SIZES.XXL:
                return 5;
            default:
                return 4;
        }
    }

    updateGridTemplateColumns() {
        this.state.gridTemplateColumns = this._getGridTemplateColumns();
    }

    get panelVisible() {
        return (
            this.state.data.show_milestones ||
            this.state.data.show_project_profitability_helper
        );
    }

    get context() {
        return this.props.context;
    }

    get projectId() {
        return this.context.active_id;
    }

    get currencyId() {
        return this.state.data.currency_id;
    }

    get showProjectProfitability() {
        const { costs, revenues } = this.state.data.profitability_items;
        return costs.data.length || revenues.data.length;
    }

    formatMonetary(value, options = {}) {
        return formatCurrency(value, this.currencyId, {
            digits: [false, 0],
            ...options,
        });
    }

    async loadData() {
        if (!this.projectId) {
            return {};
        }
        const data = await this.orm.call(
            "project.project",
            "get_panel_data",
            [[this.projectId]],
            { context: this.context },
        );
        this.state.data = data;
        return data;
    }

    async viewTasks() {
        this.actionService.doActionButton({
            type: "object",
            resId: this.projectId,
            name: "action_view_tasks_from_project_milestone",
            resModel: "project.project",
        });
    }

    async viewMilestones() {
        this.actionService.doActionButton({
            type: "object",
            resId: this.projectId,
            name: "action_get_list_view",
            resModel: "project.project",
        });
    }

    async onProjectActionClick(params) {
        this.actionService.doActionButton({
            type: "action",
            resId: this.projectId,
            context: this.context,
            resModel: "project.project",
            ...params,
        });
    }

    _getStatButtonClickParams(statButton) {
        return {
            type: statButton.action_type,
            name: statButton.action,
            context: statButton.additional_context || "{}",
        };
    }

    _getStatButtonRecordParams() {
        return {
            resId: this.projectId,
            context: this.context,
            resModel: "project.project",
        };
    }
}
