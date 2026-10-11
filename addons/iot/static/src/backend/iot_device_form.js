/** @odoo-module native */
import { readDeviceEvent } from "@iot/device_messages";
import { printReport } from "@iot/iot_report_action";
import { useAppContext } from "@web/core/app_context";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { provideViewButtonContext } from "@web/core/view_button_context_hooks";
import { formView } from "@web/views/form";

class IoTDeviceController extends formView.Controller {
    setup() {
        super.setup();
        this.appContext = useAppContext();
        this.iotHttp = useService("iot_http");
        this.notification = useService("notification");
        this.orm = useService("orm");

        provideViewButtonContext({
            onClickViewButton: this.onClickButtonTest.bind(this),
        });
    }

    async onRecordSaved(record) {
        if (["keyboard", "scanner"].includes(record.data.type)) {
            await this.updateKeyboardLayout(record.data);
        } else if (record.data.type === "display") {
            await this.updateDisplayUrl(record.data);
        }
    }
    async updateKeyboardLayout(data) {
        const { iot_id, identifier, keyboard_layout, is_scanner } = data;
        this.iotHttp.action(
            iot_id.id,
            identifier,
            {
                action: "update_is_scanner",
                is_scanner,
            },
            () => {},
            () => {
                this.notification.add(
                    _t("Failed to update scanner mode on the device."),
                    {
                        type: "danger",
                    },
                );
            },
        );
        if (keyboard_layout) {
            const [keyboard] = await this.model.orm.read(
                "iot.keyboard.layout",
                [keyboard_layout.id],
                ["layout", "variant"],
            );
            return this.iotHttp.action(
                iot_id.id,
                identifier,
                {
                    action: "update_layout",
                    layout: keyboard.layout,
                    variant: keyboard.variant,
                },
                () => {},
                () => {
                    this.notification.add(
                        _t("Failed to update keyboard layout on the device."),
                        {
                            type: "danger",
                        },
                    );
                },
            );
        } else {
            return this.iotHttp.action(iot_id.id, identifier, {
                action: "update_layout",
            });
        }
    }
    async updateDisplayUrl(data) {
        const { iot_id, identifier, display_url } = data;
        return this.iotHttp.action(iot_id.id, identifier, {
            action: "update_url",
            url: display_url,
        });
    }

    onDeviceEvent(event, type) {
        const { message: errorMessage, defaultMessage } = readDeviceEvent(type, event);
        switch (event.status) {
            case "error":
            case "timeout":
                this.notification.add(errorMessage, { type: "danger" });
                return;
            case "warning":
                this.notification.add(errorMessage, { type: "warning" });
                return;
            case "disconnected":
                this.notification.add(_t("Device is disconnected"), { type: "danger" });
                return;
            default:
                this.notification.add(defaultMessage, { type: "info" });
                return;
        }
    }

    async onClickButtonTest(params) {
        if (params.clickParams.name === "test_device") {
            const { iot_id, identifier, type, subtype } = this.model.root.data;

            if (type === "printer" && subtype === "office_printer") {
                const reportId = (
                    await this.orm.searchRead(
                        "ir.actions.report",
                        [
                            ["report_type", "=", "qweb-pdf"],
                            ["report_name", "=", "web.preview_externalreport"],
                        ],
                        ["id"],
                        { limit: 1 },
                    )
                )[0].id;
                const deviceId = this.model.root.resId;
                return printReport(
                    this.appContext,
                    [reportId, [deviceId], null],
                    [deviceId],
                );
            }

            return this.iotHttp.action(
                iot_id.id,
                identifier,
                { action: "status" },
                (event) => this.onDeviceEvent(event, type),
                (event) => this.onDeviceEvent(event, type),
            );
        }
    }
}

export const iotDeviceFormView = {
    ...formView,
    Controller: IoTDeviceController,
};

registry.category("views").add("iot_device_form", iotDeviceFormView);
