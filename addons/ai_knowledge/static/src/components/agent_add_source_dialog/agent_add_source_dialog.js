/** @odoo-module native */

import { AgentSourceAddDialog } from "@ai/components/agent_add_source_dialog/agent_add_source_dialog";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { SelectCreateDialog } from "@web/views/view_dialogs";

patch(AgentSourceAddDialog.prototype, {
    get cardsData() {
        return [
            ...super.cardsData,
            {
                image: "/ai_knowledge/static/img/icon.png",
                icon: "fa-file-text-o",
                title: _t("Add from Knowledge"),
                onClick: () => this.onAddKnowledgeSourceClick(),
            },
        ];
    },

    onAddKnowledgeSourceClick() {
        this.dialog.add(SelectCreateDialog, {
            title: _t("Add from Knowledge"),
            noCreate: true,
            multiSelect: true,
            resModel: "knowledge.article",
            domain: [
                ["is_template", "=", false],
                ["is_article_item", "=", false],
                ["user_has_access", "=", true],
            ],
            onSelected: async (resIds) => {
                if (resIds.length) {
                    this.addKnowledgeArticlesToAgent(resIds);
                }
            },
        });
    },

    async addKnowledgeArticlesToAgent(article_ids) {
        this.state.loading = true;
        await this.orm.call("ai.agent.source", "create_from_articles", [
            article_ids,
            this.agentId,
        ]);
        this.state.loading = false;
        return this.actionService.doAction({
            type: "ir.actions.client",
            tag: "soft_reload",
        });
    },
});
