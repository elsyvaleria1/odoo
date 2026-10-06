// @ts-check
/** @odoo-module native */

import { untrack, useEffect, useProps } from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { ParseError } from "@web/core/parse_error";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useRender } from "@web/core/utils/render_hooks";
import { useFieldDirtySignal } from "@web/fields/field_dirty_signal";
import { useFieldFlush } from "@web/fields/hooks/debounced_field_commit";

const log = makeLogger("web.field.input");

/**
 * @typedef InputFieldContext
 * @property {Record<string, any>} props
 * @property {any} params
 * @property {{ el: HTMLInputElement | HTMLTextAreaElement | null }} inputRef
 * @property {string} fieldName
 * @property {() => boolean} shouldSave
 * @property {(isDirty: boolean) => void} setFieldDirty
 * @property {{
 * isDirty: boolean,
 * lastSetValue: string | null,
 * }} edit
 */

/** @param {InputFieldContext} ctx */
function syncDirtyFromInput(ctx) {
    const { inputRef, edit } = ctx;
    ctx.setFieldDirty(Boolean(inputRef.el && inputRef.el.value !== edit.lastSetValue));
}

/**
 * @param {InputFieldContext} ctx
 * @param {boolean} [urgent]
 * @returns {Promise<void>}
 */
async function commitInputChanges(ctx, urgent) {
    const { props, params, inputRef, fieldName, edit } = ctx;
    if (!inputRef.el) {
        return;
    }

    if (urgent) {
        await commitUrgently(ctx);
        return;
    }

    edit.isDirty = inputRef.el.value !== edit.lastSetValue;
    if (!edit.isDirty) {
        return;
    }
    edit.isDirty = false;

    let value = inputRef.el.value;
    if (params.parse) {
        try {
            value = params.parse(value);
        } catch (error) {
            props.record.setInvalidField(fieldName);
            if (!(error instanceof ParseError)) {
                console.error(
                    `[useInputField] parsing "${fieldName}" threw a non-ParseError; ` +
                        `this is a widget defect, not invalid user input:`,
                    error,
                );
            }
            return;
        }
    }

    const current = props.record.data[fieldName];
    if ((value ?? false) === (current ?? false)) {
        inputRef.el.value = params.getValue();
        edit.lastSetValue = inputRef.el.value;
        syncDirtyFromInput(ctx);
        return;
    }

    edit.lastSetValue = inputRef.el.value;
    try {
        await props.record.update({ [fieldName]: value }, { save: ctx.shouldSave() });
    } finally {
        syncDirtyFromInput(ctx);
    }
}

/**
 * @param {InputFieldContext} ctx
 * @returns {Promise<void>}
 */
async function commitUrgently(ctx) {
    const { props, params, inputRef, fieldName } = ctx;
    if (!inputRef.el) {
        return;
    }
    let value = inputRef.el.value;
    if (params.parse) {
        try {
            value = params.parse(value);
        } catch (error) {
            log.logic("commitUrgently unparseable", () => ({
                fieldName,
                parseError: error instanceof ParseError,
            }));
            await props.record.setInvalidField(fieldName);
            return;
        }
    }
    const unchanged = (value ?? false) === (props.record.data[fieldName] ?? false);
    log.logic("commitUrgently", () => ({ fieldName, unchanged }));
    if (unchanged) {
        return;
    }
    await props.record.update({ [fieldName]: value }, { save: false });
}

/** @param {InputFieldContext} ctx */
function bindInputListeners(ctx) {
    const { props, params, inputRef, fieldName, edit } = ctx;

    const onInput = (/** @type {any} */ ev) => {
        edit.isDirty = ev.target.value !== edit.lastSetValue;
        if (params.preventLineBreaks && ev.inputType === "insertFromPaste") {
            ev.target.value = ev.target.value.replace(/[\r\n]+/g, " ");
        }
        ctx.setFieldDirty(edit.isDirty);
        if (!props.record.isValid) {
            props.record.resetFieldValidity(fieldName);
        }
    };
    const onChange = () => commitInputChanges(ctx, false);
    const onKeydown = (/** @type {any} */ ev) => {
        const hotkey = getActiveHotkey(ev);
        const keys = ["tab", "shift+tab"];
        if (ev.target.tagName.toLowerCase() !== "textarea") {
            keys.push("enter");
        }
        if (keys.includes(hotkey)) {
            commitInputChanges(ctx, false);
        }
        if (params.preventLineBreaks && ["enter", "shift+enter"].includes(hotkey)) {
            ev.preventDefault();
        }
    };

    useLayoutEffect(
        (inputEl) => {
            if (inputEl) {
                inputEl.addEventListener("input", onInput);
                inputEl.addEventListener("change", onChange);
                inputEl.addEventListener("keydown", onKeydown);
                return () => {
                    inputEl.removeEventListener("input", onInput);
                    inputEl.removeEventListener("change", onChange);
                    inputEl.removeEventListener("keydown", onKeydown);
                };
            }
        },
        () => [inputRef.el],
    );
}

/**
 * @param {Object} params
 * @param {() => string} params.getValue
 * @param {(value: string) => any} [params.parse]
 * @param {{ el: HTMLInputElement | HTMLTextAreaElement | null }} [params.ref]
 * @param {string} [params.refName="input"]
 * @param {boolean} [params.preventLineBreaks]
 * @param {string | null} [params.fieldName]
 * @param {() => boolean} [params.shouldSave]
 * @returns {{ el: HTMLInputElement | HTMLTextAreaElement | null }}
 */
export function useInputField(params) {
    const inputRef = params.ref;
    const props = useProps();

    const fieldName = "fieldName" in params ? params.fieldName : props.name;
    if (!fieldName) {
        return inputRef;
    }

    /** @type {InputFieldContext} */
    const ctx = {
        props,
        params,
        inputRef,
        fieldName,
        shouldSave: params.shouldSave ?? (() => false),
        setFieldDirty: useFieldDirtySignal(),
        edit: { isDirty: false, lastSetValue: null },
    };

    bindInputListeners(ctx);

    const syncInput = () => {
        const el = inputRef.el;
        if (!el) {
            return false;
        }
        const value = params.getValue();
        if (ctx.edit.isDirty || props.record.isFieldInvalid(fieldName)) {
            return false;
        }
        const changed = el.value !== value;
        if (changed) {
            const { selectionStart, selectionEnd, value: previousValue } = el;
            const wasFullySelected =
                selectionStart === 0 && selectionEnd === previousValue.length;
            el.value = value;
            if (wasFullySelected && document.activeElement === el) {
                el.select();
            }
        }
        ctx.edit.lastSetValue = el.value;
        return changed;
    };
    // at mount and patch, in hook order: a hook registered after this one (an
    // autoresize) measures the input once it holds its value
    useLayoutEffect(() => {
        syncInput();
    });
    // and tracked, since the field does not re-render when only its record
    // changed; the input is read first because the first run is in setup,
    // before the field has built what getValue() reads. A value it changes
    // renders the field, as a record change did in OWL 2, so that its patch
    // hooks (an autoresize) see the new value
    const render = useRender();
    useEffect(() => {
        if (syncInput()) {
            untrack(() => render());
        }
    });

    useFieldFlush(props.record.model.bus, (ev, urgent) => {
        ev.detail?.proms?.push(commitInputChanges(ctx, urgent));
    });

    return inputRef;
}
