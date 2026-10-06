/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useEventBus, useService } from "@web/core/utils/hooks";

export default class SystrayAction extends Component {
    static props = {};
    static template = "ai.SystrayAction";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.bus = useEventBus();
        this.actionService = useService("action");
        this.aiChatLauncher = useService("aiChatLauncher");
    }

    async onClickLaunchAIChat() {
        const currentController = this.actionService.currentController;
        if (currentController?.view?.type === "form") {
            this.bus.trigger("AI:OPEN_AI_CHAT", { origin: "chatter_ai_button" });
            return;
        }
        this.aiChatLauncher.launchAIChat({
            callerComponentName: "systray_ai_button",
        });
    }
}

registry
    .category("systray")
    .add("ai.systray_action", { Component: SystrayAction }, { sequence: 30 });
