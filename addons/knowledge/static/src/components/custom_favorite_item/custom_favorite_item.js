/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { CustomFavoriteItem } from "@web/search/custom_favorite_item/custom_favorite_item";
import { useSearchModel } from "@web/search/search_model";

patch(CustomFavoriteItem.prototype, {
    setup() {
        super.setup(...arguments);
        this.searchModel = useSearchModel();
    },

    isKnowledgeEmbeddedView() {
        return (
            this.searchModel &&
            this.searchModel.context &&
            this.searchModel.context.knowledgeEmbeddedViewId
        );
    },

    async saveFavorite(ev) {
        return super.saveFavorite(ev, this.isKnowledgeEmbeddedView());
    },
});
