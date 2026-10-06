/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, t, useProps } from "@odoo/owl";

export class ReadonlyEmbeddedArticleIndexComponent extends Component {
    static props = {
        articles: t.array(t.object()).optional([]),
        showAllChildren: t.boolean().optional(true),
    };
    static template = "knowledge.ReadonlyEmbeddedArticleIndex";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
    }

    /** @param {integer} articleId */
    openArticle(articleId) {
        if (this.knowledgeContext.openArticle) {
            this.knowledgeContext.openArticle(articleId);
        }
    }
}

export const readonlyArticleIndexEmbedding = {
    name: "articleIndex",
    Component: ReadonlyEmbeddedArticleIndexComponent,
    getProps: (host) => ({
        ...getEmbeddedProps(host),
    }),
};
