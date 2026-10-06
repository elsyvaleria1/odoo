// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class MessageNotificationPopover extends Component {
    static template = "mail.MessageNotificationPopover";
    static props = { message: t.any(), close: t.any().optional() };
    props = useProps(this.constructor.props);
}
