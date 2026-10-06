// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { CustomColorPicker } from "@web/components/color_picker/custom_color_picker/custom_color_picker";
import {
    DEFAULT_COLORS,
    DEFAULT_GRAYSCALES,
    DEFAULT_THEME_COLOR_VARS,
} from "@web/core/colors/colors";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
export { DEFAULT_COLORS, DEFAULT_THEME_COLOR_VARS } from "@web/core/colors/colors";
import { useColorScheme } from "@web/core/color_scheme";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { usePositionBus } from "@web/core/position/position_hook";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import {
    isColorGradient,
    isCSSColor,
    normalizeCSSColor,
} from "@web/core/utils/format/colors";
import { usePopover } from "@web/ui/popover/popover_hook";

const log = makeLogger("web.components.color_picker");

registry.category("color_picker_tabs").addValidation(
    t.strictObject({
        id: t.string(),
        name: t.or([t.string(), t.object()]),
        component: t.customValidator(t.any(), (c) => typeof c === "function"),
    }),
);

export class ColorPicker extends Component {
    static template = "web.ColorPicker";
    static components = { CustomColorPicker };
    static props = {
        state: t.object({
            selectedColor: t.string(),
            selectedColorCombination: t.string().optional(),
            getTargetedElements: t.function().optional(),
            defaultTab: t.string(),
            selectedTab: t.string().optional(),
            mode: t.string().optional(),
        }),
        getUsedCustomColors: t.function(),
        applyColor: t.function(),
        applyColorPreview: t.function(),
        applyColorResetPreview: t.function(),
        editColorCombination: t.function().optional(),
        setOnCloseCallback: t.function().optional(() => () => {}),
        setOperationCallbacks: t.function().optional(),
        enabledTabs: t.array().optional(["solid", "custom"]),
        colorPrefix: t.string(),
        cssVarColorPrefix: t.string().optional(""),
        defaultOpacity: t.number().optional(100),
        grayscales: t.object().optional(),
        noTransparency: t.boolean().optional(),
        close: t.function().optional(() => () => {}),
        className: t.string().optional(),
        useDefaultThemeColors: t.boolean().optional(true),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLElement>} */
    root;
    /** @type {any[]} */
    tabs = [];
    /** @type {string[][]} */
    defaultColors = DEFAULT_COLORS;
    /** @type {Record<string, string[]>} */
    grayscales = DEFAULT_GRAYSCALES;
    /** @type {string[]} */
    themeColorVars = [];
    /** @type {string | false | undefined} */
    defaultColorSet;
    /** @type {string[]} */
    usedCustomColors = [];
    /** @type {EventTarget | null} */
    focusedBtn = null;
    /** @type {boolean} */
    previewingFocusin = false;
    /** @type {{ activeTab: string, currentCustomColor: string, currentColorPreview: any, showGradientPicker: boolean }} */
    state;
    /** @type {() => void} */
    onApplyCallback = () => {};
    /** @type {() => void} */
    onPreviewRevertCallback = () => {};
    /** @type {() => any} */
    getPreviewColor = () => {};

    setup() {
        this.colorScheme = useColorScheme();
        this.positionBus = usePositionBus();
        useLifecycleLog(log);
        this.tabHandlers = {
            applyColor: this.selectColor.bind(this),
            onColorClick: this.onColorApply.bind(this),
            onColorPointerOver: this.onColorHover.bind(this),
            onColorPointerOut: this.onColorHoverOut.bind(this),
            onColorPointerLeave: this.resetColorPreview.bind(this),
            onFocusin: this.onColorFocusin.bind(this),
            onFocusout: this.onColorFocusout.bind(this),
            colorPickerNavigation: this.colorPickerNavigation.bind(this),
            onColorPreview: this.onColorPreview.bind(this),
            setOperationCallbacks: this.setOperationCallbacks.bind(this),
        };
        this.tabs = registry
            .category("color_picker_tabs")
            .getAll()
            .filter((tab) => this.props.enabledTabs.includes(tab.id));
        this.root = elementRef();

        this.grayscales = { ...DEFAULT_GRAYSCALES, ...this.props.grayscales };
        this.themeColorVars = this.props.useDefaultThemeColors
            ? DEFAULT_THEME_COLOR_VARS
            : [];
        this.state = proxy({
            activeTab: this.props.state.selectedTab || this.getDefaultTab(),
            currentCustomColor: this.props.state.selectedColor,
            currentColorPreview: undefined,
            showGradientPicker: false,
        });
        this.updateFromApplied();
        useLayoutEffect(
            () => {
                this.positionBus?.trigger("update");
            },
            () => [this.state.activeTab],
        );
    }

