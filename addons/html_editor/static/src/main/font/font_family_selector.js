/** @odoo-module native */
import { useEditorOverlayContext } from "@html_editor/core/editor_overlay_context";
import { useDropdownAutoVisibility } from "@html_editor/dropdown_autovisibility_hook";
import { toolbarButtonProps } from "@html_editor/main/toolbar/toolbar";
import { Component, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { useChildRef } from "@web/core/utils/hooks";

export class FontFamilySelector extends Component {
    static template = "html_editor.FontFamilySelector";
    static props = {
        document: t.any().optional(),
        fontFamilyItems: t.array(),
        currentFontFamily: t.object(),
        onSelected: t.function(),
        ...toolbarButtonProps,
    };
    static components = { Dropdown, DropdownItem };
    props = useProps(this.constructor.props);

    setup() {
        this.overlayContext = useEditorOverlayContext();
        this.menuRef = useChildRef();
        useDropdownAutoVisibility(this.overlayContext.overlayState, this.menuRef);
    }
}
