/** @odoo-module native */
import { ActionPanel } from "@mail/core/common/action_panel";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";

const commandRegistry = registry.category("discuss.channel_commands");

export class LivechatCommandDialog extends Component {
    static template = "im_livechat.LivechatCommandDialog";
    static components = { ActionPanel };
    static props = {
        thread: t.any(),
        close: t.any(),
        commandName: t.any(),
        placeholderText: t.any(),
        title: t.any(),
        icon: t.any(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ inputText: "" });
        this.store = useService("mail.store");
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && this.state.inputText.trim().length > 0) {
            this.executeCommand();
        }
    }

    executeCommand() {
        const command = commandRegistry.get(this.props.commandName, false);
        if (command) {
            this.props.thread.executeCommand(
                command,
                `/${this.props.commandName} ${this.state.inputText}`,
            );
            this.props.close();
        }
    }
}
