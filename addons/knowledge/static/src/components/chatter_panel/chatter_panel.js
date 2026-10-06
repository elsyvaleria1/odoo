/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { Component, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SIZES } from "@web/ui/viewport";
import { standardWidgetProps } from "@web/views/widgets";

export class KnowledgeArticleChatter extends Component {
    static template = "knowledge.KnowledgeArticleChatter";
    static components = { Chatter: WebChatter };
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.knowledgeContext = useKnowledgeContext();
        this.state = proxy(this.knowledgeContext.chatterPanelState);
        this.ui = useService("ui");
    }

    get isChatterAside() {
        return this.ui.size >= SIZES.LG;
    }
}

export const knowledgeChatterPanel = {
    component: KnowledgeArticleChatter,
    additionalClasses: ["border-top", "col-12", "col-lg-4", "position-relative", "p-0"],
};

registry.category("view_widgets").add("knowledge_chatter_panel", knowledgeChatterPanel);
