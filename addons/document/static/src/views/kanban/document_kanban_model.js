/** @odoo-module native */
import { RelationalModel } from "@web/model/relational_model";

import { DocumentsModelMixin } from "../document_model_mixin.js";
import { DocumentsRecordMixin } from "../document_record_mixin.js";

export class DocumentsKanbanModel extends DocumentsModelMixin(RelationalModel) {}

export class DocumentsKanbanModelRecord extends DocumentsRecordMixin(
    RelationalModel.Record,
) {}
DocumentsKanbanModel.Record = DocumentsKanbanModelRecord;
