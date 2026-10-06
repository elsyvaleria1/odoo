/** @odoo-module native */
import { BankRecKanbanController } from "@account/components/bank_reconciliation/kanban_controller";
import { patch } from "@web/core/utils/patch";
import { makeActiveField } from "@web/model/relational_model";

patch(BankRecKanbanController.prototype, {
    get modelParams() {
        const params = super.modelParams;
        params.config.activeFields.line_ids.related.fields.payment_lines_ids = {
            name: "payment_lines_ids",
            type: "many2many",
        };
        params.config.activeFields.line_ids.related.activeFields.payment_lines_ids =
            makeActiveField();
        params.config.activeFields.line_ids.related.activeFields.payment_lines_ids.related =
            {
                fields: {
                    id: { name: "id", type: "int" },
                    display_name: { name: "display_name", type: "char" },
                    batch_payment_id: { name: "batch_payment_id", type: "many2one" },
                },
                activeFields: {
                    id: makeActiveField(),
                    display_name: makeActiveField(),
                    batch_payment_id: makeActiveField(),
                },
            };
        return params;
    },
});
