/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class EmailSharingInput extends Component {
    static template = "website_slides.EmailSharingInput";
    static props = {
        id: t.number(),
        isChannel: t.boolean().optional(),
        isFullscreen: t.boolean().optional(),
        category: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.notification = useService("notification");
        this.input = elementRef();
        this.isWebsiteUser = session.is_website_user;
        this.state = proxy({
            isDone: false,
            isInvalid: false,
        });
    }

    onKeyPress(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            this.onShareByEmailClick();
        }
    }

    async onShareByEmailClick() {
        const emails = this.input.el.value;
        if (emails) {
            const type = this.props.isChannel ? "channel" : "slide";
            const done = await rpc(`/slides/${type}/send_share_email`, {
                emails: emails,
                fullscreen: this.props.isFullscreen,
                [`${type}_id`]: this.props.id,
            });
            this.state.isDone = done;
            if (done) {
                return;
            }
        }
        this.setInvalid();
    }

    setInvalid() {
        this.state.isInvalid = true;
        this.notification.add(_t("Please enter valid email(s)"), { type: "danger" });
        this.input.el.focus();
    }
}
