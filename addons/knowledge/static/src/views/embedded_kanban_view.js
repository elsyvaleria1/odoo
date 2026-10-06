/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { EmbeddedControllersPatch } from "@knowledge/views/embedded_controllers_patch";
import { registry } from "@web/core/registry";
import { KanbanController, kanbanView } from "@web/views/kanban";

export class KnowledgeArticleItemsKanbanController extends EmbeddedControllersPatch(
    KanbanController,
) {
    /**
     * @override
     * Some actions require write access on the parent article. Disable those actions if the user
     * does not have it.
     */
    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        if (
            !("isEmbeddedReadonly" in this.knowledgeContext) ||
            this.knowledgeContext.isEmbeddedReadonly
        ) {
            ["create", "createGroup", "deleteGroup", "editGroup"].forEach(
                (action) => (this.props.archInfo.activeActions[action] = false),
            );
            this.props.archInfo.groupsDraggable = false;
            this.props.archInfo.activeActions.quickCreate = false;
        }
    }
}

registry.category("views").add("knowledge_article_view_kanban_embedded", {
    ...kanbanView,
    Controller: KnowledgeArticleItemsKanbanController,
});
