/** @odoo-module native */
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { useSearchModel } from "@web/search/search_model";
import { ListRenderer } from "@web/views/list";

patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        if (this.searchModel) {
            useBus(this.searchModel, "insert-embedded-view", (ev) => {
                Object.assign(ev.detail, {
                    orderBy: JSON.stringify(this.props.list.orderBy),
                    keyOptionalFields: this.keyOptionalFields,
                });
            });
        }
    },

    /**
     * @override
     * @returns {string}
     */
    createViewKey() {
        if (this.searchModel?.context.knowledgeEmbeddedViewId) {
            return `${super.createViewKey()},${this.searchModel.context.knowledgeEmbeddedViewId}`;
        }
        return super.createViewKey();
    },
});
