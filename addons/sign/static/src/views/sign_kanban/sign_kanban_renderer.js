/** @odoo-module native */
import { SignActionHelper } from "@sign/views/helper/sign_action_helper";
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer } from "@web/views/kanban";

import { SignDocumentDropZone } from "../../mixin/document_upload.js";

export class SignKanbanRenderer extends SignDocumentDropZone(KanbanRenderer) {
    static template = "sign.KanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        SignActionHelper,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    /** @override */
    get canMoveRecords() {
        return super.canMoveRecords && this.props.list.resModel !== "sign.request";
    }

    /** @override */
    get canResequenceGroups() {
        return super.canResequenceGroups && this.props.list.resModel !== "sign.request";
    }
}