    /** @returns {Record<string, any>} */
    get tabProps() {
        const { props, state } = this;
        return {
            ...this.tabHandlers,
            setOnCloseCallback: props.setOnCloseCallback,
            editColorCombination: props.editColorCombination,
            selectedColorCombination: props.state.selectedColorCombination,
            defaultOpacity: props.defaultOpacity,
            noTransparency: props.noTransparency,
            defaultThemeColorVars: this.themeColorVars,
            defaultColorSet: this.defaultColorSet,
            cssVarColorPrefix: props.cssVarColorPrefix,
            defaultColors: this.defaultColors,
            usedCustomColors: this.usedCustomColors,
            grayscales: this.grayscales,
            currentCustomColor: state.currentCustomColor,
            currentColorPreview: state.currentColorPreview,
            selectedColor: props.state.selectedColor,
        };
    }

    updateFromApplied() {
        this.defaultColorSet = this.getDefaultColorSet();
        this.usedCustomColors = [...this.props.getUsedCustomColors()];
    }

    getDefaultTab() {
        if (this.props.enabledTabs.includes(this.props.state.defaultTab)) {
            return this.props.state.defaultTab;
        }
        return this.props.enabledTabs[0];
    }

    get selectedColor() {
        return this.props.state.selectedColor;
    }

    get isDarkTheme() {
        return this.colorScheme.isDark;
    }

    setTab(tab) {
        log.logic("setTab", () => ({ tab }));
        this.state.activeTab = tab;
        this.setOperationCallbacks({ onPreviewRevertCallback: () => {} });
        this.resetColorPreview();
    }

    processColorFromEvent(ev) {
        const target = this.getTarget(ev);
        let color = target.dataset.color || "";
        if (color && isColorCombination(color)) {
            return color;
        }
        if (color && !isCSSColor(color) && !isColorGradient(color)) {
            color = this.props.colorPrefix + color;
        }
        return color;
    }
    /**
     * @param {Object} cbs
     * @param {() => void} [cbs.onApplyCallback]
     * @param {() => void} [cbs.onPreviewRevertCallback]
     * @param {() => any} [cbs.getPreviewColor]
     */
    setOperationCallbacks(cbs) {
        if (this.props.setOperationCallbacks) {
            this.props.setOperationCallbacks(cbs);
        }
        if (cbs.onApplyCallback) {
            this.onApplyCallback = cbs.onApplyCallback;
        }
        if (cbs.onPreviewRevertCallback) {
            this.onPreviewRevertCallback = cbs.onPreviewRevertCallback;
        }
        if (cbs.getPreviewColor) {
            this.getPreviewColor = cbs.getPreviewColor;
        }
    }

    selectColor(color) {
        log.logic("selectColor", () => ({ color, tab: this.state.activeTab }));
        this.state.currentCustomColor = color;
        this.props.applyColor(color);
        this.updateFromApplied();
        this.onApplyCallback();
    }

    onColorApply(ev) {
        if (!this.isColorButton(this.getTarget(ev))) {
            return;
        }
        const color = this.processColorFromEvent(ev);
        this.selectColor(color);
        this.props.close();
    }

    resetColorPreview() {
        this.props.applyColorResetPreview();
        this.state.currentColorPreview = undefined;
        this.onPreviewRevertCallback();
    }

    onColorPreview(ev) {
        const color = ev.hex || ev.gradient || this.processColorFromEvent(ev);
        this.props.applyColorPreview(color);
        this.state.currentColorPreview = this.getPreviewColor();
    }

    onColorHover(ev) {
        if (!this.isColorButton(this.getTarget(ev))) {
            return;
        }
        this.onColorPreview(ev);
    }

    onColorHoverOut(ev) {
        if (!this.isColorButton(this.getTarget(ev))) {
            return;
        }
        this.resetColorPreview();
    }
    getTarget(ev) {
        const target = ev.target.closest(`[data-color]`);
        return this.root.el?.contains(target) ? target : ev.target;
    }

    onColorFocusin(ev) {
        if (this.previewingFocusin || this.focusedBtn === ev.target) {
            return;
        }
        this.previewingFocusin = true;
        try {
            this.onColorHover(ev);
            if (document.activeElement !== ev.target) {
                ev.target.focus();
            }
        } finally {
            this.focusedBtn = ev.target;
            this.previewingFocusin = false;
        }
    }

    onColorFocusout(ev) {
        if (this.focusedBtn === ev.target) {
            this.focusedBtn = null;
        }
        if (!ev.relatedTarget || !this.isColorButton(ev.relatedTarget)) {
            return;
        }
        const activeEl = document.activeElement;
        this.resetColorPreview();
        if (document.activeElement !== activeEl) {
            ev.relatedTarget.focus();
        }
    }

