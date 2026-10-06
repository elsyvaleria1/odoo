// @ts-check
/** @odoo-module native */
import { LinkPreview } from "@mail/core/common/link_preview";
import { useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";

/**
 * @typedef {Object} Props
 * @property {import("models").MessageLinkPreview[]} messageLinkPreviews
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class MessageLinkPreviewList extends Component {
    static template = "mail.MessageLinkPreviewList";
    static props = { messageLinkPreviews: t.any() };
    static components = { LinkPreview };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.mailContext = useMailContext();
    }
}
