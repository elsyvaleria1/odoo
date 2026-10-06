/** @odoo-module native */
import { KnowledgeHierarchyModel } from "@knowledge/views/hierarchy/knowledge_hierarchy_model";
import { KnowledgeHierarchyRenderer } from "@knowledge/views/hierarchy/knowledge_hierarchy_renderer";
import { registry } from "@web/core/registry";
import { hierarchyView } from "@web_hierarchy/hierarchy_view";

export const KnowledgeHierarchyView = {
    ...hierarchyView,
    Model: KnowledgeHierarchyModel,
    Renderer: KnowledgeHierarchyRenderer,
    searchMenuTypes: ["filter", "favorite"],
};

registry.category("views").add("knowledge_hierarchy", KnowledgeHierarchyView);
