/** @odoo-module native */
import { Component, onMounted, useProps } from "@odoo/owl";
import { router, routerBus } from "@web/core/browser/router";
import { provideDebugContext } from "@web/core/debug/debug_context";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { MainComponentsContainer } from "@web/ui/main_components_container";
import { ActionContainer } from "@web/webclient/actions";

export class KnowledgePortalWebClient extends Component {
    static props = {};
    static components = { ActionContainer, MainComponentsContainer };
    static template = "knowledge.KnowledgePortalWebClient";
    props = useProps(this.constructor.props);

    setup() {
        this.bus = useEventBus();
        window.parent.document.body.style.margin = "0";
        this.actionService = useService("action");
        provideDebugContext({ categories: ["default"] });
        useBus(routerBus, "ROUTE_CHANGE", this._showView.bind(this));
        onMounted(() => {
            this._showView();
        });
    }

    async _showView() {
        const isOnKnowledgeArticleFormView = () => {
            if (this.actionService.currentController) {
                const { action } = this.actionService.currentController;
                return (
                    action &&
                    action.xml_id === "knowledge.knowledge_article_action_form"
                );
            }
            return false;
        };

        if (isOnKnowledgeArticleFormView() && router.current.resId) {
            this.bus.trigger("KNOWLEDGE:OPEN_ARTICLE", {
                id: router.current.resId,
            });
            return;
        }

        await this.actionService.doAction(
            "knowledge.ir_actions_server_knowledge_home_page",
            {
                additionalContext: router.current.resId
                    ? { res_id: router.current.resId }
                    : {},
                stackPosition: "replaceCurrentAction",
            },
        );
    }
}
