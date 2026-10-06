/** @odoo-module native */
import { onWillStart, proxy, t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpWorkcenterDialog extends ConfirmationDialog {
    static template = "mrp_workorder.MrpWorkcenterDialog";
    static props = {
        ...ConfirmationDialog.props,
        body: t.string().optional(),
        workcenters: t.array().optional(),
        disabled: t.array().optional(),
        active: t.array().optional(),
        radioMode: t.boolean().optional(),
        showWarning: t.boolean().optional(),
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.action = useService("action");
        this.workcenters = this.props.workcenters || [];
        this.state = proxy({
            activeWorkcenters: this.props.active ? [...this.props.active] : [],
            noWorkcenters: false,
        });

        onWillStart(async () => {
            if (!this.workcenters.length) {
                await this._loadWorkcenters();
            }
        });
    }

    get appName() {
        return encodeURIComponent(this.menu.getCurrentApp()?.name || _t("Shop Floor"));
    }

    isActive(workcenter) {
        return this.state.activeWorkcenters.includes(workcenter.id);
    }

    get disabled() {
        if (!this.props.disabled) {
            return false;
        }
        return this.props.disabled.includes(this.workcenter.id);
    }

    selectWorkcenter(workcenter) {
        if (this.props.radioMode) {
            this.state.activeWorkcenters = [workcenter.id];
        } else if (this.state.activeWorkcenters.includes(workcenter.id)) {
            this.state.activeWorkcenters = this.state.activeWorkcenters.filter(
                (id) => id !== workcenter.id,
            );
        } else {
            this.state.activeWorkcenters.push(workcenter.id);
        }
    }

    confirm() {
        this.props.confirm(
            this.state.activeWorkcenters.reduce((acc, id) => {
                const res = this.workcenters.find((wc) => wc.id === id);
                return res ? [...acc, res] : acc;
            }, []),
        );
        this.props.close();
    }

    async _loadWorkcenters() {
        this.workcenters = await this.ormService.searchRead(
            "mrp.workcenter",
            [],
            ["display_name"],
        );
        if (!this.workcenters.length) {
            this.state.noWorkcenters = true;
        }
    }

    async createWorkcenter() {
        await this.ormService.call("mrp.workcenter", "action_enable_routings", [[]]);
        location.assign("/odoo/workcenters");
    }
}
