/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController, listView } from "@web/views/list";

export class VersionPayrunListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = proxy({
            disabled: false,
        });
    }

    async onReload() {
        return this.actionService.doAction({
            type: "ir.actions.client",
            tag: "soft_reload",
        });
    }

    async onClose() {
        if (this.createdPayrunId) {
            await this.orm.call("hr.payslip.run", "unlink", [[this.createdPayrunId]]);
            this.createdPayrunId = null;
        }
        return this.actionService.doAction({ type: "ir.actions.act_window_close" });
    }

    buildRawRecord(rawRecord) {
        return { ...rawRecord };
    }

    async generatePayslips() {
        this.state.disabled = true;
        const selectedVersions = await this.model.root.getResIds(true);
        if (selectedVersions.length < 1) {
            return;
        }
        if (this.props.context.raw_record && !this.createdPayrunId) {
            const rawRecord = this.buildRawRecord(this.props.context.raw_record);
            this.createdPayrunId = (
                await this.orm.create("hr.payslip.run", [rawRecord])
            )[0];
        }
        const ids = this.createdPayrunId
            ? [this.createdPayrunId]
            : [this.props.context.active_id];
        try {
            await this.orm.call("hr.payslip.run", "generate_payslips", [ids], {
                version_ids: selectedVersions,
            });
            if (this.props.context.raw_record) {
                await this.openPayslips(ids);
            }
            this.createdPayrunId = null;
            await this.onClose();
            await this.onReload();
        } catch (err) {
            if (this.createdPayrunId) {
                await this.orm.call("hr.payslip.run", "unlink", [
                    [this.createdPayrunId],
                ]);
                this.createdPayrunId = null;
            }
            throw err;
        } finally {
            this.state.disabled = false;
        }
    }

    async openPayslips(ids) {
        const action = await this.orm.call("hr.payslip.run", "action_view_payslips", [
            ids,
        ]);
        return this.actionService.doAction(action);
    }

    async onBack() {
        const rawRecord = this.buildRawRecord(this.props.context.raw_record);
        return this.actionService.doAction("hr_payroll.action_hr_payslip_run_create", {
            additionalContext: Object.fromEntries(
                Object.entries(rawRecord).map(([key, value]) => [
                    `default_${key}`,
                    value,
                ]),
            ),
        });
    }
}
export const versionPayrunListController = {
    ...listView,
    Controller: VersionPayrunListController,
    buttonTemplate: "hr_payroll.VersionPayrunListController.Buttons",
};

registry.category("views").add("hr_version_payrun_list", versionPayrunListController);
