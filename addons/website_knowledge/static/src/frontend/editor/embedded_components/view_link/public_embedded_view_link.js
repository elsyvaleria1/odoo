/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { EMBEDDED_VIEW_LINK_STYLES } from "@knowledge/editor/embedded_components/core/embedded_view_link/embedded_view_link_style";
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, t, useProps } from "@odoo/owl";

export class PublicEmbeddedViewLinkComponent extends Component {
    static template = "knowledge.PublicEmbeddedViewLink";
    static props = { viewProps: t.object(), linkStyle: t.string().optional("link") };
    props = useProps(this.constructor.props);

    setup() {
        this.url = `/knowledge/article/${useKnowledgeContext().articleId}`;
    }

    getLinkClass() {
        return EMBEDDED_VIEW_LINK_STYLES[this.props.linkStyle].class;
    }
}

export const publicViewLinkEmbedding = {
    name: "viewLink",
    Component: PublicEmbeddedViewLinkComponent,
    getProps: (host) => ({ ...getEmbeddedProps(host) }),
};
