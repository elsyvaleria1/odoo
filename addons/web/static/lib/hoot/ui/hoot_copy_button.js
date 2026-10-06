/** @odoo-module */

import { Component, proxy, t, useProps, xml } from "@odoo/owl";

import { copy, hasClipboard } from "../hoot_utils.js";

/**
 * @typedef {{
 *  altText?: string;
 *  text: string;
 * }} HootCopyButtonProps
 */

/** @extends {Component<HootCopyButtonProps, import("../hoot").Environment>} */
export class HootCopyButton extends Component {
    static props = { altText: t.string().optional(), text: t.string() };
    props = useProps(this.constructor.props);

    static template = xml`
        <t t-if="this.hasClipboard()">
            <button
                type="button"
                class="text-gray-400 hover:text-gray-500"
                t-att-class="{ 'text-emerald': this.state.copied }"
                title="copy to clipboard"
                t-on-click.stop="this.onClick"
            >
                <i class="fa-solid fa-paste" />
            </button>
        </t>
    `;

    hasClipboard = hasClipboard;

    setup() {
        this.state = proxy({ copied: false });
    }

    /** @param {PointerEvent} ev */
    async onClick(ev) {
        const text =
            ev.altKey && this.props.altText ? this.props.altText : this.props.text;
        await copy(text);
        this.state.copied = true;
    }
}
