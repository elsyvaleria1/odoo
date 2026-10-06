/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    BooleanFavoriteField,
    booleanFavoriteField,
} from "@web/fields/basic/boolean_favorite/boolean_favorite_field";

export class DocumentFavoriteField extends BooleanFavoriteField {
    setup() {
        super.setup();
        this.documentService = useService("document.document");
    }

    async update() {
        if (this.props.readonly) {
            return;
        }
        const { record } = this.props;
        await this.documentService.toggleFavorite([record.resId]);
        await record.load();
        // a folder's star is also read from its search panel value (the cog)
        if (record.data.type === "folder") {
            await record.model.viewContext?.searchModel?._reloadSearchPanel?.();
        }
    }
}

export const documentFavoriteField = {
    ...booleanFavoriteField,
    component: DocumentFavoriteField,
};

registry.category("fields").add("document_favorite", documentFavoriteField);
