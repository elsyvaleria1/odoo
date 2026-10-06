/** @odoo-module native */
import { _t } from "@web/core/translation";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";

export const AiDocumentsControllerMixin = () => ({
    async onClickAutoSort() {
        const documentsIds = this.aiSortableDocuments().map((r) => r.data.id);
        const action = await this.orm.call("document.document", "action_ai_sort", [
            documentsIds,
        ]);
        if (action) {
            this.actionService.doAction(action);
        }
        this.documentService.reload();
    },

    aiSortableDocuments() {
        return this.model.targetRecords.filter((r) => r.data.ai_sortable);
    },

    getTopBarActionMenuItems() {
        const menuItems = super.getTopBarActionMenuItems();
        return {
            ...menuItems,
            aiAutoSort: {
                isAvailable: () =>
                    this.searchModel.getSelectedFolder()?.ai_has_sort_prompt &&
                    this.aiSortableDocuments().length,
                sequence: 30,
                description: _t("Sort with AI"),
                icon: "fa-solid fa-wand-magic-sparkles",
                callback: async () => this.onClickAutoSort(),
                groupNumber: COG_GROUP.APP,
            },
        };
    },
});
