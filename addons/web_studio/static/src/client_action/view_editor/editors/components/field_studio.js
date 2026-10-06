/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useViewConfig } from "@web/core/view_config_hooks";
import { Field } from "@web/fields/field";
import {
    studioIsVisible,
    useStudioRef,
} from "@web_studio/client_action/view_editor/editors/utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { FieldContentOverlay } from "./field_content_overlay.js";

/*
 * Field:
 * - Displays an Overlay for X2Many fields
 * - handles invisible
 */
export class FieldStudio extends Field {
    static components = { ...Field.components, FieldContentOverlay };
    static template = "web_studio.Field";
    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
        this.config = useViewConfig();
        this.state = proxy({
            displayOverlay: false,
        });
        this.rootRefRef = elementRef();
        useStudioRef(this.rootRefRef, this.onClick.bind(this));
    }
    get fieldComponentProps() {
        const fieldComponentProps = super.fieldComponentProps;
        if (this.type === "kanban.many2one_avatar_user") {
            // This field must be visible, even when dealing without a record
            fieldComponentProps.readonly = false;
        }
        delete fieldComponentProps.studioXpath;
        delete fieldComponentProps.hasEmptyPlaceholder;
        delete fieldComponentProps.hasLabel;
        delete fieldComponentProps.studioIsVisible;
        return fieldComponentProps;
    }
    get classNames() {
        const classNames = super.classNames;
        classNames["o_web_studio_show_invisible"] = !studioIsVisible(this.props);
        classNames["o-web-studio-editor--element-clickable"] = !!this.props.studioXpath;
        if (this.studioIsEmpty()) {
            delete classNames["o_field_empty"];
            classNames["o_web_studio_widget_empty"] = true;
            classNames["text-muted"] = true;
        }
        return classNames;
    }

    studioIsEmpty() {
        const { name, record, hasLabel } = this.props;
        if (hasLabel) {
            return false;
        }
        if (this.type === "kanban.many2one_avatar_user") {
            return false; // The widget has its own visibility when empty
        }
        return "isEmpty" in this.field
            ? this.field.isEmpty(record, name)
            : !record.data[name];
    }

    getEmptyPlaceholder() {
        const { hasEmptyPlaceholder, name, record, fieldInfo } = this.props;
        if (!hasEmptyPlaceholder) {
            return false;
        }
        return this.studioIsEmpty() && (fieldInfo.string || record.fields[name].string);
    }

    isX2ManyEditable(props) {
        const { name, record } = props;
        const field = record.fields[name];
        if (!["one2many", "many2many"].includes(field.type)) {
            return false;
        }
        return !!this.props.fieldInfo.field.useSubView;
    }

    onEditViewType(viewType) {
        const { name, record, studioXpath } = this.props;
        this.viewEditorModel.editX2ManyView({
            viewType,
            fieldName: name,
            record,
            xpath: studioXpath,
            fieldContext: this.fieldComponentProps.context,
        });
    }

    onClick(ev) {
        if (ev.target.classList.contains("o_web_studio_editX2Many")) {
            return;
        }
        ev.stopPropagation();
        ev.preventDefault();
        this.config.onNodeClicked(this.props.studioXpath);
        this.state.displayOverlay = !this.state.displayOverlay;
    }
}
