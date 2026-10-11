/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";

export class SlideUnsubscribeDialog extends Component {
    static template = "website_slides.SlideUnsubscribeDialog";
    static components = { CheckBox, Dialog };
    static props = {
        channelId: t.number(),
        isFollower: t.boolean().optional(),
        visibility: t.string(),
        enroll: t.string().optional(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            buttonDisabled: false,
        });
        this.channelID = this.props.channelId;
        this.isFollower = Boolean(this.props.isFollower);
        this.updateState("subscription");
        this.isChecked = this.isFollower;
    }

    updateState(mode) {
        if (mode === "subscription") {
            this.state.title = this.isFollower ? _t("Subscribe") : _t("Notifications");
            this.state.mode = "subscription";
        } else if (mode === "leave") {
            this.state.title = _t("Leave the course");
            this.state.mode = "leave";
        }
    }

    onChangeCheckbox(isChecked) {
        this.isChecked = isChecked;
    }

    onClickLeaveCourse() {
        this.updateState("leave");
    }

    onClickLeaveCourseCancel() {
        this.updateState("subscription");
    }

    async onClickLeaveCourseSubmit() {
        if (this.state.buttonDisabled) {
            return;
        }
        this.state.buttonDisabled = true;

        await rpc("/slides/channel/leave", { channel_id: this.channelID });
        if (
            this.props.visibility === "public" ||
            this.props.visibility === "connected"
        ) {
            window.location.reload();
        } else {
            window.location.href = "/slides";
        }
    }

    async onClickSubscriptionSubmit() {
        if (this.state.buttonDisabled) {
            return;
        }
        this.state.buttonDisabled = true;

        if (this.isFollower === this.isChecked) {
            this.props.close();
        } else {
            await rpc(
                `/slides/channel/${this.isChecked ? "subscribe" : "unsubscribe"}`,
                {
                    channel_id: this.channelID,
                },
            );
            window.location.reload();
        }
    }
}
