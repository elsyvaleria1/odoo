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

    /**
     * Creates a loop to check for new IoT Boxes every 10 seconds.
     * @returns {Promise<void>}
     */
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

    /**
     * Look for new IoT Boxes that have been connected since the last check.
     * @returns {Promise<boolean>} True if a new IoT Box has been found, false otherwise.
     */
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

    /**
     * Notify the user if a new IoT Box has been found. If no new IoT Box has been found, notify the user.
     * @param {boolean} found Whether a new IoT Box has been found.
     */
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
