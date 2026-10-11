/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

export class PdfGroupName extends Component {
    static props = {
        groupId: t.string(),
        name: t.string(),
        edit: t.boolean(),
        onToggleEdit: t.function().optional(),
        onGroupNameClicked: t.function().optional(),
        onEditName: t.function().optional(),
    };
    static template = "document.component.PdfGroupName";
    props = useProps(this.constructor.props);

    setup() {
        this.nameInputRef = elementRef();
        useAutofocus({ ref: this.nameInputRef, selectAll: true });
    }

    /**
     * @public
     */
    onBlur() {
        this.props.onEditName(this.props.groupId, this.nameInputRef.el.value);
        this.props.onToggleEdit(this.props.groupId, false);
    }
    /**
     * @public
     */
    onClickGroupName() {
        this.props.onGroupNameClicked(this.props.groupId);
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onKeyDown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.stopPropagation();
        this.props.onEditName(this.props.groupId, this.nameInputRef.el.value);
        this.props.onToggleEdit(this.props.groupId, false);
    }
}
