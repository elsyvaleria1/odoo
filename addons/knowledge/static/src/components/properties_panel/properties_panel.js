/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { PropertiesField } from "@web/fields/specialized/properties";
import { standardWidgetProps } from "@web/views/widgets";

export class KnowledgeArticleProperties extends Component {
    static template = "knowledge.KnowledgeArticleProperties";
    static props = { ...standardWidgetProps };
    static components = { PropertiesField };
    props = useProps(this.constructor.props);

    setup() {
        this.knowledgeContext = useKnowledgeContext();
        this.state = proxy(this.knowledgeContext.propertiesPanelState);
        this.ui = useService("ui");
        useLayoutEffect(
            () => {
                if (!this.ui.isSmall && this.hasProperties && !this.state.isDisplayed) {
                    this.state.isDisplayed = true;
                } else if (this.state.isDisplayed && !this.hasProperties) {
                    this.state.isDisplayed = false;
                }
            },
            () => [this.props.record.resId, this.hasProperties],
        );
        onWillStart(
            async () => (this.userIsInternal = await user.hasGroup("base.group_user")),
        );
    }

    get hasProperties() {
        return this.props.record.data.article_properties.some(
            (prop) => !prop.definition_deleted,
        );
    }
}

export const knowledgePropertiesPanel = {
    component: KnowledgeArticleProperties,
    additionalClasses: ["col-12", "col-lg-2", "p-0", "position-relative", "border-top"],
    fieldDependencies: [{ name: "article_properties", type: "jsonb" }],
};

registry
    .category("view_widgets")
    .add("knowledge_properties_panel", knowledgePropertiesPanel);
