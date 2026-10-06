/** @odoo-module native */
import { useEditorOverlayContext } from "@html_editor/core/editor_overlay_context";
import { useDropdownAutoVisibility } from "@html_editor/dropdown_autovisibility_hook";
import { getCSSVariableValue, getHtmlStyle } from "@html_editor/utils/formatting";
import { Component, proxy, t, useProps } from "@odoo/owl";
import {
    DEFAULT_COLORS,
    DEFAULT_THEME_COLOR_VARS,
    useColorPicker,
} from "@web/components/color_picker";
import { elementRef } from "@web/core/utils/element_ref";
import { isColorGradient } from "@web/core/utils/format/colors";
import { useChildRef } from "@web/core/utils/hooks";
import { effect } from "@web/core/utils/reactive";

import { toolbarButtonProps } from "../toolbar/toolbar.js";

export class ColorSelector extends Component {
    static template = "html_editor.ColorSelector";
    static props = {
        ...toolbarButtonProps,
        mode: t.string(),
        type: t.string(),
        customIconClass: t.string().optional(),
        getDefaultColor: t.function().optional(),
        getSelectedColors: t.function(),
        applyColor: t.function(),
        applyColorPreview: t.function(),
        applyColorResetPreview: t.function(),
        getUsedCustomColors: t.function(),
        getTargetedElements: t.function(),
        colorPrefix: t.string(),
        enabledTabs: t.array().optional(["solid", "gradient", "custom"]),
        cssVarColorPrefix: t.string().optional(""),
        onClose: t.function(),
        useDefaultThemeColors: t.boolean().optional(true),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.overlayContext = useEditorOverlayContext();
        this.state = proxy({});
        this.colorSelectorState = proxy({ isOpen: false });
        const htmlStyle = getHtmlStyle(document);
        const defaultThemeColors = DEFAULT_THEME_COLOR_VARS.map((color) =>
            getCSSVariableValue(color, htmlStyle),
        );
        this.solidColors = [
            ...DEFAULT_COLORS.flat(),
            ...defaultThemeColors,
            getCSSVariableValue("body-color", htmlStyle),
            "#00000000",
        ];
        effect(
            (selectedColors) => {
                this.state.selectedColor = selectedColors[this.props.mode];
                this.state.defaultTab = "solid";
                this.state.selectedTab = this.getCorrespondingColorTab(
                    selectedColors[this.props.mode],
                );
                this.state.getTargetedElements = this.props.getTargetedElements;
                this.state.mode = this.props.mode;
            },
            [this.props.getSelectedColors()],
        );

        const colorPickerRef = useChildRef();
        this.rootRef = elementRef();
        this.colorPicker = useColorPicker(
            this.rootRef,
            () => ({
                state: this.state,
                applyColor: this.props.applyColor,
                applyColorPreview: this.props.applyColorPreview,
                applyColorResetPreview: this.props.applyColorResetPreview,
                getUsedCustomColors: this.props.getUsedCustomColors,
                colorPrefix: this.props.colorPrefix,
                enabledTabs: this.props.enabledTabs,
                cssVarColorPrefix: this.props.cssVarColorPrefix,
                useDefaultThemeColors: this.props.useDefaultThemeColors,
            }),
            {
                pluginManager: this.__owl__.pluginManager,
                onClose: () => {
                    this.props.applyColorResetPreview();
                    this.props.onClose();
                    this.colorSelectorState.isOpen = false;
                },
                onOpen: () => {
                    this.colorSelectorState.isOpen = true;
                },
                ref: colorPickerRef,
            },
        );
        useDropdownAutoVisibility(this.overlayContext.overlayState, colorPickerRef);
    }

    getCorrespondingColorTab(color) {
        if (!color || this.solidColors.includes(color.toUpperCase())) {
            return "solid";
        } else if (isColorGradient(color)) {
            return "gradient";
        } else {
            return "custom";
        }
    }

    getSelectedColorStyle() {
        if (isColorGradient(this.state.selectedColor)) {
            return `border-bottom: 2px solid transparent; border-image: ${this.state.selectedColor}; border-image-slice: 1`;
        }
        return `border-bottom: 2px solid ${
            this.state.selectedColor || this.props.getDefaultColor?.()
        }`;
    }
}
