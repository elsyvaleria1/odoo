/** @odoo-module native */
import { cleanTerm } from "@mail/utils/common/format";
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { imageUrl } from "@web/core/utils/urls";

const commandProviderRegistry = registry.category("command_provider");
const commandCategoryRegistry = registry.category("command_categories");

commandCategoryRegistry.add(
    "AI_AGENTS",
    { namespace: "@", name: _t("Agents") },
    { sequence: 30 },
);

const envsWithoutAi = new WeakSet();

export class AICommand extends Component {
    static template = "ai_app.AICommand";
    static props = {
        executeCommand: t.function(),
        name: t.string(),
        subtitle: t.string(),
        imgUrl: t.string(),
        action: t.object().optional(),
        searchValue: t.string(),
        slots: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}
export class AICommandPalette {
    constructor(env, options) {
        this.env = env;
        this.options = options;
        this.orm = env.services.orm;
        this.ui = env.services.ui;
        this.actions = env.services.action;
        this.commands = [];
        this.options = options;
        this.cleanedTerm = cleanTerm(this.options.searchValue);
        this.agents = [];
    }

    async fetch() {
        if (envsWithoutAi.has(this.env)) {
            this.agents = [];
            return;
        }
        try {
            this.agents = await this.orm.searchRead(
                "ai.agent",
                [],
                ["id", "name", "subtitle", "partner_id"],
                { load: false },
            );
        } catch (error) {
            envsWithoutAi.add(this.env);
            console.warn("[ai_app] CommandPalette: ai.agent unavailable", error);
            this.agents = [];
        }
    }

    async addCommands(filtered) {
        this.agents
            .filter(
                (agent) =>
                    (cleanTerm(agent.name).includes(this.cleanedTerm) ||
                        (agent.subtitle &&
                            cleanTerm(agent.subtitle).includes(this.cleanedTerm))) &&
                    (!filtered || !filtered.has(agent)),
            )
            .slice(0, 5)
            .forEach((agent) => {
                this.commands.push({
                    Component: AICommand,
                    action: async () => {
                        const result = await this.orm.call(
                            "ai.agent",
                            "open_agent_chat",
                            [agent.id],
                        );
                        if (result) {
                            this.actions.doAction(result);
                        }
                    },
                    name: agent.name,
                    props: {
                        imgUrl: imageUrl("ai.agent", agent.id, "image_128"),
                        subtitle: agent.subtitle ? agent.subtitle : "",
                    },
                    category: "AI_AGENTS",
                });
            });
    }
}

commandProviderRegistry.add("chat_with_agent", {
    namespace: "@",
    async provide(env, options) {
        const palette = new AICommandPalette(env, options);
        await palette.fetch();
        palette.addCommands();
        return palette.commands;
    },
});
