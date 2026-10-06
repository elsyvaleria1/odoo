/** @odoo-module */

import { Component, t, useProps, xml } from "@odoo/owl";

import { Tag } from "../core/tag.js";
import { HootLink } from "./hoot_link.js";

/**
 * @typedef {{
 *  inert?: boolean;
 *  tag: Tag;
 * }} HootTagButtonProps
 */

/** @extends {Component<HootTagButtonProps, import("../hoot").Environment>} */
export class HootTagButton extends Component {
    static components = { HootLink };

    static props = { inert: t.boolean().optional(), tag: t.instanceOf(Tag) };
    props = useProps(this.constructor.props);

    static template = xml`
        <t t-if="this.props.inert">
            <span
                class="rounded-full px-2"
                t-att-style="this.style"
                t-att-title="this.title"
            >
                <small class="text-xs font-bold" t-out="this.props.tag.name" />
            </span>
        </t>
        <t t-else="">
            <HootLink
                ids="{ tag: this.props.tag.name }"
                class="'rounded-full px-2'"
                style="this.style"
                title="this.title"
            >
                <small class="text-xs font-bold hidden md:inline" t-out="this.props.tag.name" />
                <span class="md:hidden">&#8205;</span>
            </HootLink>
        </t>
    `;

    get style() {
        return `background-color: ${this.props.tag.color[0]}; color: ${this.props.tag.color[1]};`;
    }

    get title() {
        return `Tag ${this.props.tag.name}`;
    }
}
