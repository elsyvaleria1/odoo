/** @odoo-module native */
import { useKnowledgeArticleSelector } from "@knowledge/hooks/knowledge_article_selector";
import { Component, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";
import { useActionCallbackRecorders } from "@web/core/action_hook";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { omit } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { renderToElement } from "@web/core/utils/render";
import { useViewConfig } from "@web/core/view_config_hooks";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";
import { useSearchModel } from "@web/search/search_model";

const cogMenuRegistry = registry.category("cogMenu");

const supportedEmbeddedViews = new Set([
    "calendar",
    "graph",
    "hierarchy",
    "kanban",
    "list",
    "pivot",
    "cohort",
    "gantt",
    "map",
]);

class InsertEmbeddedViewMenu extends Component {
    static props = {};
    static template = "knowledge.InsertEmbeddedViewMenu";
    static components = { CogMenuItem, Dropdown };
    props = useProps(this.constructor.props);

    setup() {
        this.actionCallbacks = useActionCallbackRecorders();
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.knowledgeCommandsService = useService("knowledgeCommandsService");
        this.openArticleSelector = useKnowledgeArticleSelector();
    }

    /** @returns {Object|null} */
    extractCurrentViewEmbedTemplateProps() {
        const viewProps = {
            context: this.getViewContext(),
            displayName: this.config.getDisplayName(),
            viewType: this.config.viewType,
        };
        const xmlId = this.actionService.currentController?.action?.xml_id;
        if (xmlId) {
            viewProps.actionXmlId = xmlId;
            return { embeddedProps: { viewProps } };
        }
        const originalAction =
            this.actionService.currentController?.action?._originalAction;
        if (originalAction) {
            const action = JSON.parse(originalAction);
            delete action.help;
            viewProps.actWindow = action;
            return { embeddedProps: { viewProps } };
        }
        return null;
    }

    /** @returns {Object} */
    getViewContext() {
        const context = {};
        if (this.searchModel) {
            Object.assign(
                context,
                omit(this.searchModel.context, ...Object.keys(user.context)),
            );
            Object.assign(context, {
                knowledge_search_model_state: JSON.stringify(
                    this.searchModel.exportState(),
                ),
            });
        }
        const fns = this.actionCallbacks.__getContext__.callbacks;
        const localContext = Object.assign({}, ...fns.map((fn) => fn()));
        const extraContext = {};
        this.searchModel.trigger("insert-embedded-view", extraContext);
        Object.assign(context, localContext, extraContext);
        return context;
    }

    /** @param {string} template */
    insertCurrentViewInKnowledge(template) {
        const config = this.config;
        const templateProps = this.extractCurrentViewEmbedTemplateProps();
        if (config.actionType !== "ir.actions.act_window" || !templateProps) {
            throw new Error(
                'This view can not be embedded in an article: the action is not an "ir.actions.act_window" or is not serializable.',
            );
        }
        this.openArticleSelector(async (id) => {
            this.knowledgeCommandsService.setPendingEmbeddedBlueprint({
                embeddedBlueprint: renderToElement(template, {
                    embeddedProps: JSON.stringify(templateProps.embeddedProps),
                }),
                model: "knowledge.article",
                field: "body",
                resId: id,
            });
            this.actionService.doAction(
                "knowledge.ir_actions_server_knowledge_home_page",
                {
                    additionalContext: {
                        res_id: id,
                    },
                },
            );
        });
    }

    onInsertEmbeddedViewInArticle() {
        this.insertCurrentViewInKnowledge("knowledge.EmbeddedViewBlueprint");
    }

    onInsertViewLinkInArticle() {
        this.insertCurrentViewInKnowledge("knowledge.EmbeddedViewLinkBlueprint");
    }
}

cogMenuRegistry.add("insert-embedded-view-menu", {
    Component: InsertEmbeddedViewMenu,
    groupNumber: COG_GROUP.INTEGRATE,
    isDisplayed: (env) =>
        isActWindowView(env, [...supportedEmbeddedViews]) &&
        Boolean(env.config.actionId) &&
        !env.searchModel.context.knowledgeEmbeddedViewId,
});
