/** @odoo-module native */
import { DocumentsKanbanController } from "@document/views/kanban/document_kanban_controller";
import { patch } from "@web/core/utils/patch";

import { AiDocumentsControllerMixin } from "../document_controller_mixin.js";

patch(DocumentsKanbanController.prototype, AiDocumentsControllerMixin());
