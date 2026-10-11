/** @odoo-module native */
import { Component, markRaw, t, useProps } from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { highlightText } from "@web/core/utils/dom/html";
import { patch } from "@web/core/utils/patch";
import { imageUrl } from "@web/core/utils/urls";
import { CommandPalette, DefaultCommandItem } from "@web/ui/commands";

const commandProviderRegistry = registry.category("command_provider");

class AskAICommand extends Component {
    static template = "ai.AskAICommand";
    static props = { imgUrl: t.string(), ...DefaultCommandItem.props };
    props = useProps(this.constructor.props);
}

const envsWithoutAi = new WeakSet();

async function askAIProvide(env, options) {
    if (envsWithoutAi.has(env)) {
        return [];
    }
    const orm = env.services.orm;
    const actions = env.services.action;
    let agent;
    try {
        agent = await orm.cache().call("ai.agent", "get_ask_ai_agent", []);
    } catch (error) {
        envsWithoutAi.add(env);
        console.warn("[ai] CommandPalette: ai.agent unavailable", error);
        return [];
    }
    if (!agent) {
        return [];
    }
    return [
        {
            action: async () => {
                const action = await orm.call("ai.agent", "action_ask_ai", [
                    options.searchValue,
                ]);
                if (action) {
                    actions.doAction(action);
                }
            },
            category: "apps",
            Component: AskAICommand,
            props: {
                imgUrl: agent
                    ? imageUrl("ai.agent", agent.id, "image_128")
                    : "/ai/static/description/icon.png",
            },
            name: _t("Ask AI"),
        },
    ];
}

commandProviderRegistry.add("ask_ai", {
    namespace: "/",
    async provide(env, options) {
        return askAIProvide(env, options);
    },
});

patch(CommandPalette.prototype, {
    setup() {
        super.setup(...arguments);
        this.appContext = useAppContext();
    },
    async setCommands(namespace, options = {}) {
        const [askAICommand] = await askAIProvide(this.appContext, options);
        const result = await super.setCommands(namespace, options);
        if (
            askAICommand &&
            namespace === "default" &&
            this.state.commands.length === 0 &&
            options.searchValue
        ) {
            this.state.commands = markRaw([
                {
                    ...askAICommand,
                    index: 0,
                    keyId: this.keyId++,
                    text: highlightText(
                        options.searchValue,
                        askAICommand.name,
                        "fw-bolder text-primary",
                    ),
                },
            ]);
            this.selectCommand(this.state.commands.length ? 0 : -1);
        }
        return result;
    },
});
