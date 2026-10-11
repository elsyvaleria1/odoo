/** @odoo-module native */
import { AddIoTBoxFormController } from "@iot/backend/add_iot_box_form_controller";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(AddIoTBoxFormController.prototype, {
    setup() {
        super.setup();
        this.actionService = useService("action");
    },
    async notifyIoTBoxFound(found) {
        if (
            !found ||
            this.newIoTBoxes.length === 0 ||
            !(await user.hasGroup("point_of_sale.group_pos_manager"))
        ) {
            return super.notifyIoTBoxFound(...arguments);
        }

        const posConfigAmount = await this.orm.searchCount("pos.config", [
            ["active", "=", true],
        ]);
        if (posConfigAmount === 0) {
            return super.notifyIoTBoxFound(...arguments);
        }

        const iotBoxIdentifier = this.newIoTBoxes[0].identifier;
        this.interval = setInterval(async () => {
            const connectedDevicesAmount = await this.orm.searchCount("iot.device", [
                ["iot_id.identifier", "=", iotBoxIdentifier],
            ]);

            if (connectedDevicesAmount > 0) {
                clearInterval(this.interval);
                this.actionService.doAction({
                    type: "ir.actions.act_window",
                    name: _t("Connect to a Point of Sale"),
                    res_model: "wizard.pos.config.update.iot.device",
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        default_iot_box_identifier: iotBoxIdentifier,
                    },
                });
            }
        }, 1000);

        this.timeout = setTimeout(
            () =>
                this.actionService.doAction({
                    type: "ir.actions.act_window_close",
                }),
            30 * 1000,
        );
    },
    onWillUnmount() {
        super.onWillUnmount();
        if (this.interval) {
            clearInterval(this.interval);
        }
        if (this.timeout) {
            clearTimeout(this.timeout);
        }
    },
});
