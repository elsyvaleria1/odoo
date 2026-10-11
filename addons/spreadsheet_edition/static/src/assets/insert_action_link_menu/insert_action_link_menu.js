/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { SpreadsheetSelectorDialog } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_dialog";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";
import { useSearchModel } from "@web/search/search_model";

/**
 * Insert a link to a view in spreadsheet
 * @extends Component
 */
export class InsertViewSpreadsheet extends Component {
    static props = {};
    static template = "spreadsheet_edition.InsertActionSpreadsheet";
    static components = { CogMenuItem };
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.dialogManager = useService("dialog");
    }

    async linkInSpreadsheet() {
        const actionToLink = await this.getViewDescription();
        const actionOptions = {
            preProcessingAction: "insertLink",
            preProcessingActionData: actionToLink,
        };

        this.dialogManager.add(SpreadsheetSelectorDialog, {
            type: "LINK",
            actionOptions,
            name: this.config.getDisplayName(),
        });
    }

    async getViewDescription() {
        const { resModel } = this.searchModel;
        const { views = [], actionId, viewType } = this.config;
        const { xml_id } = actionId
            ? await this.actionService.loadAction(actionId, this.searchModel.context)
            : {};
        const { context } = this.searchModel.getIrFilterValues();
        const action = {
            xmlId: xml_id,
            domain: this.searchModel.domain,
            context,
            modelName: resModel,
            views: views.map(([, type]) => [false, type]),
        };
        return {
            viewType,
            action,
        };
    }
}
