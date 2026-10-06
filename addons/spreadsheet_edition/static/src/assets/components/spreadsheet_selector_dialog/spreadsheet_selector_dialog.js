/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Notebook } from "@web/components/notebook";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

import { SpreadsheetSelectorPanel } from "./spreadsheet_selector_panel.js";

const NAME_LABELS = {
    PIVOT: _t("Pivot name"),
    LIST: _t("List name"),
    LINK: _t("Link name"),
    GRAPH: _t("Graph name"),
};

/**
 * @typedef State
 * @property {string} [threshold]
 * @property {string} name
 * @property {boolean} confirmationIsPending
 */

export class SpreadsheetSelectorDialog extends Component {
    static template = "spreadsheet_edition.SpreadsheetSelectorDialog";
    static components = { Dialog, Notebook };
    static props = {
        actionOptions: t.object(),
        type: t.string(),
        threshold: t.number().optional(),
        maxThreshold: t.number().optional(),
        name: t.string(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        /** @type {State} */
        this.state = proxy({
            threshold: this.props.threshold,
            name: this.props.name,
            confirmationIsPending: false,
        });
        this.actionState = {
            getOpenSpreadsheetAction: () => {},
        };
        this.notification = useService("notification");
        this.actionService = useService("action");
        const orm = useService("orm");
        onWillStart(async () => {
            const spreadsheetModels = await orm.call(
                "mixin.spreadsheet",
                "get_selector_spreadsheet_models",
            );
            this.noteBookPages = spreadsheetModels.map(
                ({ model, display_name, allow_create }) => ({
                    Component: SpreadsheetSelectorPanel,
                    id: model,
                    title: display_name,
                    props: {
                        model,
                        displayBlank: allow_create,
                        onSpreadsheetSelected: this.onSpreadsheetSelected.bind(this),
                        onSpreadsheetDblClicked: this._onInsert.bind(this),
                    },
                }),
            );
        });
    }

    get nameLabel() {
        return NAME_LABELS[this.props.type];
    }

    get title() {
        return _t("Insert in Spreadsheet");
    }

    /**
     * @param {Object} param0
     * @param {Function} param0.getOpenSpreadsheetAction
     */
    onSpreadsheetSelected({ getOpenSpreadsheetAction }) {
        this.actionState = {
            getOpenSpreadsheetAction,
        };
    }

    async _onInsert() {
        if (this.state.confirmationIsPending) {
            return;
        }
        this.state.confirmationIsPending = true;
        const action = await this.actionState.getOpenSpreadsheetAction();
        if (!action) {
            this.state.confirmationIsPending = false;
            return;
        }
        const threshold = this.state.threshold ? parseInt(this.state.threshold, 10) : 0;
        const name = this.state.name.toString();

        // the action can be preceded by a notification
        const actionOpen = action;
        actionOpen.params = this._addToPreprocessingAction(
            actionOpen.params,
            threshold,
            name,
        );
        this.actionService.doAction(action);
        this.props.close();
    }

    _addToPreprocessingAction(actionParams, threshold, name) {
        return {
            ...this.props.actionOptions,
            preProcessingAsyncActionData: {
                ...this.props.actionOptions.preProcessingAsyncActionData,
                threshold,
                name,
            },
            preProcessingActionData: {
                ...this.props.actionOptions.preProcessingActionData,
                threshold,
                name,
            },
            ...actionParams,
        };
    }

    _onDiscard() {
        this.props.close();
    }
}
