/** @odoo-module native */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { FormController, formView } from "@web/views/form";

export class AddIoTBoxFormController extends FormController {
    setup() {
        super.setup();
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.iotBoxesBeforeConnection = [];
        this.newIoTBoxes = [];
        this.iotCheckTimer = null;

        onMounted(async () => {
            await this.initializeIoTConnection();
        });

        onWillUnmount(() => {
            this.onWillUnmount();
        });
    }

    /** @returns {Promise<void>} */
    async initializeIoTConnection() {
        this.iotBoxesBeforeConnection = await this.orm.call("iot.box", "search_read", [
            [],
            ["identifier"],
        ]);

        this.iotCheckTimer = setInterval(async () => {
            if (await this.lookForNewIoTBox()) {
                this.notifyIoTBoxFound(true);
                clearInterval(this.iotCheckTimer);
            }
        }, 5000);

        setTimeout(() => this.notifyIoTBoxFound(false), 60 * 2 * 1000);
    }

    /** @returns {Promise<boolean>} */
    async lookForNewIoTBox() {
        const iotBoxesAfterConnection = await this.orm.call("iot.box", "search_read", [
            [],
            ["identifier"],
        ]);
        this.newIoTBoxes = iotBoxesAfterConnection.filter(
            (afterBox) =>
                !this.iotBoxesBeforeConnection.some(
                    (beforeBox) => beforeBox.identifier === afterBox.identifier,
                ),
        );

        return this.newIoTBoxes.length > 0;
    }

    /** @param {boolean} found */
    notifyIoTBoxFound(found) {
        if (found) {
            this.action.doAction({ type: "ir.actions.act_window_close" });
            this.notification.add(_t("New IoT Box connected!"), { type: "success" });
        }
    }

    onWillUnmount() {
        if (this.iotCheckTimer) {
            clearInterval(this.iotCheckTimer);
        }
    }
}

export const addIoTBox = { ...formView, Controller: AddIoTBoxFormController };

registry.category("views").add("add_iot_box_wizard", addIoTBox);
