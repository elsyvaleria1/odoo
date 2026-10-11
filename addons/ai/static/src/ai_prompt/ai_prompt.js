/** @odoo-module native */
import {
    AI_FIELD_SELECTOR,
    AIFieldSelectorPlugin,
} from "@ai/ai_prompt/ai_field_selector_plugin";
import {
    AI_RECORD_SELECTOR,
    AIRecordsSelectorPlugin,
} from "@ai/ai_prompt/ai_records_selector_plugin";
import { FeffPlugin } from "@html_editor/main/feff_plugin";
import { HintPlugin } from "@html_editor/main/hint_plugin";
import { PlaceholderPlugin } from "@html_editor/main/placeholder_plugin";
import { PowerboxPlugin } from "@html_editor/main/powerbox/powerbox_plugin";
import { SearchPowerboxPlugin } from "@html_editor/main/powerbox/search_powerbox_plugin";
import { CORE_PLUGINS } from "@html_editor/plugin_sets";
import { childNodeIndex } from "@html_editor/utils/position";
import { withSequence } from "@html_editor/utils/resource";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { Component, markup, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { localization } from "@web/core/l10n/localization";
import { isHtmlEmpty } from "@web/core/utils/dom/html";
import { Dialog } from "@web/ui/dialog";

export class AiPrompt extends Component {
    static template = "ai.AiPrompt";
    static components = { Wysiwyg };
    static props = {
        comodel: t.string().optional(),
        domain: t.string().optional(),
        model: t.string().optional(),
        onChange: t.function().optional(),
        placeholder: t.string().optional(),
        prompt: t.string(),
        readonly: t.boolean().optional(),
        aiFieldPath: t.string().optional(),
        missingRecordsWarning: t.string().optional(),
        updatePrompt: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.state = proxy({
            key: 0,
            hasRecords: this.props.prompt.includes("data-ai-record"),
        });
        this.lastValue = this.props.prompt;

        onWillUpdateProps((newProps) => {
            if (
                (newProps.prompt || "").toString() !== (this.lastValue || "").toString()
            ) {
                this.lastValue = newProps.prompt;
                this.state.key++;
            } else if (
                newProps.comodel !== this.props.comodel ||
                newProps.domain !== this.props.domain
            ) {
                this.state.key++;
            }
        });
    }

    get content() {
        const elContent = this.editor.getElContent();
        if (isHtmlEmpty(elContent.innerText)) {
            return "";
        }
        return elContent.innerHTML;
    }

    get hasRecords() {
        return Boolean(this.editor.getElContent().querySelector(AI_RECORD_SELECTOR));
    }

    get missingRecordsWarning() {
        return (
            this.props.comodel &&
            !this.state.hasRecords &&
            this.props.missingRecordsWarning
        );
    }

    get value() {
        return markup(this.props.prompt || "<p><br></p>");
    }

    getConfig() {
        return {
            content: this.value,
            debug: !!this.debug,
            direction: localization.direction || "ltr",
            aiFieldPath: this.props.aiFieldPath,
            fieldSelectorResModel: this.props.model,
            getRecordInfo: () => {
                const { resModel, resId } = this.props.record;
                return { resModel, resId };
            },
            onChange: () => this.onChange(),
            onEditorReady: () => (this.state.hasRecords = this.hasRecords),
            placeholder: this.props.placeholder,
            Plugins: [
                ...CORE_PLUGINS,
                AIFieldSelectorPlugin,
                AIRecordsSelectorPlugin,
                FeffPlugin,
                HintPlugin,
                PlaceholderPlugin,
                PowerboxPlugin,
                SearchPowerboxPlugin,
            ],
            baseContainers: ["DIV"],
            recordsSelectorDomain: this.props.domain,
            recordsSelectorResModel: this.props.comodel,
            resources: {
                hints: [
                    withSequence(20, {
                        selector: ".odoo-editor-editable > p:only-child",
                        text: this.props.placeholder,
                    }),
                ],
            },
        };
    }

    onBlur() {
        const content = this.content;
        if (content !== this.lastValue) {
            this.props.updatePrompt(this.content);
            this.lastValue = content;
        }
    }

    onChange() {
        this.state.hasRecords = this.hasRecords;
        this.props.onChange?.();
    }

    onClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const target = ev.target?.closest(
            `${AI_FIELD_SELECTOR}, ${AI_RECORD_SELECTOR}`,
        );
        if (!target) {
            return;
        }
        this.editor.shared.selection.setSelection({
            anchorNode: target.parentElement,
            anchorOffset: childNodeIndex(target),
            focusOffset: childNodeIndex(target) + 1,
        });
        if (target.matches(AI_FIELD_SELECTOR)) {
            this.editor.shared.AIFieldSelector.open([target.dataset.aiField]);
        } else if (this.props.comodel) {
            this.editor.shared.AIRecordsSelector.open([
                Number(target.dataset.aiRecordId),
            ]);
        }
    }

    onEditorLoad(editor) {
        this.editor = editor;
    }
}

export class AiPromptDialog extends Component {
    static template = "ai.AiPromptDialog";
    static components = { Dialog, AiPrompt };
    static props = {
        aiPromptProps: t.object(),
        close: t.function(),
        confirm: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.confirmVals = { prompt: this.props.aiPromptProps.prompt };
    }

    get aiPromptProps() {
        return {
            ...this.props.aiPromptProps,
            updatePrompt: (prompt) => (this.confirmVals.prompt = prompt),
        };
    }

    confirm() {
        this.props.confirm(this.confirmVals.prompt);
        this.props.close();
    }
}
