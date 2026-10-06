/** @odoo-module native */
import { DocumentsActivityModel } from "@document/views/activity/document_activity_model";
import { patch } from "@web/core/utils/patch";

import { AccountIsViewablePatch } from "../document_model_mixin.js";

patch(DocumentsActivityModel.Record.prototype, AccountIsViewablePatch());
