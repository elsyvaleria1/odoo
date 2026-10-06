/** @odoo-module native */
import { endOf, serializeDate, today } from "@web/core/l10n/dates";
import { evaluateExpr } from "@web/core/py_js/py";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { KanbanRenderer } from "@web/views/kanban";

export class AccountReturnBaseKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup();
        this.orm = useService("orm");

        // Retrieve the allowed categories from xml arch
        const optionsArch = this.props.archInfo.xmlDoc.getAttribute("options");
        this.allowedCategories = ["account_return"];
        if (optionsArch) {
            const options = evaluateExpr(optionsArch);
            this.allowedCategories = options.allowed_categories;
        }

        useLayoutEffect(
            () => {
                this.runAllReturnChecks();
            },
            () => [],
        );
    }

    async runAllReturnChecks() {
        const additionalDomain = [
            ["date_from", "<=", serializeDate(endOf(today(), "month"))],
            ["return_type_category", "in", this.allowedCategories],
        ];

        const returnIds = await this.orm.call(
            "account.return",
            "get_next_returns_ids",
            [
                null,
                additionalDomain,
                true, //allow_multiple_by_types
            ],
        );

        await this.orm.call("account.return", "refresh_checks", [returnIds]);

        // reload records
        await this.props.list.model.load();
    }
}
