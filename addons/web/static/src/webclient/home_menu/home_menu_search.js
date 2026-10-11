// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { isMacOS } from "@web/core/browser/feature_detection";
import { makeLogger } from "@web/core/debug/debug_logger";
import { inputModality } from "@web/core/input_modality";
import { registry } from "@web/core/registry";
import { useMountedListener, useService } from "@web/core/utils/hooks";

class FooterComponent extends Component {
    static template = "web.HomeMenu.CommandPalette.Footer";
    static props = { switchNamespace: t.function().optional() };
    props = useProps(this.constructor.props);

    setup() {
        this.controlKey = isMacOS() ? "COMMAND" : "CONTROL";
    }
}

const log = makeLogger("web.home_menu.search");

/**
 * @param {{
 *  onQueryChanged: () => void,
 *  inputRef: import("@odoo/owl").Ref<HTMLElement>,
 * }} params
 */
export function useHomeMenuSearch({ onQueryChanged, inputRef }) {
    const command = useService("command");
    const ui = useService("ui");
    const state = proxy({ query: "" });
    let composing = false;

    /** @returns {HTMLInputElement | null} */
    const inputEl = () => /** @type {HTMLInputElement | null} */ (inputRef.el);

    const search = {
        get query() {
            return state.query;
        },

        get inputEl() {
            return inputEl();
        },

        focus() {
            const el = inputEl();
            if (el && !inputModality.isTouch) {
                el.focus({ preventScroll: true });
            }
        },

        clear() {
            state.query = "";
            const el = inputEl();
            if (el) {
                el.value = "";
            }
            onQueryChanged();
        },

        onInput() {
            if (composing) {
                return;
            }
            const typed = inputEl()?.value.trim() ?? "";
            if (!isNamespaced(typed)) {
                state.query = typed;
                onQueryChanged();
                return;
            }
            search.clear();
            handOverToPalette(command, typed, () => search.focus());
        },

        openPalette() {
            handOverToPalette(command, state.query, () => search.focus());
        },

        /** @param {FocusEvent} [ev] */
        onBlur(ev) {
            if (inputModality.isTouch) {
                return;
            }
            const target = ev?.relatedTarget;
            const focusedElsewhere = Boolean(target) && target !== document.body;
            browser.setTimeout(() => {
                const refocus =
                    !focusedElsewhere &&
                    document.activeElement === document.body &&
                    ui.activeElement === document;
                log.logic("blur", () => ({
                    refocus,
                    focusedElsewhere,
                    relatedTarget:
                        target instanceof Element
                            ? target.outerHTML.slice(0, 80)
                            : null,
                    activeElement: document.activeElement?.tagName,
                    uiActiveElement:
                        ui.activeElement === document ? "document" : "overlay",
                }));
                if (refocus) {
                    search.focus();
                }
            });
        },

        onCompositionStart() {
            composing = true;
        },
        onCompositionEnd() {
            composing = false;
            search.onInput();
        },
    };

    useTypeToFocus(inputRef, ui, () => search.focus());

    return search;
}

/** @param {string} typed */
function isNamespaced(typed) {
    return typed.length > 0 && registry.category("command_setup").contains(typed[0]);
}

/**
 * @param {import("services").ServiceFactories["command"]} command
 * @param {string} typed
 * @param {() => void} [refocus]
 */
function handOverToPalette(command, typed, refocus) {
    const searchValue = isNamespaced(typed) ? typed : `/${typed}`;
    command.openMainPalette(
        /** @type {any} */ ({ searchValue, FooterComponent }),
        refocus,
    );
}

/**
 * @param {import("@odoo/owl").Ref<HTMLElement>} inputRef
 * @param {import("services").ServiceFactories["ui"]} ui
 * @param {() => void} focus
 */
function useTypeToFocus(inputRef, ui, focus) {
    useMountedListener(window, "keydown", (/** @type {KeyboardEvent} */ ev) => {
        const printable =
            [...(ev.key ?? "")].length === 1 &&
            !ev.ctrlKey &&
            !ev.metaKey &&
            !ev.altKey;
        if (
            printable &&
            document.activeElement !== inputRef.el &&
            ui.activeElement === document &&
            !["TEXTAREA", "INPUT", "SELECT"].includes(
                document.activeElement?.tagName ?? "",
            ) &&
            !document.activeElement?.closest("[contenteditable=true]")
        ) {
            focus();
        }
    });
}
