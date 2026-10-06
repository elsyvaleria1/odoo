// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export const messagingMenuEmptyProps = {
    title: t.any(),
    subtitle: t.any().optional(),
    padding: t.any().optional("p-3"),
    slots: t.any().optional(),
};

export class MessagingMenuEmpty extends Component {
    static props = messagingMenuEmptyProps;
    static template = "mail.MessagingMenuEmpty";
    props = useProps(this.constructor.props);
}
