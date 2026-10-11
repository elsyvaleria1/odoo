/** @odoo-module native */
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { ListController, listView } from "@web/views/list";
import { prepareStaticActionMenuItems } from "@web/views/view_utils";

export class KnowledgeArticleController extends ListController {
    setup() {
        super.setup();
        this.activeActions.create = false;
    }

    /**
     * @override
     */
    getStaticActionMenuItems() {
        return {
            ...super.getStaticActionMenuItems(),
            ...prepareStaticActionMenuItems({
                duplicate: {
                    isAvailable: () => this.hasSelectedRecords && user.isAdmin,
                    callback: () => this.duplicateSelectedArticles(),
                },
            }),
        };
    }

    async duplicateSelectedArticles() {
        const selectedResIds = await this.model.root.getResIds(true);
        const method = selectedResIds.length === 1 ? "copy" : "copy_batch";
        await this.model.orm.call(this.props.resModel, method, [selectedResIds]);
        await this.model.load();
    }
}

registry.category("views").add("knowledge_article_view_tree", {
    ...listView,
    Controller: KnowledgeArticleController,
});
