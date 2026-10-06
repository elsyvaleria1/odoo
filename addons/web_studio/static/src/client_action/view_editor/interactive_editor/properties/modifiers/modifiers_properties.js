/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { ExpressionEditorDialog } from "@web/components/expression_editor_dialog";
import { useOwnedDialogs } from "@web/core/utils/hooks";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class ModifiersProperties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Modifiers";
    static components = { CheckBox };
    static props = { node: t.object(), availableOptions: t.array() };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.addDialog = useOwnedDialogs();
    }

    /**
     * @param {string} name of the attribute
     * @returns if this attribute supported in the current view
     */
    isAttributeSupported(name) {
        return this.props.availableOptions?.includes(name);
    }

    // <tag invisible="EXPRESSION"  />
    onChangeModifier(name, value) {
        const isTypeBoolean = typeof value === "boolean";
        const encodesBoolean = isTypeBoolean || this.isBooleanExpression(value);
        const isTruthy = encodesBoolean ? this.isBoolTrue(value) : !!value;
        const newAttrs = {};
        const oldAttrs = { ...this.props.node.attrs };

        const changingInvisible = name === "invisible";
        const isInList = this.viewEditorModel.viewType === "list";

        if (encodesBoolean) {
            if (changingInvisible && isInList) {
                if (isTruthy) {
                    newAttrs["column_invisible"] = "True";
                } else {
                    newAttrs["column_invisible"] = "False";
                    newAttrs["invisible"] = "False";
                }
            } else {
                newAttrs[name] = isTruthy ? "True" : "False";
            }
        } else {
            newAttrs[name] = value;
            if (changingInvisible && isInList && "column_invisible" in oldAttrs) {
                newAttrs["column_invisible"] = "False";
            }
        }

        if (this.viewEditorModel.viewType === "form" && name === "readonly") {
            newAttrs.force_save = isTruthy ? "1" : "0";
        }

        const operation = {
            new_attrs: newAttrs,
            type: "attributes",
            position: "attributes",
            target: this.viewEditorModel.getFullTarget(
                this.viewEditorModel.activeNodeXpath,
            ),
        };
        return this.viewEditorModel.doOperation(operation);
    }

    isIndeterminate(value) {
        return value && !this.isBooleanExpression(value);
    }

    isBooleanExpression(expression) {
        return ["1", "0", "True", "true", "False", "false"].includes(expression);
    }

    isBoolTrue(value) {
        if (typeof value === "boolean") {
            return value;
        }
        return ["1", "True", "true"].includes(value);
    }

    valueAsBoolean(expression) {
        if (!expression) {
            return false;
        }
        if (this.isBooleanExpression(expression)) {
            return this.isBoolTrue(expression);
        }
        return true;
    }

    onConditionalButtonClicked(name, value) {
        if (typeof value !== "string" || value === "") {
            value = "False"; // See py.js:evaluateBooleanExpr default value is False
        }
        const { fields, resModel } = this.viewEditorModel;
        this.addDialog(ExpressionEditorDialog, {
            resModel,
            fields,
            expression: value,
            onConfirm: (expression) => this.onChangeModifier(name, expression),
        });
    }
}