    getDefaultColorSet() {
        if (!this.props.state.selectedColor) {
            return;
        }
        let defaultColors = this.props.enabledTabs.includes("solid")
            ? this.themeColorVars
            : [];
        for (const grayscale of Object.values(this.grayscales)) {
            defaultColors = [...defaultColors, ...grayscale];
        }

        const targetedElement =
            this.props.state.getTargetedElements?.()?.[0] || document.documentElement;
        const selectedColor = this.props.state.selectedColor.toUpperCase();
        const view = targetedElement.ownerDocument.defaultView;
        if (!view) {
            return false;
        }
        const htmlStyle = view.getComputedStyle(targetedElement);

        for (const color of defaultColors) {
            const cssVar = normalizeCSSColor(htmlStyle.getPropertyValue(`--${color}`));
            if (cssVar?.toUpperCase() === selectedColor) {
                return color;
            }
        }

        return false;
    }

    colorPickerNavigation(ev) {
        const { target, key } = ev;
        if (!target.classList.contains("o_color_button")) {
            return;
        }
        if (!["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"].includes(key)) {
            return;
        }

        let targetBtn;
        if (key === "ArrowRight") {
            targetBtn = target.nextElementSibling;
        } else if (key === "ArrowLeft") {
            targetBtn = target.previousElementSibling;
        } else if (key === "ArrowUp" || key === "ArrowDown") {
            const buttonIndex = [...target.parentElement.children].indexOf(target);
            const nbColumns = parseFloat(
                getComputedStyle(target).getPropertyValue(
                    "--o-color-picker-grid-columns",
                ),
            );
            targetBtn =
                target.parentElement.children[
                    buttonIndex + (key === "ArrowUp" ? -1 : 1) * nbColumns
                ];
            if (!targetBtn) {
                const section =
                    key === "ArrowUp"
                        ? target.parentElement.previousElementSibling
                        : target.parentElement.nextElementSibling;
                if (section?.matches(".o_color_section, .o_colorpicker_section")) {
                    targetBtn = getClosestInEdgeRow(
                        section,
                        target,
                        key === "ArrowUp" ? "last" : "first",
                    );
                    log.logic("cross-section arrow", () => ({
                        key,
                        from: target.dataset.color,
                        to: targetBtn?.dataset.color,
                    }));
                }
            }
        }
        if (targetBtn?.classList.contains("o_color_button")) {
            targetBtn.focus();
        }
    }

    isColorButton(targetEl) {
        return (
            targetEl.tagName === "BUTTON" && !targetEl.matches(".o_colorpicker_ignore")
        );
    }
}

/**
 * @param {Element} section
 * @param {Element} origin
 * @param {"first" | "last"} edge
 * @returns {Element | undefined}
 */
function getClosestInEdgeRow(section, origin, edge) {
    const buttons = [...section.children]
        .filter((el) => el.classList.contains("o_color_button"))
        .map((el) => ({ el, rect: el.getBoundingClientRect() }));
    if (!buttons.length) {
        return undefined;
    }
    const tops = buttons.map(({ rect }) => rect.top);
    const edgeTop = edge === "first" ? Math.min(...tops) : Math.max(...tops);
    const originRect = origin.getBoundingClientRect();
    const originX = originRect.left + originRect.width / 2;
    let closest;
    let closestDistance = Infinity;
    for (const { el, rect } of buttons) {
        if (Math.abs(rect.top - edgeTop) >= 1) {
            continue;
        }
        const distance = Math.abs(rect.left + rect.width / 2 - originX);
        if (distance < closestDistance) {
            closest = el;
            closestDistance = distance;
        }
    }
    return closest;
}

/**
 * @param {import("@web/core/utils/element_ref").ElementRef} root
 * @param {Record<string, any> | (() => Record<string, any>)} props
 * @param {Record<string, any>} [options]
 */
export function useColorPicker(root, props, options = {}) {
    const getProps = typeof props === "function" ? props : () => props;
    /** @type {() => void} */
    let onCloseCallback = () => {};
    const setOnCloseCallback = (cb) => {
        onCloseCallback = cb;
    };
    const userOnClose = options.onClose;
    const popoverOptions = {
        ...options,
        onClose: () => {
            const callback = onCloseCallback;
            onCloseCallback = () => {};
            callback();
            userOnClose?.();
        },
    };

    const colorPicker = usePopover(ColorPicker, popoverOptions);

    function onClick() {
        if (colorPicker.isOpen) {
            colorPicker.close();
        } else if (root.el) {
            colorPicker.open(root.el, { ...getProps(), setOnCloseCallback });
            options.onOpen?.();
        }
    }

    useLayoutEffect(
        (el) => {
            if (!el) {
                return;
            }
            el.addEventListener("click", onClick);
            return () => {
                el.removeEventListener("click", onClick);
            };
        },
        () => [root.el],
    );

    return colorPicker;
}

/**
 * @param {string} color
 * @returns {boolean}
 */
function isColorCombination(color) {
    return color.startsWith("o_cc");
}
