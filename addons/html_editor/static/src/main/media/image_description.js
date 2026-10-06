/** @odoo-module native */
import { toolbarButtonProps } from "@html_editor/main/toolbar/toolbar";
import { Component, t, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { Dialog } from "@web/ui/dialog";

export class ImageDescription extends Component {
    static components = { Dialog };
    static props = { ...toolbarButtonProps, openImageDescriptionPopover: t.function() };
    static template = "html_editor.ImageDescription";
    props = useProps(this.constructor.props);
}

export class ImageDescriptionPopover extends Component {
    static props = {
        close: t.function(),
        description: t.string().optional(),
        onConfirm: t.function(),
        tooltip: t.string().optional(),
    };
    static template = "html_editor.ImageDescriptionPopover";
    props = useProps(this.constructor.props);

    setup() {
        this.state = {
            description: this.props.description,
            tooltip: this.props.tooltip,
        };
        this.inputRef = elementRef();
        useLayoutEffect(
            (el) => el?.focus(),
            () => [this.inputRef.el],
        );
        useHotkey("escape", () => this.props.close());
    }

    onSave() {
        this.props.onConfirm(this.state.description || "", this.state.tooltip || "");
        this.props.close();
    }
}
