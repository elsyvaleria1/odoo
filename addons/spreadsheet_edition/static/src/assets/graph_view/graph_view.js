/** @odoo-module native */
import { SpreadsheetSelectorDialog } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_dialog";
import { user } from "@web/core/user";
import { omit } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useSearchModel } from "@web/search/search_model";
import { session } from "@web/session";
import { GraphRenderer } from "@web/views/graph";

patch(GraphRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.menu = useService("menu");
        this.canInsertChart = session.can_insert_in_spreadsheet;
    },

    async onInsertInSpreadsheet() {
        const { actionId } = this.config;
        const { xml_id } = actionId
            ? await this.actionService.loadAction(actionId, this.searchModel.context)
            : {};
        const actionOptions = {
            preProcessingAsyncAction: "insertChart",
            preProcessingAsyncActionData: {
                metaData: {
                    ...this.model.metaData,
                    axisType: this.chart.scales.x?.type,
                },
                searchParams: {
                    ...this.model.searchParams,
                    domain: this.searchModel.domainString,
                    context: omit(
                        this.model.searchParams.context,
                        ...Object.keys(user.context),
                        "graph_measure",
                        "graph_order",
                    ),
                },
                actionXmlId: xml_id,
            },
        };
        const params = {
            type: "GRAPH",
            name: this.model.metaData.title,
            actionOptions,
        };
        this.dialog.add(SpreadsheetSelectorDialog, params);
    },
});
