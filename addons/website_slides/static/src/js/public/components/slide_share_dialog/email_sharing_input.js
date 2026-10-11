/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { rpc } from "@web/core/network";
import { elementRef } from "@web/core/utils/element_ref";
import { session } from "@web/session";

const log = makeLogger("website_slides.share_email");

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
        this.state.isInvalid = false;
        if (emails) {
            const type = this.props.isChannel ? "channel" : "slide";
            try {
                this.state.isDone = await rpc(`/slides/${type}/send_share_email`, {
                    emails: emails,
                    fullscreen: this.props.isFullscreen,
                    [`${type}_id`]: this.props.id,
                });
            } catch (error) {
                log.logic("share by email failed", () => ({ error: String(error) }));
            }
            if (this.state.isDone) {
                return;
            }
        }
        this.state.isInvalid = true;
        this.input.el.focus();
    }
}
