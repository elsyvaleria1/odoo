/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useEventBus } from "@web/core/utils/hooks";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";
import { useSearchModel } from "@web/search/search_model";

const cogMenuRegistry = registry.category("cogMenu");

export class EmbeddedViewActionsMenu extends Component {
    static props = {};
    static template = "knowledge.EmbeddedViewActionsMenu";
    static components = { CogMenuItem };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.bus = useEventBus();
        this.searchModel = useSearchModel();
    }

    _onOpenEmbeddedView() {
        this.bus.trigger(
            `KNOWLEDGE_EMBEDDED_${this.searchModel.context.knowledgeEmbeddedViewId}:OPEN`,
        );
    }
    _onEditEmbeddedView() {
        this.bus.trigger(
            `KNOWLEDGE_EMBEDDED_${this.searchModel.context.knowledgeEmbeddedViewId}:EDIT`,
        );
    }
}

cogMenuRegistry.add("embedded-view-actions-menu", {
    Component: EmbeddedViewActionsMenu,
    groupNumber: COG_GROUP.APP,
    isDisplayed: (env) =>
        Boolean(env.searchModel.context.knowledgeEmbeddedViewId) &&
        !env.searchModel.context.isOpenedEmbeddedView,
});
