/** @odoo-module */

import { Component, proxy, t, useProps, xml } from "@odoo/owl";

import {
    elementRef,
    useAutofocus,
    useHootKey,
    useWindowListener,
} from "../hoot_utils.js";

/**
 * @typedef {{
 *  buttonClassName?: string;
 *  className?: string;
 *  slots: Record<string, any>;
 * }} HootDropdownProps
 */

/** @extends {Component<HootDropdownProps, import("../hoot").Environment>} */
export class HootDropdown extends Component {
    static template = xml`
        <div class="${HootDropdown.name} relative" t-att-class="this.props.className" t-ref="this.rootRef">
            <button
                t-ref="this.togglerRef"
                class="flex rounded p-2 transition-colors"
                t-att-class="this.props.buttonClassName"
            >
                <t t-call-slot="toggler" open="this.state.open" />
            </button>
            <t t-if="this.state.open">
                <div
                    class="
                        hoot-dropdown absolute animate-slide-down
                        flex flex-col end-0 p-3 gap-2
                        bg-base text-base mt-1 shadow rounded z-2"
                >
                    <button class="fixed end-2 top-2 p-1 text-rose sm:hidden" t-on-click="() => this.state.open = false">
                        <i class="fa-solid fa-times w-5 h-5" />
                    </button>
                    <t t-call-slot="menu" open="this.state.open" />
                </div>
            </t>
        </div>
    `;
    static props = {
        buttonClassName: t.string().optional(),
        className: t.string().optional(),
        slots: t.object({ toggler: t.object(), menu: t.object() }),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.rootRef = elementRef();
        this.togglerRef = elementRef();
        this.state = proxy({
            open: false,
        });

        useAutofocus(this.rootRef);
        useHootKey(["Escape"], this.close);
        useWindowListener(
            "click",
            (ev) => {
                const path = ev.composedPath();
                if (!path.includes(this.rootRef.el)) {
                    this.state.open = false;
                } else if (path.includes(this.togglerRef.el)) {
                    this.state.open = !this.state.open;
                }
            },
            { capture: true },
        );
    }

    /** @param {KeyboardEvent} ev */
    close(ev) {
        if (this.state.open) {
            ev.preventDefault();
            this.state.open = false;
        }
    }
}
