/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ReportController } from "@web/views/report_controller";

export class CohortController extends ReportController {
    static template = "web_cohort.CohortView";

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.actionService = useService("action");
    }

    /** @override */
    get modelOptions() {
        return {};
    }

    getContext() {
        const { measure, interval } = this.model.metaData;
        return { cohort_measure: measure, cohort_interval: interval };
    }

    /**
     * @param {Object} row
     */
    onRowClicked(row, newWindow) {
        if (row.value === undefined || this.model.metaData.disableLinking) {
            return;
        }

        const context = Object.assign({}, this.model.searchParams.context);
        const domain = row.domain;
        const views = {};
        for (const [viewId, viewType] of this.config.views || []) {
            views[viewType] = viewId;
        }
        function getView(viewType) {
            return [
                context[`${viewType}_view_id`] || views[viewType] || false,
                viewType,
            ];
        }
        const actionViews = [getView("list"), getView("form")];
        this.openView(domain, actionViews, context, newWindow);
    }

    openView(domain, views, context, newWindow) {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                name: this.model.metaData.title,
                res_model: this.model.metaData.resModel,
                views,
                view_mode: "list",
                target: "current",
                context,
                domain,
            },
            { newWindow },
        );
    }
}
