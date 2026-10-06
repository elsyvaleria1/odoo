// @ts-check
/** @odoo-module native */

import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { useAceEditor } from "@web/components/code_editor/ace_editor_hook";
import { loadAce } from "@web/core/lib/ace";
import { elementRef } from "@web/core/utils/element_ref";
/** @typedef {import("@web/components/code_editor/ace_editor_hook").CursorPosition} CursorPosition */
export class CodeEditor extends Component {
    static template = "web.CodeEditor";
    static props = {
        mode: t
            .customValidator(t.string(), (mode) => CodeEditor.MODES.includes(mode))
            .optional(),
        value: t.customValidator(t.any(), (v) => typeof v === "string").optional(""),
        readonly: t.boolean().optional(false),
        onChange: t.function().optional(() => () => {}),
        onBlur: t.function().optional(),
        class: t.string().optional(""),
        theme: t
            .customValidator(t.string(), (theme) => CodeEditor.THEMES.includes(theme))
            .optional(""),
        maxLines: t.number().optional(),
        sessionId: t.or([t.number(), t.string()]).optional(1),
        initialCursorPosition: t.object().optional(),
        showLineNumbers: t.boolean().optional(true),
    };

    /** @type {string[]} */
    static MODES = ["javascript", "xml", "qweb", "scss", "python", "json"];
    /** @type {string[]} */
    static THEMES = ["", "monokai"];
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    editorRef;
    /** @type {{ activeMode: string | undefined }} */
    state;
    /** @type {import("@web/components/code_editor/ace_editor_hook").AceEditorController} */
    controller;

    setup() {
        /** @type {import("@odoo/owl").Ref<HTMLElement>} */
        this.editorRef = elementRef();
        this.state = proxy({
            /** @type {string | undefined} */
            activeMode: undefined,
        });

        onWillStart(async () => {
            await loadAce();
        });

        this.controller = useAceEditor({
            ref: this.editorRef,
            getValue: () => this.props.value,
            getSessionId: () => this.props.sessionId,
            getMode: () => this.props.mode,
            getTheme: () => this.props.theme,
            isReadonly: () => this.props.readonly,
            showLineNumbers: () => this.props.showLineNumbers,
            getMaxLines: () => this.props.maxLines,
            onChange: (value, cursor) => this.props.onChange(value, cursor),
            onBlur: () => this.props.onBlur?.(),
            onModeChanged: (modeId) => {
                this.state.activeMode = modeId;
            },
            initialCursorPosition: this.props.initialCursorPosition,
        });
    }

    /** @returns {any} */
    get aceEditor() {
        return this.controller.editor;
    }
}
