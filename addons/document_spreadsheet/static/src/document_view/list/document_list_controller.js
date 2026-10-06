/** @odoo-module native */
import { DocumentsListController } from "@document/views/list/document_list_controller";
import { patch } from "@web/core/utils/patch";

import { DocumentsSpreadsheetControllerMixin } from "../document_spreadsheet_controller_mixin.js";

patch(DocumentsListController.prototype, DocumentsSpreadsheetControllerMixin());
