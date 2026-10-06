// @ts-check
/** @odoo-module native */

import {
    Component,
    onMounted,
    onWillDestroy,
    onWillUpdateProps,
    proxy,
    status,
    t,
    useProps,
    xml,
} from "@odoo/owl";
import { useDropdownGroup } from "@web/components/dropdown/_behaviours/dropdown_group_hook";
import { useDropdownNesting } from "@web/components/dropdown/_behaviours/dropdown_nesting";
import { DropdownPopover } from "@web/components/dropdown/_behaviours/dropdown_popover";
import { useDropdownState } from "@web/components/dropdown/dropdown_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { inputModality } from "@web/core/input_modality";
import { mergeNavigationOptions, useNavigation } from "@web/core/navigation/navigation";
import { getComponentElement } from "@web/core/utils/components";
import { mergeClasses } from "@web/core/utils/dom/classname";
import { uniqueId } from "@web/core/utils/functions";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { effect } from "@web/core/utils/reactive";
import { onRendered } from "@web/core/utils/render_hooks";
import { usePopover } from "@web/ui/popover/popover_hook";
import { utils } from "@web/ui/viewport";

const log = makeLogger("web.components.dropdown");

const DIRECTION_CLASSES = {
    bottom: "dropdown",
    top: "dropup",
    left: "dropstart",
    right: "dropend",
};

const MENU_BOTTOM_SHEET_CLASSES = "o-dropdown--menu dropdown-menu show";
const MENU_INLINE_CLASSES = "o-dropdown--menu dropdown-menu mx-0";
const MENU_SUBMENU_CLASS = "o-dropdown--menu-submenu";

// ARIA allows aria-expanded only on a role that exposes that state: a generic wrapper used as
// the toggle (the search bar's field, whose input is the combobox) must not carry it.
const EXPANDABLE_TARGET = [
    "button",
    "a[href]",
    "summary",
    "select",
    ...[
        "application",
        "button",
        "checkbox",
        "columnheader",
        "combobox",
        "gridcell",
        "link",
        "listbox",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "row",
        "rowheader",
        "switch",
        "tab",
        "treeitem",
    ].map((role) => `[role=${role}]`),
].join(", ");

const STATIC_MENU_CLASSES = new Set([
    ...MENU_BOTTOM_SHEET_CLASSES.split(" "),
    ...MENU_INLINE_CLASSES.split(" "),
    MENU_SUBMENU_CLASS,
]);

export class Dropdown extends Component {
    static template = xml`<t t-call-slot="default"/>`;

    /** @type {string[]} */
    _menuClassNames;

