/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, useProps } from "@odoo/owl";

export class ViewPlaceholderComponent extends Component {
    static template = "website_knowledge.ViewPlaceholder";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.url = `/knowledge/article/${useKnowledgeContext().articleId}`;
    }
}

export const viewPlaceholderEmbedding = {
    name: "view",
    Component: ViewPlaceholderComponent,
};
