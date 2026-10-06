/** @odoo-module native */
import { proxy, t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KanbanController, KanbanRenderer, kanbanView } from "@web/views/kanban";

export class BankRecReconcileDialogKanbanController extends KanbanController {
    static template = "account.BankRecReconcileDialogKanbanView";
    static props = { ...KanbanController.props, bankRecInfo: t.object().optional() };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    async onSelectionChanged() {
        this.props.bankRecInfo.onSelectionChanged(this);
    }
}

export class BankRecReconcileDialogKanbanRenderer extends KanbanRenderer {
    static template = "account.BankRecReconcileDialogKanbanRenderer";
    static props = { ...KanbanRenderer.props, bankRecInfo: t.any().optional() };

    setup() {
        super.setup();
        this.ui = useService("ui");
        if (this.props.bankRecInfo?.state) {
            this.bankRecState = proxy(this.props.bankRecInfo.state);
        }
    }
}

export const bankRecReconcileDialogKanbanRenderer = {
    ...kanbanView,
    Renderer: BankRecReconcileDialogKanbanRenderer,
    Controller: BankRecReconcileDialogKanbanController,
    props: (genericProps, view) => {
        const baseProps = kanbanView.props(genericProps, view);
        return {
            ...baseProps,
            bankRecInfo: genericProps.bankRecInfo,
        };
    },
};

registry
    .category("views")
    .add("bank_rec_dialog_kanban", bankRecReconcileDialogKanbanRenderer);
