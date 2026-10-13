/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { EmbeddedControllersPatch } from "@knowledge/views/embedded_controllers_patch";
import { registry } from "@web/core/registry";
import { ListController, listView } from "@web/views/list";

export class KnowledgeArticleItemsListController extends EmbeddedControllersPatch(
    ListController,
) {
    /** @override */
    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        if (
            !("isEmbeddedReadonly" in this.knowledgeContext) ||
            this.knowledgeContext.isEmbeddedReadonly
        ) {
            this.activeActions.create = false;
        }
    }
}

registry.category("views").add("knowledge_article_view_tree_embedded", {
    ...listView,
    Controller: KnowledgeArticleItemsListController,
});
