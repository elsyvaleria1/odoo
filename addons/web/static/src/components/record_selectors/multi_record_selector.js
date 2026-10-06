// @ts-check
/** @odoo-module native */

import { proxy, t } from "@odoo/owl";
import { tagAvatar } from "@web/components/record_selectors/avatar_models";
import { TagsList } from "@web/components/tags_list/tags_list";
import { elementRef } from "@web/core/utils/element_ref";

import { BaseRecordSelector, displayNameFor } from "./base_record_selector.js";
import { RecordAutocomplete } from "./record_autocomplete.js";
import { useTagNavigation } from "./tag_navigation_hook.js";

/**
 * @typedef {{ id?: number, text: string, onDelete: Function, img: string | false,
 * colorIndex?: number, canEdit?: boolean }} RecordTag
 */
/** @typedef {{ resIds: number[], [key: string]: any }} MultiRecordSelectorProps */

export class MultiRecordSelector extends BaseRecordSelector {
    /** @type {Record<string, any>} */
    static props = {
        resIds: t.array(t.number()),
        resModel: t.string(),
        update: t.function(),
        domain: t.array().optional(),
        context: t.object().optional(),
        fieldString: t.string().optional(),
        placeholder: t.string().optional(),
    };
    static components = { RecordAutocomplete, TagsList };
    static template = "web.MultiRecordSelector";

    /** @type {{ tags: RecordTag[] }} */
    state;

    setup() {
        super.setup();
        this.state = proxy({ tags: [] });
        this.multiRecordSelectorRef = elementRef();
        useTagNavigation(this.multiRecordSelectorRef, {
            delete: (index) => this.removeTagAt(index),
        });
    }

    /** @returns {RecordTag[]} */
    get tags() {
        return this.state.tags;
    }

    /**
     * @param {MultiRecordSelectorProps} props
     * @param {Record<number, string>} displayNames
     */
    applyDisplayNames(props, displayNames) {
        this.state.tags = this.getTags(props, displayNames);
    }

    /** @returns {string | undefined} */
    get placeholder() {
        return this.props.resIds.length ? "" : this.props.placeholder;
    }

    /**
     * @param {MultiRecordSelectorProps} [props]
     * @returns {number[]}
     */
    getIds(props = this.props) {
        return props.resIds;
    }

    /**
     * @param {MultiRecordSelectorProps} props
     * @param {Record<number, string>} displayNames
     * @returns {RecordTag[]}
     */
    getTags(props, displayNames) {
        return props.resIds.map((id) => ({
            id,
            text: displayNameFor(displayNames, id),
            onDelete: () => {
                this.removeTag(id);
            },
            img: tagAvatar(props.resModel, id),
        }));
    }

    /** @param {number} resId */
    removeTag(resId) {
        const props = /** @type {MultiRecordSelectorProps} */ (this.props);
        props.update(props.resIds.filter((id) => id !== resId));
    }

    /** @param {number} index */
    removeTagAt(index) {
        this.state.tags[index]?.onDelete();
    }

    /** @param {number[]} resIds */
    update(resIds) {
        if (!resIds.length) {
            return;
        }
        this.props.update([...this.props.resIds, ...resIds]);
    }
}
