/** @odoo-module native */
import { markup, onWillStart, proxy } from "@odoo/owl";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { Record } from "@web/model/record";
import { useSearchModel } from "@web/search/search_model";
import { ListController, listView } from "@web/views/list";
import { compileViewTemplates } from "@web/views/view_compiler";

import { PayRunCard } from "../../components/payrun_card/payrun_card.js";
import { PayRunKanbanCompiler } from "../payslip_run_kanban/hr_payslip_run_kanban_compiler.js";
import { PayslipListRenderer } from "./hr_payslip_list_renderer.js";

export class PayslipListController extends ListController {
    static template = "hr_payroll.PayslipListView";
    static components = {
        ...ListController.components,
        PayRunCard,
        Record,
    };

    static KANBAN_CARD_ATTRIBUTE = "card";
    static KANBAN_MENU_ATTRIBUTE = "menu";

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.viewService = useService("view");
        this.notificationService = useService("notification");
        this.state = proxy({});
        this.revId = 0;
        const viewRegistry = registry.category("views");

        onWillStart(async () => {
            const resModel = "hr.payslip.run";
            const { relatedModels, views } = await this.viewService.loadViews({
                resModel: resModel,
                views: [[false, "kanban"]],
            });
            const { ArchParser } = viewRegistry.get("kanban");
            const archInfo = new ArchParser().parse(
                views["kanban"].ir,
                relatedModels,
                resModel,
            );
            const { templateDocs: templates } = archInfo;

            this.templates = compileViewTemplates(PayRunKanbanCompiler, templates);

            this.payRunArchInfo = archInfo;
            this.props.archInfo.fieldNodes = {
                ...this.props.archInfo.fieldNodes,
                ...archInfo.fieldNodes,
            };
        });

        this.headerButtonRules = {
            action_validate: (states) => states.includes("draft"),
            action_payslip_paid: (states) =>
                states.every((state) => ["validated", "paid"].includes(state)),
            action_payslip_draft: () => true,
        };
    }

    get payrunId() {
        return (
            this.searchModel.domain.find(
                ([field, operator]) => field === "payslip_run_id" && operator === "=",
            )?.[2] ?? null
        );
    }

    async onSelectionChanged() {
        await super.onSelectionChanged();
        let selection;
        if ((selection = await this.model.root.getResIds(true))) {
            this.state.selectionStates = await this.orm.read("hr.payslip", selection, [
                "state",
            ]);
        }
    }

    displaySelectionButton(button) {
        if (this.dialogContext.inDialog) {
            return false;
        }
        const tolerates = this.headerButtonRules[button.clickParams.name];
        if (!tolerates) {
            return true;
        }
        const states = this.state.selectionStates?.map((s) => s.state) ?? [];
        return states.length > 0 && tolerates(states);
    }

    createNewPayRun() {
        return this.actionService.doAction("hr_payroll.action_hr_payslip_run_create");
    }

    async selectEmployees() {
        const employeeListAction = await this.orm.call(
            "hr.payslip.run",
            "action_payroll_hr_version_list_view_payrun",
            [[this.payrunId]],
        );
        return this.actionService.doAction({
            ...employeeListAction,
            help: markup(employeeListAction.help),
            context: {
                active_id: this.payrunId,
            },
        });
    }

    async onReload() {
        return this.actionService.doAction({
            type: "ir.actions.client",
            tag: "soft_reload",
        });
    }

    async onClose() {
        return this.actionService.doAction({ type: "ir.actions.act_window_close" });
    }

    async addPayslips() {
        const slipIds = await this.model.root.getResIds(true);
        await this.orm.write("hr.payslip", slipIds, {
            payslip_run_id: this.model.config.context.active_id,
        });
        await this.model.root.load();
        this.notificationService.add(_t("The payslips(s) are now added to the batch"), {
            type: "success",
        });
        await this.onClose();
        await this.onReload();
    }

    get recordComponentProps() {
        return {
            resModel: "hr.payslip.run",
            resId: this.payrunId,
            fieldNames: Object.values(this.payRunArchInfo.fieldNodes).map(
                (f) => f.name,
            ),
            context: this.props.context,
            mode: "readonly",
        };
    }

    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name !== "unlink") {
            this.revId++;
        }
        return super.beforeExecuteActionButton(...arguments);
    }

    async afterExecuteActionButton(clickParams) {
        if (clickParams.name === "unlink") {
            const payrun = await this.orm.search("hr.payslip.run", [
                ["id", "=", this.payrunId],
            ]);
            if (!payrun.length) {
                this.config.historyBack();
            }
        }
        return super.afterExecuteActionButton(...arguments);
    }

    get actionMenuProps() {
        const res = super.actionMenuProps;
        const oldOnActionExecuted = res.onActionExecuted;
        res.onActionExecuted = (params) => {
            this.revId++;
            return oldOnActionExecuted?.(params);
        };
        return res;
    }

    onDeleteSelectedRecords() {
        super.onDeleteSelectedRecords();
        this.revId++;
    }
}

export const payslipListView = {
    ...listView,
    Renderer: PayslipListRenderer,
    Controller: PayslipListController,
    buttonTemplate: "hr_payroll.PayslipListView.Buttons",
};

registry.category("views").add("hr_payroll_payslip_list", payslipListView);
