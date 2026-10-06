// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useRenderCounter } from "@web/core/utils/render_instrumentation";

/**
 * @typedef {Object} Tag
 * @property {string|number} [id]
 * @property {string} [text]
 * @property {string} [title]
 * @property {string} [img]
 * @property {string} [imageClass]
 * @property {string} [icon]
 * @property {string} [className]
 * @property {number} [colorIndex]
 * @property {boolean} [canEdit]
 * @property {(ev: MouseEvent) => any} [onClick]
 * @property {(ev: MouseEvent) => any} [onDelete]
 */
const TAG_SHAPE = t.object({
    id: t.or([t.string(), t.number()]).optional(),
    text: t.string().optional(),
    title: t.string().optional(),
    img: t.or([t.string(), t.boolean()]).optional(),
    imageClass: t.string().optional(),
    icon: t.string().optional(),
    className: t.string().optional(),
    colorIndex: t.number().optional(),
    canEdit: t.boolean().optional(),
    onClick: t.function().optional(),
    onDelete: t.function().optional(),
});

export class TagsList extends Component {
    static template = "web.TagsList";
    static props = {
        displayText: t.boolean().optional(true),
        visibleItemsLimit: t.number().optional(),
        tags: t.array(TAG_SHAPE),
    };
    props = useProps(this.constructor.props);

    setup() {
        useRenderCounter("components.TagsList");
    }

    /**
     * @param {Tag} tag
     * @param {number} index
     * @returns {string | number}
     */
    tagKey(tag, index) {
        return /** @type {any} */ (tag).resId || tag.id || `index-${index}`;
    }

    /** @returns {number} */
    get splitIndex() {
        return this.props.visibleItemsLimit ? this.props.visibleItemsLimit - 1 : 0;
    }
    /** @returns {boolean} */
    get hasOverflow() {
        return Boolean(
            this.props.visibleItemsLimit &&
            this.props.tags.length > this.props.visibleItemsLimit,
        );
    }
    /** @returns {Object[]} */
    get visibleTags() {
        return this.hasOverflow
            ? this.props.tags.slice(0, this.splitIndex)
            : this.props.tags;
    }
    /** @returns {Record<string, any>[]} */
    get otherTags() {
        return this.hasOverflow ? this.props.tags.slice(this.splitIndex) : [];
    }
    /** @returns {string} */
    get tooltipInfo() {
        return JSON.stringify({
            tags: this.otherTags.map((tag) => ({
                text: tag.text,
                id: tag.id,
            })),
        });
    }
}
