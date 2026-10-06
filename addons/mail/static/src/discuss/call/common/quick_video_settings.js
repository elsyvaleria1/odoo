// @ts-check
/** @odoo-module native */
import { CallSettingsDialog } from "@mail/discuss/call/common/call_settings";
import { DeviceSelect } from "@mail/discuss/call/common/device_select";
import { Component, useProps } from "@odoo/owl";
import { isBrowserSafari } from "@web/core/browser/feature_detection";
import { useService } from "@web/core/utils/hooks";
export class QuickVideoSettings extends Component {
    static template = "discuss.QuickVideoSettings";
    static props = {};
    static components = { DeviceSelect };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.dialogService = useService("dialog");
        this.isBrowserSafari = isBrowserSafari;
    }

    onClickVideoSettings() {
        this.dialogService.add(CallSettingsDialog, {});
    }
}
