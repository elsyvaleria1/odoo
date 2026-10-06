// @ts-check
/** @odoo-module native */
import { CallSettingsDialog } from "@mail/discuss/call/common/call_settings";
import { DeviceSelect } from "@mail/discuss/call/common/device_select";
import { Component, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
export class QuickVoiceSettings extends Component {
    static template = "discuss.QuickVoiceSettings";
    static props = {};
    static components = { DeviceSelect };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.dialogService = useService("dialog");
    }

    onClickVoiceSettings() {
        this.dialogService.add(CallSettingsDialog, {});
    }
}
