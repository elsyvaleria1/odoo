// @ts-check
/** @odoo-module native */
import { DiscussNotificationSettings } from "@mail/discuss/core/common/discuss_notification_settings";
import { Component, useProps, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
export class DiscussNotificationSettingsClientAction extends Component {
    static components = { DiscussNotificationSettings };
    static props = null;
    static template = xml`
        <div class="o-mail-DiscussNotificationSettingsClientAction mx-3 my-2">
            <DiscussNotificationSettings/>
        </div>
    `;
    props = useProps(this.constructor.props);
}

registry
    .category("actions")
    .add(
        "mail.discuss_notification_settings_action",
        DiscussNotificationSettingsClientAction,
    );
