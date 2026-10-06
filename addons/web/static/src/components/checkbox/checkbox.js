// @ts-check
/** @odoo-module native */

import { Component, status, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useDebugMode } from "@web/core/debug/debug_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useSyncedInputProperty } from "@web/core/utils/hooks";

const log = makeLogger("web.components.checkbox");

export class CheckBox extends Component {
    static template = "web.CheckBox";
    static nextId = 1;
    static props = {
        id: t.any().optional(),
        disabled: t.boolean().optional(),
        value: t.boolean().optional(),
        slots: t.object().optional(),
        onChange: t.function().optional(() => () => {}),
        className: t.string().optional(),
        name: t.string().optional(),
        indeterminate: t.boolean().optional(),
        ariaLabel: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    rootRef;

    /** @type {() => boolean} */
    syncWithValue;

    setup() {
        this.debug = useDebugMode();
        this.id = `checkbox-comp-${CheckBox.nextId++}`;
        this.rootRef = elementRef();

        this.syncWithValue = useSyncedInputProperty(
            () => this.input,
            () => this.props.value,
            { property: "checked" },
        );

        useHotkey(
            "Enter",
            () => {
                if (this.props.disabled) {
                    return;
                }
                const input = this.input;
                if (!input) {
                    return;
                }
                this.toggle(input, !(this.props.value ?? input.checked));
            },
            {
                area: () => /** @type {HTMLElement} */ (this.rootRef.el),
                bypassEditableProtection: true,
            },
        );
    }

    /** @returns {HTMLInputElement | null} */
    get input() {
        return this.rootRef.el?.querySelector("input") ?? null;
    }
    /**
     * @param {HTMLInputElement} input
     * @param {boolean} checked
     */
    toggle(input, checked) {
        input.checked = checked;
        if (this.props.value === undefined) {
            this.props.onChange(checked);
            return;
        }
        let changed;
        try {
            changed = this.props.onChange(checked);
        } catch (error) {
            log.logic("onChange threw: resyncing anyway", () => ({ checked }));
            changed = Promise.reject(error);
        }
        Promise.resolve(changed).finally(() => this.resyncNextFrame());
    }

    async resyncNextFrame() {
        await new Promise((resolve) => browser.requestAnimationFrame(resolve));
        const destroyed = status(this) === "destroyed";
        const reverted = !destroyed && this.syncWithValue();
        log.logic("resync", () => ({ destroyed, reverted, value: this.props.value }));
        if (!reverted) {
            return;
        }
        if (!this.debug) {
            return;
        }
        browser.console.warn(
            "[CheckBox] reverted a click because `value` never moved. " +
                "Either the parent rejected the change, or it stored it " +
                "somewhere owl cannot see (a plain Set/Map/field instead " +
                "of `useState`) — in which case the model took the change " +
                "and only the box snapped back.",
        );
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        if (
            ev
                .composedPath()
                .some((el) =>
                    ["INPUT", "LABEL"].includes(/** @type {Element} */ (el).tagName),
                )
        ) {
            ev.stopPropagation();
            return;
        }

        const input = this.input;
        if (!input) {
            return;
        }
        input.focus();
        if (!this.props.disabled) {
            ev.stopPropagation();
            this.toggle(input, !input.checked);
        }
    }

    /** @param {Event} ev */
    onChange(ev) {
        if (this.props.disabled) {
            return;
        }
        const input = /** @type {HTMLInputElement} */ (ev.target);
        this.toggle(input, input.checked);
    }
}
