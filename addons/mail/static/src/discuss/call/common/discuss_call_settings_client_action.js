// @ts-check
/** @odoo-module native */
import { CallSettings } from "@mail/discuss/call/common/call_settings";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
export class DiscussCallSettingsClientAction extends Component {
    static components = { CallSettings };
    static props = null;
    static template = "mail.DiscussCallSettingsClientAction";
    props = useProps(this.constructor.props);
}

registry
    .category("actions")
    .add("mail.discuss_call_settings_action", DiscussCallSettingsClientAction);
