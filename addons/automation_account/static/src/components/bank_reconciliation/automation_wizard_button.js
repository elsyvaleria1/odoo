/** @odoo-module native */
import { BankRecButtonList } from "@account/components/bank_reconciliation/button_list/button_list";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(BankRecButtonList.prototype, {
    get buttons() {
        const buttons = super.buttons;
        const runtimeId = this.statementLineData.automation_runtime_id?.id;
        if (!runtimeId) {
            buttons.automation = {
                label: _t("Start Automation"),
                action: () => this.actionOpenAutomationWizard(),
                classes: "start-automation-btn",
            };
        } else {
            const isDone = this.statementLineData.automation_runtime_state === "done";
            buttons.automation = {
                label: isDone ? _t("View Automation Summary") : _t("View Automation"),
                action: () => this.actionOpenAutomationRuntime(runtimeId),
                classes: "view-automation-btn",
            };
        }
        return buttons;
    },

    async actionOpenAutomationRuntime(runtimeId) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "automation.runtime",
            res_id: runtimeId,
            views: [[false, "form"]],
            target: "current",
        });
    },

    async actionOpenAutomationWizard() {
        const stLineId = this.statementLineData.id;
        const context = {
            active_id: stLineId,
            active_model: "account.bank.statement.line",
            default_st_line_id: stLineId,
        };

        try {
            const approvals = await this.orm.searchRead(
                "approval.request",
                [["bank_statement_line_id", "=", stLineId]],
                ["telegram_data"],
                { limit: 1 },
            );
            const partnerCnId = approvals[0]?.telegram_data?.partner_cn_id;
            if (partnerCnId) {
                context.default_partner_id = partnerCnId;
            }
        } catch {}

        await this.action.doAction({
            name: _t("Create Automation Workflow"),
            type: "ir.actions.act_window",
            res_model: "wizard.account.bank.statement.line.start.automation",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context,
        });
    },
});
