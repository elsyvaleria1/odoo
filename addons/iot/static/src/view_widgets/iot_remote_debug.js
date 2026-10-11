/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
import { standardWidgetProps } from "@web/views/widgets";

export class IoTRemoteDebug extends Component {
    static template = `iot.HeaderButton`;
    static props = {
        ...standardWidgetProps,
        btn_name: t.string(),
        btn_class: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.iotHttp = useService("iot_http");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.state = proxy({ enabled: false });

        this.iotHttp.websocket.onMessage(
            this.identifier,
            null,
            this.onMessageUpdateStatus.bind(this),
        );
        this.iotHttp.websocket.sendMessage(
            this.identifier,
            { status: true },
            null,
            "remote_debug",
        );
    }

    get identifier() {
        return this.props.record.data.identifier;
    }

    async onClick() {
        this.dialog.add(TokenDialog, {
            validate: this.enableRemoteDebug.bind(this),
            enabled: this.state.enabled,
        });
    }

    async enableRemoteDebug(token) {
        this.iotHttp.websocket.onMessage(
            this.identifier,
            null,
            (message) => {
                this.onMessageUpdateStatus(message);
                if (token && !this.state.enabled) {
                    return this.onFailure();
                }
                this.notification.add(
                    _t(
                        "Remote debug is %s.",
                        this.state.enabled ? _t("enabled") : _t("disabled"),
                    ),
                    {
                        type: "info",
                    },
                );
            },
            this.onFailure.bind(this),
        );
        this.iotHttp.websocket.sendMessage(
            this.identifier,
            { token },
            null,
            "remote_debug",
        );
    }

    onMessageUpdateStatus(message) {
        this.state.enabled = message.result?.enabled;
    }

    onFailure() {
        this.notification.add(_t("Failed to toggle remote debug."), {
            type: "danger",
        });
    }
}

export const ioTRemoteDebug = {
    component: IoTRemoteDebug,
    extractProps: ({ attrs }) => ({
        btn_name: attrs.btn_name,
        btn_class: attrs.btn_class,
    }),
};

export class TokenDialog extends Component {
    static template = "iot.RemoteDebugDialog";
    static components = { Dialog };
    static props = {
        validate: t.function(),
        close: t.function(),
        enabled: t.boolean(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ token: "" });
    }

    validate() {
        this.props.validate(this.state.token);
        this.props.close();
    }
}

registry.category("view_widgets").add("iot_remote_debug", ioTRemoteDebug);
