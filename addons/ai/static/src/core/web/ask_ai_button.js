/** @odoo-module native */
import { Component, onWillStart, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { useService } from "@web/core/utils/hooks";

export class AskAIButton extends Component {
    static template = "ai.AskAIButton";
    static components = { DropdownItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        onWillStart(async () => {
            const agent = await this.orm
                .cache()
                .call("ai.agent", "get_ask_ai_agent", []);
            this.hasAIAgent = Boolean(agent);
        });
    }
    async onAskAIClick() {
        const action = await this.orm.call("ai.agent", "action_ask_ai", [""]);
        if (action) {
            // Don't await so that the command palette can close immediately
            this.action.doAction(action);
        }
    }
}
