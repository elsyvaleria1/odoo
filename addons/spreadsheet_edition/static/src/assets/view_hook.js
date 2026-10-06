/** @odoo-module native */
import { useSearchModel } from "@web/core/search_model_hooks";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { omit } from "@web/core/utils/collections/objects";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useViewModel } from "@web/model/model";

import { SpreadsheetSelectorDialog } from "./components/spreadsheet_selector_dialog/spreadsheet_selector_dialog.js";

export function useInsertInSpreadsheet(getExportableFields) {
    const config = useViewConfig();
    const bus = useEventBus();
    const model = useViewModel();
    const searchModel = useSearchModel();
    useBus(bus, "insert-in-spreadsheet", async () => {
        _openSpreadsheetSelectorDialog();
    });
    const action = useService("action");
    const dialog = useService("dialog");
    const _getColumnsForSpreadsheet = () => {
        const fields = model.root.fields;
        const columns = getExportableFields();
        return columns
            .filter((col) => !["binary", "json"].includes(fields[col.name].type))
            .map((col) => {
                const field = fields[col.name];
                return { name: col.name, type: field.type, string: field.string };
            });
    };

    const _getListForSpreadsheet = async (name) => {
        const root = model.root;
        const { actionId } = config;
        const { xml_id } = actionId
            ? await action.loadAction(actionId, model.root.context)
            : {};
        const fields = root.fields;

        return {
            list: {
                model: root.resModel,
                domain: searchModel.domainString,
                orderBy: root.orderBy.filter((field) => fields[field.name]),
                context: omit(root.context, ...Object.keys(user.context)),
                columns: _getColumnsForSpreadsheet(),
                name,
                actionXmlId: xml_id,
            },
            fields,
        };
    };

    const _openSpreadsheetSelectorDialog = async () => {
        const root = model.root;
        const count = root.groups
            ? root.groups.reduce((acc, group) => group.count + acc, 0)
            : root.count;
        const selection = await root.getResIds(true);
        const threshold =
            selection.length > 0 ? selection.length : Math.min(count, root.limit);
        let name = config.getDisplayName();
        const sortBy = root.orderBy[0];
        if (sortBy && root.fields[sortBy.name]) {
            name = _t("%(field name)s by %(order)s", {
                "field name": name,
                order: root.fields[sortBy.name].string,
            });
        }
        const { list, fields } = await _getListForSpreadsheet(name);

        // if some records are selected, we replace the domain with a "id in [selection]" clause
        if (selection.length > 0) {
            list.domain = [["id", "in", selection]];
        }
        const actionOptions = {
            preProcessingAsyncAction: "insertList",
            preProcessingAsyncActionData: { list, threshold, fields },
        };

        const params = {
            threshold,
            type: "LIST",
            name,
            actionOptions,
        };
        dialog.add(SpreadsheetSelectorDialog, params);
    };

    return _openSpreadsheetSelectorDialog;
}