    static props = {
        menuClass: t.any().optional(""),
        position: t.string().optional(),
        slots: t.object({ default: t.any().optional(), content: t.any().optional() }),
        items: t
            .array(
                t.object({
                    label: t.string(),
                    onSelected: t.function(),
                    class: t.any().optional(),
                }),
            )
            .optional(),
        menuRef: t.function().optional(),
        disabled: t.boolean().optional(false),
        holdOnHover: t.boolean().optional(false),
        focusToggleOnClosed: t.boolean().optional(true),
        beforeOpen: t.function().optional(),
        onOpened: t.function().optional(),
        onStateChanged: t.function().optional(),
        state: t
            .object({ isOpen: t.boolean(), close: t.function(), open: t.function() })
            .optional(undefined),
        manual: t.boolean().optional(),
        noClasses: t.boolean().optional(false),
        navigationOptions: t.object().optional({}),
        bottomSheet: t.boolean().optional(true),
        role: t.string().optional("menu"),
        menuId: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {any} */
    nesting;
    /** @type {any} */
    group;
    /** @type {any} */
    popover;
    /** @type {any} */
    navigation;
    /** @type {import("services").ServiceFactories["ui"]} */
    uiService;
    /** @type {{ token: number, items: any[] | undefined } | undefined} */
    popoverRefresher;
    /** @type {Record<string, any>} */
    popoverSlots = {};

    setup() {
        useLifecycleLog(log);
        this.menuRef = this.props.menuRef || useChildRef();
        this.menuId = this.props.menuId || uniqueId("o-dropdown-menu-");
        this._boundHandleClick = this.handleClick.bind(this);
        this._boundHandleMouseEnter = this.handleMouseEnter.bind(this);

        this.state = this.props.state || useDropdownState();
        this.nesting = useDropdownNesting(this.state);
        this.group = useDropdownGroup(this.state);

        this.navigation = useNavigation(
            this.menuRef,
            mergeNavigationOptions(
                {
                    shouldRegisterHotkeys: false,
                    isNavigationAvailable: () => this.state.isOpen,
                    getItems: () => {
                        if (this.state.isOpen && this.menuRef.el) {
                            return this.menuRef.el.querySelectorAll(
                                ":scope .o-navigable, :scope .o-dropdown",
                            );
                        } else {
                            return [];
                        }
                    },
                },
                this.nesting.navigationOptions,
                this.props.navigationOptions,
            ),
        );

        this.uiService = useService("ui");
        this.setupPopover();
        this.setupTargetBinding();
    }

    setupPopover() {
        const self = this;
        /** @type {any} */
        const options = {
            animation: false,
            arrow: false,
            closeOnClickAway: (target) => this.popoverCloseOnClickAway(target),
            closeOnEscape: false,
            pluginManager: /** @type {any} */ (this).__owl__.pluginManager,
            holdOnHover: this.props.holdOnHover,
            onClose: () => this.state.close(),
            onPositioned: (el, { direction }) =>
                this.setTargetDirectionClass(direction),
            get role() {
                return self.props.role;
            },
            id: this.menuId,
            get position() {
                return self.position;
            },
            ref: this.menuRef,
            setActiveElement: false,
            useBottomSheet: () => this.isBottomSheet,
            get class() {
                return self.isBottomSheet
                    ? mergeClasses(MENU_BOTTOM_SHEET_CLASSES, self.props.menuClass)
                    : mergeClasses(
                          MENU_INLINE_CLASSES,
                          { [MENU_SUBMENU_CLASS]: self.hasParent },
                          self.props.menuClass,
                      );
            },
        };
        this.popover = usePopover(DropdownPopover, options);

        onRendered(() => {
            if (this.popoverRefresher) {
                this.syncPopoverContent();
                this.popoverRefresher.token++;
            }
        });

        onMounted(() => this.onStateChanged(this.state));
        const disposeEffect = effect(
            (state) => {
                // the read keeps the subscription; before the mount there is no
                // popover to open or close, onMounted takes the state from there
                const { isOpen } = state;
                if (status(this) === "mounted") {
                    this.onStateChanged({ isOpen });
                }
            },
            [this.state],
        );
        onWillDestroy(disposeEffect);
    }

    setupTargetBinding() {
        useLayoutEffect(
            (target) => this.setTargetElement(target),
            () => [this.target],
        );

        this._menuClassNames = [];
        useLayoutEffect(
            (menuEl) => {
                if (menuEl) {
                    this.syncMenuClass(menuEl);
                }
            },
            () => [this.menuRef.el, this.menuClassNames.join(" ")],
        );

        onWillUpdateProps((nextProps) => {
            if (nextProps.state && nextProps.state !== this.props.state) {
                throw new Error(
                    "Dropdown: the `state` prop is read once, in setup. Hold one " +
                        "object for the life of the component instead of computing " +
                        "a new one per render.",
                );
            }
            if (nextProps.disabled) {
                this.state.close();
            }
        });
    }

    get isBottomSheet() {
        // decided when the menu opens and kept while it is open: a navigation
        // key turns the modality to keyboard, and swapping the sheet for an
        // inline menu then would replace the content the user is in
        if (this.openedAsBottomSheet !== undefined) {
            return this.openedAsBottomSheet;
        }
        return utils.isSmall() && inputModality.isTouch && this.props.bottomSheet;
    }

    /** @returns {string[]} */
    get menuClassNames() {
        const merged = mergeClasses(this.props.menuClass);
        return Object.keys(merged)
            .filter((name) => merged[name] && name.trim())
            .map((name) => name.trim());
    }

    /** @param {HTMLElement} menuEl */
    syncMenuClass(menuEl) {
        const wanted = this.menuClassNames;
        for (const name of this._menuClassNames) {
            if (!wanted.includes(name) && !STATIC_MENU_CLASSES.has(name)) {
                menuEl.classList.remove(name);
            }
        }
        menuEl.classList.add(...wanted);
        this._menuClassNames = wanted;
    }

    /** @type {string} */
    get position() {
        return this.props.position || (this.hasParent ? "right-start" : "bottom-start");
    }

    get hasParent() {
        return this.nesting.hasParent;
    }

    /** @type {HTMLElement|null} */
    get target() {
        return getComponentElement(this);
    }

    handleClick(event) {
        if (this.props.disabled) {
            return;
        }

        event.stopPropagation();
        log.logic("handleClick", () => ({
            isOpen: this.state.isOpen,
            hasParent: this.hasParent,
        }));
        if (this.state.isOpen && !this.hasParent) {
            this.state.close();
        } else {
            this._captureFocusBeforeOpen();
            this.state.open();
        }
    }

    handleMouseEnter() {
        if (this.props.disabled) {
            return;
        }

        if (this.hasParent || this.group.isOpen) {
            const activeElement = /** @type {HTMLElement | null} */ (
                document.activeElement
            );
            const isEditableActive =
                activeElement &&
                (["INPUT", "TEXTAREA"].includes(activeElement.nodeName) ||
                    activeElement.isContentEditable);
            if (!isEditableActive || this.target?.contains(activeElement)) {
                this.target?.focus();
            }
            this._captureFocusBeforeOpen();
            this.state.open();
        }
    }

    _captureFocusBeforeOpen() {
        if (this.state.isOpen) {
            return;
        }
        this._pendingFocusEl = /** @type {HTMLElement | null} */ (
            document.activeElement
        );
    }

    onStateChanged(state) {
        if (state.isOpen) {
            this.openPopover();
        } else {
            this.closePopover();
        }
    }

    popoverCloseOnClickAway(target) {
        const rootNode = target.getRootNode();
        if (rootNode instanceof ShadowRoot) {
            target = rootNode.host;
        }
        return this.uiService.getActiveElementOf(target) === this.activeEl;
    }

    setTargetElement(target) {
        if (!target) {
            return;
        }

        if (target.matches(EXPANDABLE_TARGET)) {
            target.ariaExpanded = "false";
        }
        const optionalClasses = [];
        const requiredClasses = [];
        optionalClasses.push("o-dropdown");

        if (this.hasParent) {
            requiredClasses.push("o-dropdown--has-parent");
        }

        const tagName = target.tagName.toLowerCase();
        if (
            ![
                "input",
                "textarea",
                "table",
                "thead",
                "tbody",
                "tr",
                "th",
                "td",
            ].includes(tagName)
        ) {
            optionalClasses.push("dropdown-toggle");
            if (this.hasParent) {
                optionalClasses.push("o-dropdown-item", "dropdown-item");
                requiredClasses.push("o-navigable");

                if (!target.classList.contains("o-dropdown--no-caret")) {
                    requiredClasses.push("o-dropdown-caret");
                }
            }
        }

        const applied = this.props.noClasses
            ? requiredClasses
            : [...requiredClasses, ...optionalClasses];
        const added = applied.filter((cls) => !target.classList.contains(cls));
        target.classList.add(...added);

        this.defaultDirection = this.position.split("-")[0];
        this.setTargetDirectionClass(this.defaultDirection);

        if (!this.props.manual) {
            target.addEventListener("click", this._boundHandleClick);
            target.addEventListener("mouseenter", this._boundHandleMouseEnter);
        }

        return () => {
            target.removeEventListener("click", this._boundHandleClick);
            target.removeEventListener("mouseenter", this._boundHandleMouseEnter);
            target.classList.remove(...added, ...Object.values(DIRECTION_CLASSES));
            target.removeAttribute("aria-expanded");
        };
    }

    setTargetDirectionClass(direction) {
        if (!this.target || this.props.noClasses) {
            return;
        }
        this.target.classList.remove(...Object.values(DIRECTION_CLASSES));
        this.target.classList.add(DIRECTION_CLASSES[direction]);
    }

    openPopover() {
        log.logic("openPopover", () => ({
            popoverIsOpen: this.popover.isOpen,
            status: status(this),
            targetConnected: Boolean(this.target?.isConnected),
        }));
        const captured =
            this._pendingFocusEl !== undefined
                ? this._pendingFocusEl
                : /** @type {HTMLElement | null} */ (document.activeElement);
        this._pendingFocusEl = undefined;

        if (this.popover.isOpen || status(this) !== "mounted") {
            return;
        }
        if (!this.target || !this.target.isConnected) {
            this.state.close();
            return;
        }

        this.openedAsBottomSheet = undefined;
        this.openedAsBottomSheet = this.isBottomSheet;
        this.popoverRefresher = proxy({ token: 0, items: this.props.items });
        this.popoverSlots = {};
        this.syncPopoverContent();
        const props = {
            beforeOpen: () => this.props.beforeOpen?.(),
            onOpened: () => this.onOpened(),
            onClosed: () => this.onClosed(),
            refresher: this.popoverRefresher,
            slots: this.popoverSlots,
        };
        const capturedInOtherDropdown =
            captured &&
            !this.target.contains(captured) &&
            Boolean(
                captured.closest?.(".o-dropdown, .o-dropdown--menu, .dropdown-menu"),
            );
        const capturedUsable =
            captured && !capturedInOtherDropdown && !captured.isContentEditable;
        this._focusedElBeforeOpen = capturedUsable ? captured : this.target;
        this.popover.open(this.target, props);
    }

    /**
     * The popover is opened once with its props; every later render of the
     * dropdown hands it the slots and items of that render through the
     * objects it already holds, so the open menu follows the parent.
     */
    syncPopoverContent() {
        const slots = this.props.slots || {};
        for (const name of Object.keys(this.popoverSlots)) {
            if (!(name in slots)) {
                delete this.popoverSlots[name];
            }
        }
        Object.assign(this.popoverSlots, slots);
        this.popoverRefresher.items = this.props.items;
    }

    closePopover() {
        this.openedAsBottomSheet = undefined;
        log.logic("closePopover", () => ({
            focusToggleOnClosed: this.props.focusToggleOnClosed,
            restore: this._focusedElBeforeOpen?.tagName,
        }));
        const restoreEl = this._focusedElBeforeOpen;
        this._focusedElBeforeOpen = undefined;
        const active = document.activeElement;
        this.popover.close();
        if (!this.props.focusToggleOnClosed || !restoreEl) {
            return;
        }
        const focusOutside =
            active &&
            !this.target?.contains(active) &&
            !this.menuRef.el?.contains(active);
        const leaveFocus = this.group.isInGroup
            ? focusOutside && active !== document.body
            : focusOutside &&
              (["INPUT", "TEXTAREA"].includes(active.nodeName) ||
                  /** @type {HTMLElement} */ (active).isContentEditable);
        if (!leaveFocus) {
            restoreEl.focus();
        }
    }

    onOpened() {
        log.lifecycle("opened", () => ({ menuId: this.menuId }));
        this.syncMenuClass(this.menuRef.el);
        this.activeEl = this.uiService.activeElement;
        this.navigation.registerHotkeys();
        this.navigation.observe(this.menuRef.el);
        this.props.onOpened?.();
        this.props.onStateChanged?.(true);

        if (this.target) {
            if (this.target.hasAttribute("aria-expanded")) {
                this.target.ariaExpanded = "true";
            }
            this.target.classList.add("show");
        }
    }

    onClosed() {
        log.lifecycle("closed", () => ({ menuId: this.menuId }));
        this._menuClassNames = [];
        this.navigation.unregisterHotkeys();
        this.navigation.observe(null);
        this.navigation.update();
        this.props.onStateChanged?.(false);
        delete this.activeEl;

        if (this.target) {
            if (this.target.hasAttribute("aria-expanded")) {
                this.target.ariaExpanded = "false";
            }
            this.target.classList.remove("show");
            this.setTargetDirectionClass(this.defaultDirection);
        }
    }
}
