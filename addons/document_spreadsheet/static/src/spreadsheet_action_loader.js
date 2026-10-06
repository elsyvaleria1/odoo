/** @odoo-module native */
import { addSpreadsheetActionLazyLoader } from "@spreadsheet/assets_backend/spreadsheet_action_loader";
import { _t } from "@web/core/translation";

addSpreadsheetActionLazyLoader(
    "action_view_spreadsheet",
    "spreadsheet",
    _t("Spreadsheet"),
);
addSpreadsheetActionLazyLoader("action_view_template");
