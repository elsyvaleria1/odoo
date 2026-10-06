/** @odoo-module native */
import { DocumentsActivityController } from "@document/views/activity/document_activity_controller";
import { patch } from "@web/core/utils/patch";

import { DocumentsSpreadsheetControllerMixin } from "../document_spreadsheet_controller_mixin.js";

patch(DocumentsActivityController.prototype, DocumentsSpreadsheetControllerMixin());
