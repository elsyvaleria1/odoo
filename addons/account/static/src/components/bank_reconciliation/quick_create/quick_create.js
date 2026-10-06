/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    KanbanQuickCreateController,
    KanbanRecordQuickCreate,
} from "@web/views/kanban";

export class BankRecQuickCreateController extends KanbanQuickCreateController {
    static template = "account.BankRecQuickCreateController";

    showFormDialogInError(e) {
        this.props.onCancel();
        throw e;
    }
}

export class BankRecQuickCreate extends KanbanRecordQuickCreate {
    static template = "account.BankRecQuickCreate";
    static props = {
        ...KanbanRecordQuickCreate.props,
        resModel: t.string(),
        context: t.object(),
        group: t.object().optional(),
    };
    static components = { BankRecQuickCreateController };

    async getQuickCreateProps(props) {
        await super.getQuickCreateProps({
            ...props,
            group: {
                resModel: props.resModel,
                context: props.context,
            },
        });
    }
}
