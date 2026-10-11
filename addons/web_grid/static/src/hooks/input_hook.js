/** @odoo-module native */

import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export function useInputHook(params) {
    const ownRef = params.ref;
    const inputRef = params.ref || ownRef;

    let isDirty = false;

    let lastSetValue = null;

    function onInput(ev) {
        isDirty = ev.target.value !== lastSetValue;
        if (params.setDirty) {
            params.setDirty(isDirty);
        }
    }

    function onChange(ev) {
        if (isDirty) {
            isDirty = false;
            let isInvalid = false;
            let val = ev.target.value;
            if (params.parse) {
                try {
                    val = params.parse(val);
                } catch {
                    if (params.setInvalid) {
                        params.setInvalid();
                    }
                    isInvalid = true;
                }
            }

            if (!isInvalid) {
                params.notifyChange(val);
                lastSetValue = ev.target.value;
            }

            if (params.setDirty) {
                params.setDirty(isDirty);
            }
        }
    }
    function onKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (params.discard && hotkey === "escape") {
            params.discard();
        } else if (
            params.commitChanges &&
            ["enter", "tab", "shift+tab"].includes(hotkey)
        ) {
            commitChanges();
        }
        if (params.onKeyDown) {
            params.onKeyDown(ev);
        }
    }

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

    useLayoutEffect(() => {
        const isInvalid = params.isInvalid ? params.isInvalid() : false;
        if (inputRef.el && !isDirty && !isInvalid) {
            inputRef.el.value = params.getValue();
            lastSetValue = inputRef.el.value;
        }
    });

    function isUrgentSaved(urgent) {
        if (params.isUrgentSaved) {
            return params.isUrgentSaved(urgent);
        }
        return urgent;
    }

    async function commitChanges(urgent) {
        if (!inputRef.el) {
            return;
        }

        isDirty = inputRef.el.value !== lastSetValue;
        if (isDirty || isUrgentSaved(urgent)) {
            let isInvalid = false;
            isDirty = false;
            let val = inputRef.el.value;
            if (params.parse) {
                try {
                    val = params.parse(val);
                } catch {
                    isInvalid = true;
                    if (urgent) {
                        return;
                    } else {
                        params.setInvalid();
                    }
                }
            }

            if (isInvalid) {
                return;
            }

            const result = params.commitChanges(val);
            if (result) {
                lastSetValue = inputRef.el.value;
                if (params.setDirty) {
                    params.setDirty(isDirty);
                }
            }
        }
    }

    return inputRef;
}
