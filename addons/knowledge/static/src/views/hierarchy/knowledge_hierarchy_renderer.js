/** @odoo-module native */
import { KnowledgeHierarchyCard } from "@knowledge/views/hierarchy/knowledge_hierarchy_card";
import { HierarchyRenderer } from "@web_hierarchy/hierarchy_renderer";

export class KnowledgeHierarchyRenderer extends HierarchyRenderer {
    static components = {
        ...HierarchyRenderer.components,
        HierarchyCard: KnowledgeHierarchyCard,
    };
}
