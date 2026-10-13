/** @odoo-module native */
import { HierarchyCard } from "@web_hierarchy/hierarchy_card";

export class KnowledgeHierarchyCard extends HierarchyCard {
    /** @override */
    getRenderingContext(data) {
        const context = super.getRenderingContext(data);
        return {
            ...context,
            isRoot: !this.props.node.parentNode,
        };
    }
}
