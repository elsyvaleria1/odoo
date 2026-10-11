/** @odoo-module native */
import { Many2ManyTagsField } from "@web/fields/relational/many2many_tags";
import { useSearchModel } from "@web/search/search_model";

/**
 * @override update,
 */
export class DocumentsDetailsMany2ManyTagsField extends Many2ManyTagsField {
    static props = {
        ...Many2ManyTagsField.props,
        readonlyPlaceholder: Many2ManyTagsField.props.placeholder,
    };
    static template = "document.DocumentsDetailsPanelMany2ManyTagsField";

    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        const superUpdate = this.update;
        this.update = async (recordlist) => {
            const ret = await superUpdate(recordlist);
            await this._saveTags();
            return ret;
        };
        if (this.quickCreate) {
            const superQuickCreate = this.quickCreate;
            this.quickCreate = async (name) => {
                const ret = await superQuickCreate(name);
                await this._saveTags();
                return ret;
            };
        }
    }

    async removeTag(id) {
        await super.removeTag(id);
        await this._saveTags();
    }

    async _saveTags() {
        await this.props.record.save();
        if (
            this.props.record.isDetailsPanelRecord &&
            this.props.record.data.type === "folder"
        ) {
            await this.searchModel._reloadSearchPanel();
        }
    }
}
