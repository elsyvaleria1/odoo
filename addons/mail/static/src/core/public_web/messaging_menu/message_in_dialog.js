// @ts-check
/** @odoo-module native */
import { discussComponentRegistry } from "@mail/core/common/discuss_component_registry";
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";

export class MessageInDialog extends Component {
    static components = { Dialog };
    static props = { close: t.any(), message: t.any() };
    static template = "mail.MessageInDialog";
    props = useProps(this.constructor.props);

    get messageComponent() {
        return discussComponentRegistry.get("Message");
    }

    get title() {
        return this.props.message.thread?.displayName ?? _t("Message");
    }
}
