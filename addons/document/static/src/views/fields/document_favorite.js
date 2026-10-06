/** @odoo-module native */
import { registry } from "@web/core/registry";
import {
    BooleanFavoriteField,
    booleanFavoriteField,
} from "@web/fields/basic/boolean_favorite/boolean_favorite_field";

export class DocumentFavoriteField extends BooleanFavoriteField {
    async update() {
        if (!this.props.readonly) {
            await this.props.record.model.toggleFavorite([this.props.record.resId]);
        }
    }
}

export const documentFavoriteField = {
    ...booleanFavoriteField,
    component: DocumentFavoriteField,
};

registry.category("fields").add("document_favorite", documentFavoriteField);
