// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
export class CallPermissionDialog extends Component {
    static components = { Dialog };
    static props = {
        close: t.function(),
        media: t.customValidator(t.string(), (s) =>
            ["camera", "microphone"].includes(s),
        ),
        useMicrophone: t.function(),
        useCamera: t.function(),
    };
    static template = "discuss.CallPermissionDialog";
    props = useProps(this.constructor.props);

    setup() {
        this.rtc = useService("discuss.rtc");
    }

    async onClickUseMicrophone() {
        if (await this.rtc.askForBrowserPermission({ audio: true })) {
            await this.props.useMicrophone();
        }
        this.props.close();
    }

    async onClickUseCamera() {
        if (await this.rtc.askForBrowserPermission({ video: true })) {
            await this.props.useCamera();
        }
        this.props.close();
    }

    async onClickUseMicAndCamera() {
        if (await this.rtc.askForBrowserPermission({ audio: true, video: true })) {
            await Promise.all([this.props.useMicrophone(), this.props.useCamera()]);
        }
        this.props.close();
    }

    get primaryActionText() {
        return this.props.media === "camera" ? _t("Use Camera") : _t("Use Microphone");
    }

    get permissionPrompt() {
        if (this.props.media === "microphone") {
            return _t("Do you want people to hear you in the meeting?");
        }
        return _t("Do you want people to see you in the meeting?");
    }

    get permissionNote() {
        return _t("You can still turn off your %s anytime.", this.props.media);
    }
}
