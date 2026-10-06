/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { SearchBarMenu } from "@web/search/search_bar_menu/search_bar_menu";
import { ConfirmationDialog } from "@web/ui/dialog";

patch(SearchBarMenu.prototype, {
    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.dialogService = useService("dialog");
    },
    onDeleteKnowledgeFavoriteItem(itemId) {
        const dialogProps = {
            title: _t("Warning"),
            body: _t("This filter is global and will be removed for everyone."),
            confirmLabel: _t("Delete Filter"),
            confirm: () => this.searchModel.deleteFavorite?.(itemId),
            cancel: () => {},
        };
        this.dialogService.add(ConfirmationDialog, dialogProps);
    },
});
