/** @odoo-module native */
import { provideApprovalContext } from "@approval/views/approval_context";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";

import { trace } from "../../common/approval_trace.js";

/**
 * Tells the view's buttons which of its models carry approval bindings, so a
 * button of a list row, a kanban card or a list header is gated as a form's is:
 * a window action has nothing on the server to refuse it.
 */
function provideGatedModels(props) {
    const approvalGatedModels = {};
    for (const [model, info] of Object.entries(props.relatedModels || {})) {
        approvalGatedModels[model] = Boolean(info.has_approval_bindings);
    }
    if (trace.on("button")) {
        trace.event("button", "gated_models", {
            model: props.resModel,
            related: Object.keys(approvalGatedModels).length,
            gated: Object.keys(approvalGatedModels).filter(
                (model) => approvalGatedModels[model],
            ),
        });
    }
    provideApprovalContext({ approvalGatedModels });
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        provideGatedModels(this.props);
    },
});

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        provideGatedModels(this.props);
    },
});

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        provideGatedModels(this.props);
    },
});
