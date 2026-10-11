/** @odoo-module native */
import {
    getEmbeddedProps,
    StateChangeManager,
    useEmbeddedState,
} from "@html_editor/others/embedded_component_utils";
import {
    EmbeddedComponentToolbar,
    EmbeddedComponentToolbarButton,
} from "@html_editor/others/embedded_components/core/embedded_component_toolbar/embedded_component_toolbar";
import { ArticleIndexList } from "@knowledge/editor/embedded_components/backend/article_index/article_index_list";
import {
    provideKnowledgeContext,
    useKnowledgeContext,
} from "@knowledge/js/knowledge_context";
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { KeepLast } from "@web/core/utils/concurrency";
import { useEventBus, useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";

export class EmbeddedArticleIndexComponent extends Component {
    static template = "knowledge.EmbeddedArticleIndex";
    static components = {
        ArticleIndexList,
        EmbeddedComponentToolbar,
        EmbeddedComponentToolbarButton,
    };
    static props = {
        host: t.object(),
        articles: t.array(t.object()).optional(),
        showAllChildren: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.bus = useEventBus();
        this.model = useViewModel();
        this.orm = useService("orm");
        this.embeddedState = useEmbeddedState(this.props.host);
        this.keepLastFetch = new KeepLast();
        this.state = proxy({
            loading: false,
            key: 0,
        });

        provideKnowledgeContext({
            reloadArticleIndex: () => this.loadArticleIndex(),
        });
        this.knowledgeContext = useKnowledgeContext();

        onWillStart(async () => {
            if (this.embeddedState.articles === undefined) {
                this.loadArticleIndex({ firstLoad: true });
            }
        });
    }

    /**
     * @param {integer} resId
     * @param {Boolean} showAllChildren
     * @returns {Array[Object]}
     */
    async fetchAllArticles(resId, showAllChildren) {
        const domain = [
            ["parent_id", !showAllChildren ? "=" : "child_of", resId],
            ["is_article_item", "=", false],
        ];
        const { records } = await this.orm.webSearchRead("knowledge.article", domain, {
            specification: {
                display_name: {},
                parent_id: {},
            },
            order: "sequence",
        });
        return records;
    }

    async loadArticleIndex({ showAllChildren = undefined, firstLoad = false } = {}) {
        this.state.loading = true;
        if (showAllChildren === undefined) {
            showAllChildren = this.embeddedState.showAllChildren;
        }
        const resId = this.model.root.resId;
        const promise = this.fetchAllArticles(resId, showAllChildren);
        const articles = await this.keepLastFetch.add(promise);
        if (firstLoad && this.embeddedState.articles !== undefined) {
            this.state.loading = false;
            return;
        }
        /**
         * @param {integer} parentId
         * @returns {Object}
         */
        const buildIndex = (parentId) =>
            articles
                .filter(
                    (article) => article.parent_id && article.parent_id === parentId,
                )
                .map((article) => ({
                    id: article.id,
                    name: article.display_name,
                    childIds: buildIndex(article.id),
                }));
        this.state.loading = false;
        this.embeddedState.showAllChildren = showAllChildren;
        this.embeddedState.articles = buildIndex(resId);
        this.bus.trigger("KNOWLEDGE:RELOAD_SIDEBAR", {});
    }

    async onSwitchModeBtnClick() {
        await this.loadArticleIndex({
            showAllChildren: !this.embeddedState.showAllChildren,
        });
        this.state.key++;
    }

    async openTemplatePicker() {
        const record = this.model.root;
        const templates = await this.orm.call(
            "knowledge.article",
            "get_suggested_templates",
            [[record.resId]],
        );
        this.bus.trigger("KNOWLEDGE:OPEN_ANNEXE_TEMPLATE_PICKER", {
            articles: [],
            templates: templates,
            onLoadArticle: () => {},
            /** @param {integer} templateId */
            onLoadTemplate: async (templateId) => {
                const articleIds = await this.orm.call(
                    "knowledge.article",
                    "load_suggested_template",
                    [record.resId, templateId],
                );
                if (articleIds?.length) {
                    await this.loadArticleIndex();
                    await this.knowledgeContext.openArticle(articleIds[0]);
                }
            },
            onDeleteArticle: () => {},
            /** @param {integer} templateId */
            onDeleteTemplate: async (templateId) => {
                await this.orm.unlink("knowledge.article", [templateId]);
            },
        });
    }

    async addChildToArticle() {
        const [articleId] = await this.orm.create("knowledge.article", [
            {
                parent_id: this.model.root.resId,
            },
        ]);
        await this.knowledgeContext.openArticle(articleId);
    }
}

export const articleIndexEmbedding = {
    name: "articleIndex",
    Component: EmbeddedArticleIndexComponent,
    getStateChangeManager: (config) => new StateChangeManager(config),
    getProps: (host) => ({
        host,
        ...getEmbeddedProps(host),
    }),
};
