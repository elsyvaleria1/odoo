/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class SnailmailNotificationPopover extends Component {
    static template = "snailmail.SnailmailNotificationPopover";
    static props = { message: t.any(), close: t.any().optional() };
    props = useProps(this.constructor.props);
}
