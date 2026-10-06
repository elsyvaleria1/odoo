/** @odoo-module native */
import { useKnowledgeArticleSelector } from "@knowledge/hooks/knowledge_article_selector";
import { useAccountReportContext } from "@report_formula/components/account_report/account_report_context";
import { AccountReportCogMenu } from "@report_formula/components/account_report/cog_menu/cog_menu";
import { _t } from "@web/core/translation";
import { uuid } from "@web/core/utils/format/strings";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";

patch(AccountReportCogMenu.prototype, {
    /** @override */
    setup() {
        super.setup();
        this.reportContext = useAccountReportContext();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.openArticleSelector = useKnowledgeArticleSelector();
        this.knowledgeCommandsService = useService("knowledgeCommandsService");
    },
    /** @override */
    get cogButtons() {
        const buttons = super.cogButtons;
        buttons.push({
            groupNumber: COG_GROUP.INTEGRATE,
            icon: "fa-solid fa-book",
            name: _t("Insert in Article…"),
            onClick: () => {
                this.openArticleSelector(async (articleId) => {
                    const blueprint = document.createElement("div");
                    blueprint.setAttribute("data-oe-id", uuid());
                    blueprint.setAttribute("data-oe-protected", true);
                    blueprint.setAttribute("data-embedded", "accountReport");
                    blueprint.setAttribute(
                        "data-embedded-props",
                        JSON.stringify({
                            name: this.actionService.currentController.action.name,
                            options: this.reportContext.controller.cachedFilterOptions,
                        }),
                    );
                    this.knowledgeCommandsService.setPendingEmbeddedBlueprint({
                        embeddedBlueprint: blueprint,
                        model: "knowledge.article",
                        field: "body",
                        resId: articleId,
                    });
                    this.actionService.doAction(
                        "knowledge.ir_actions_server_knowledge_home_page",
                        {
                            additionalContext: {
                                res_id: articleId,
                            },
                        },
                    );
                });
            },
        });
        return buttons;
    },
});
