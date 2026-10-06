/** @odoo-module native */
import { DocumentsKanbanController } from "@document/views/kanban/document_kanban_controller";
import { patch } from "@web/core/utils/patch";

import { DocumentsSpreadsheetControllerMixin } from "../document_spreadsheet_controller_mixin.js";

patch(DocumentsKanbanController.prototype, DocumentsSpreadsheetControllerMixin());
