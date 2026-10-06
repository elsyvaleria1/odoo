/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, t, useProps } from "@odoo/owl";
import { useNestedSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";

export class ArticleIndexList extends Component {
    static template = "knowledge.ArticleIndexList";
    static props = { articles: t.array(t.object()), isNested: t.boolean().optional() };
    props = useProps(this.constructor.props);

    setup() {
        this.knowledgeContext = useKnowledgeContext();
        this.model = useViewModel();
        this.orm = useService("orm");
        this.root = elementRef();

        useNestedSortable({
            ref: this.root,
            elements: "li",
            nest: this.props.isNested,
            onDrop: async ({ element, next, parent }) => {
                const options = {
                    parent_id: parent
                        ? parseInt(parent.getAttribute("data-article-id"))
                        : this.model.root.resId,
                };
                if (next) {
                    options.before_article_id = parseInt(
                        next.getAttribute("data-article-id"),
                    );
                }
                const id = parseInt(element.getAttribute("data-article-id"));
                await this.orm.call("knowledge.article", "move_to", [id], options);
                await this.knowledgeContext.reloadArticleIndex();
            },
        });
    }

    /** @param {integer} articleId */
    openArticle(articleId) {
        if (this.knowledgeContext.openArticle) {
            this.knowledgeContext.openArticle(articleId);
        }
    }

    /** @param {integer} articleId */
    async deleteArticle(articleId) {
        try {
            await this.orm.call("knowledge.article", "action_send_to_trash", [
                articleId,
            ]);
        } finally {
            await this.knowledgeContext.reloadArticleIndex();
        }
    }
}
