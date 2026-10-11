/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { ModelFieldSelector } from "@web/components/model_field_selector";
import { useDebugMode } from "@web/core/debug/debug_context";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";

export class StudioDynamicPlaceholderPopover extends Component {
    static template = "web_studio.StudioDynamicPlaceholderPopover";
    static components = { ModelFieldSelector };
    static props = {
        resModel: t.string(),
        availableQwebVariables: t.object(),
        close: t.function(),
        validate: t.function(),
        initialQwebVar: t.string(),
        showOnlyX2ManyFields: t.boolean(),
        initialPath: t.any().optional(false),
        initialLabelValue: t.any().optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.debug = useDebugMode();
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
        this.state = proxy({
            currentVar: this.props.initialQwebVar,
            path: this.props.initialPath || "",
            isPathSelected: false,
            labelValue: this.props.initialLabelValue || null,
        });
        this.fieldService = useService("field");
        useHotkey("Enter", () => this.validate(), { bypassEditableProtection: true });
        useHotkey("Escape", () => this.props.close(), {
            bypassEditableProtection: true,
        });

        onWillStart(async () => {
            if (this.state.path) {
                const fieldInfo = (
                    await this.fieldService.loadFieldInfo(
                        this.currentResModel,
                        this.state.path,
                    )
                ).fieldDef;
                this.fieldType = fieldInfo.type;
                this.state.fieldName = fieldInfo.string;
            }
        });
    }

    get labelValueInput() {
        const state = this.state;
        const lv = state.labelValue;
        return (lv !== null ? lv : state.fieldName) || "";
    }
    onLabelInput(ev) {
        const val = ev.target.value;
        this.state.labelValue = val;
    }

    filter(fieldDef) {
        if (this.props.showOnlyX2ManyFields) {
            return ["one2many", "many2many"].includes(fieldDef.type);
        } else {
            return !["one2many", "boolean", "many2many"].includes(fieldDef.type);
        }
    }

    async validate() {
        const resModel = this.currentResModel;
        const fieldInfo = (
            await this.fieldService.loadFieldInfo(resModel, this.state.path)
        ).fieldDef;
        if (!fieldInfo) {
            return;
        }
        const filename_exists = (
            await this.fieldService.loadFieldInfo(
                resModel,
                this.state.path + "_filename",
            )
        ).fieldDef;
        const is_image = fieldInfo.type === "binary" && !filename_exists;
        this.props.validate(
            this.state.currentVar,
            this.state.path,
            this.labelValueInput,
            is_image,
            fieldInfo.relation,
            fieldInfo.string,
        );
        this.props.close();
    }

    setPath(path, { fieldDef }) {
        this.state.path = path;
        this.state.fieldName = fieldDef?.string;
        this.fieldType = fieldDef?.type;
    }

    get currentModel() {
        const currentVar = this.state.currentVar;
        const model = currentVar && this.props.availableQwebVariables[currentVar];
        return model || {};
    }

    get currentResModel() {
        const resModel = this.currentModel.model;
        return resModel || this.props.resModel;
    }
}
