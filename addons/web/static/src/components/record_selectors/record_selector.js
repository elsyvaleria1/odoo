// @ts-check
/** @odoo-module native */

import { proxy, t } from "@odoo/owl";
import { avatarUrl } from "@web/components/record_selectors/avatar_models";
import { isId } from "@web/core/tree/utils";

import { BaseRecordSelector, displayNameFor } from "./base_record_selector.js";
import { RecordAutocomplete } from "./record_autocomplete.js";

export class RecordSelector extends BaseRecordSelector {
    static props = {
        resId: t.or([t.number(), t.literal(false)]),
        resModel: t.string(),
        update: t.function(),
        domain: t.array().optional(),
        context: t.object().optional(),
        fieldString: t.string().optional(),
        placeholder: t.string().optional(),
    };
    static components = { RecordAutocomplete };
    static template = "web.RecordSelector";

    /** @type {{ displayName: string }} */
    state;

    setup() {
        super.setup();
        this.state = proxy({ displayName: "" });
    }

    /** @returns {boolean} */
    get hasAvatarImg() {
        return this.isAvatarModel && isId(this.props.resId);
    }

    /** @returns {string} */
    get avatarUrl() {
        return avatarUrl(this.props.resModel, this.props.resId);
    }

    /** @returns {string} */
    get displayName() {
        return this.state.displayName;
    }

    /**
     * @param {Record<string, any>} props
     * @param {Record<number, string>} displayNames
     */
    applyDisplayNames(props, displayNames) {
        this.state.displayName = this.getDisplayName(props, displayNames);
    }

    /**
     * @param {Record<string, any>} props
     * @param {Record<number, string>} displayNames
     * @returns {string}
     */
    getDisplayName(props, displayNames) {
        const { resId } = props;
        return resId === false ? "" : displayNameFor(displayNames, resId);
    }

    /**
     * @param {Record<string, any>} [props]
     * @returns {number[]}
     */
    getIds(props = this.props) {
        if (props.resId) {
            return [props.resId];
        }
        return [];
    }

    /** @param {number[]} resIds */
    update(resIds) {
        this.props.update(resIds[0] || false);
    }
}
