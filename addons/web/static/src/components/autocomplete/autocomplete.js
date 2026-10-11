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
} from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { reportUncaught } from "@web/core/errors/error_utils";
import { useNavigation } from "@web/core/navigation/navigation";
import { usePosition } from "@web/core/position/position_hook";
import { Deferred, KeepLast, SupersededError } from "@web/core/utils/concurrency";
import { mergeClasses } from "@web/core/utils/dom/classname";
import { useClickAway } from "@web/core/utils/dom/click_away";
import { isScrollableY, scrollTo } from "@web/core/utils/dom/scrolling";
import { elementRef } from "@web/core/utils/element_ref";
import { uniqueId } from "@web/core/utils/functions";
import { useAutofocus, useForwardRefToParent } from "@web/core/utils/hooks";
import { INPUT_DEBOUNCE_DELAY, useDebounced } from "@web/core/utils/timing";

const log = makeLogger("web.components.autocomplete");

export class AutoComplete extends Component {
    static template = "web.AutoComplete";
    static props = {
        value: t.string().optional(""),
        id: t.string().optional(),
        sources: t.array(
            t.object({
                placeholder: t.string().optional(""),
                options: t.or([t.array(), t.function()]),
                optionSlot: t.string().optional(),
            }),
        ),
        placeholder: t.string().optional(),
        title: t.string().optional(""),
        autocomplete: t.string().optional("new-password"),
        autoSelect: t.boolean().optional(false),
        resetOnSelect: t.boolean().optional(),
        onInput: t.function().optional(() => () => {}),
        onCancel: t.function().optional(() => () => {}),
        onChange: t.function().optional(() => () => {}),
        onBlur: t.function().optional(() => () => {}),
        onFocus: t.function().optional(() => () => {}),
        searchOnInputClick: t.boolean().optional(true),
        input: t.function().optional(),
        inputDebounceDelay: t.number().optional(INPUT_DEBOUNCE_DELAY),
        dropdown: t.boolean().optional(true),
        autofocus: t.boolean().optional(),
        class: t.string().optional(),
        slots: t.object().optional(),
        menuPositionOptions: t.object().optional({}),
        menuCssClass: t.or([t.string(), t.array(), t.object()]).optional({}),
        selectOnBlur: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    inEdition = false;
    isOptionSelected = false;
    forceValFromProp = false;
    /** @type {string} */
    inputValue = "";

    dismissed = false;
    ignoreBlur = false;
    _scrollAwayAttached = false;

    /** @type {Deferred<void> | null} */
    pendingPromise = null;
    /** @type {Deferred<void> | null} */
    loadingPromise = null;
    /** @type {any} */
    _loadedRequest = null;
    _loadedInputValue = "";
    /** @type {string | null} */
    _lastChangeValue = null;
    /** @type {string | null} */
    _replayedChangeValue = null;
    /** @type {{ direction: number, applied: Deferred<void> } | null} */
    _entry = null;
    navigationRev = 0;

    get timeout() {
        return this.props.inputDebounceDelay;
    }

    setup() {
        useLifecycleLog(log);
        this.autoCompleteId = uniqueId("autocomplete_");
        this.nextSourceId = 0;
        this.nextOptionId = 0;

        this.keepLast = new KeepLast({ rejectSuperseded: true });

        this.state = proxy({
            open: false,
            /** @type {any[]} */
            sources: [],
        });
        this.inputValue = this.props.value;

        this.inputRef = /** @type {ReturnType<typeof elementRef<HTMLInputElement>>} */ (
            elementRef()
        );
        this.inputRef = /** @type {any} */ (
            useForwardRefToParent("input", this.inputRef)
        );
        onMounted(() => this.setInputValue(this.inputValue));
        this.listRef = elementRef();
        if (this.props.autofocus) {
            useAutofocus({ ref: this.inputRef });
        }
        this.root = elementRef();

        this.navigator = useNavigation(this.root, {
            virtualFocus: true,
            wrap: false,
            activeClass: "ui-state-active",
            mouseActivation: "armed",
            shouldFocusChildInput: false,
            shouldRegisterHotkeys: false,
            getItems: () =>
                /** @type {any} */ (
                    this.root.el?.querySelectorAll(
                        ":scope .o-autocomplete--dropdown-item > a.ui-menu-item-wrapper",
                    ) ?? []
                ),
            getHoverTarget: (el) =>
                /** @type {HTMLElement} */ (
                    el.closest(".o-autocomplete--dropdown-item") ?? el
                ),
            onUpdated: () => this.onNavigationUpdated(),
            scrollTo: (el) => {
                if (!this.props.dropdown) {
                    scrollTo(el);
                    return;
                }
                const menu = this.listRef.el;
                if (menu && isScrollableY(menu)) {
                    scrollTo(el, { scrollable: menu });
                }
            },
        });

        this.setupInputDebounce();
        this.setupDismissal();

        onWillUpdateProps((nextProps) => {
            if (this.props.value !== nextProps.value || this.forceValFromProp) {
                this.forceValFromProp = false;
                if (this.inEdition) {
                    this.closeDropdown();
                } else {
                    this.setInputValue(nextProps.value);
                    this.close();
                }
            }
        });

        this.setupPresentation();
    }

    setupInputDebounce() {
        this.debouncedProcessInput = useDebounced(
            async () => {
                const currentPromise = this.pendingPromise;
                this.pendingPromise = null;
                this.props.onInput({
                    inputValue: this.inputRef.el.value,
                });
                try {
                    await this.open(true);
                    currentPromise.resolve();
                } catch (error) {
                    currentPromise.reject(error);
                } finally {
                    if (currentPromise === this.loadingPromise) {
                        this.loadingPromise = null;
                    }
                }
            },
            () => this.timeout,
        );
    }

    setupDismissal() {
        useClickAway(() => this.externalClose(), {
            getAnchor: () => this.root.el,
            getContentEl: () => this.listRef.el,
        });
        this._onScrollAway = (/** @type {Event} */ ev) => {
            const target = /** @type {Node} */ (ev.target);
            if (
                target === document ||
                target === document.documentElement ||
                target === document.body ||
                this.root.el?.contains(target) ||
                this._readAnchorPosition() === this._anchorPosition
            ) {
                return;
            }
            this.externalClose();
        };
        onWillDestroy(() => this.close());
    }

    setupPresentation() {
        if (this.props.dropdown) {
            this._dropdownOptions = new Proxy(
                {},
                {
                    get: (_, key) => Reflect.get(this.dropdownOptions, key),
                    has: (_, key) => key in this.dropdownOptions,
                    ownKeys: () => Reflect.ownKeys(this.dropdownOptions),
                    getOwnPropertyDescriptor: (_, key) =>
                        key in this.dropdownOptions
                            ? {
                                  value: Reflect.get(this.dropdownOptions, key),
                                  enumerable: true,
                                  configurable: true,
                              }
                            : undefined,
                },
            );
            usePosition(this.listRef, () => this.targetDropdown, this._dropdownOptions);
            return;
        }
        this.state.open = true;
        this.loadSources(false);
        onMounted(() => {
            if (this.state.open) {
                this._addGlobalListeners();
            }
        });
    }

    /** @param {string} value */
    setInputValue(value) {
        this.inputValue = value;
        if (this.inputRef.el) {
            this.inputRef.el.value = value;
        }
    }

    get targetDropdown() {
        return this.inputRef.el;
    }

    get sources() {
        return this.state.sources;
    }

    /** @type {string} */
    get idPrefix() {
        return this.props.id || this.autoCompleteId;
    }

    /** @returns {boolean} */
    get isLoadingSources() {
        return this.sources.some((source) => source.isLoading);
    }

    /** @returns {Record<string, any>} */
    get dropdownOptions() {
        return {
            position: "bottom-start",
            ...this.props.menuPositionOptions,
        };
    }

    get isOpened() {
        return this.state.open;
    }

    get hasOptions() {
        for (const source of this.sources) {
            if (source.isLoading || source.options.length) {
                return true;
            }
        }
        return false;
    }

    get activeOption() {
        const el = this.navigator.activeItem?.el;
        return el ? this._optionForElement(el) : null;
    }

    /**
     * @param {HTMLElement} el
     * @returns {any | null}
     */
    _optionForElement(el) {
        const id = Number(el.dataset.optionId);
        if (!id) {
            return null;
        }
        for (const source of this.sources) {
            const option = source.options.find((candidate) => candidate.id === id);
            if (option) {
                return option;
            }
        }
        return null;
    }

    /**
     * @param {boolean} [useInput]
     * @param {number} [entryDirection]
     */
    open(useInput = false, entryDirection = 0) {
        if (status(this) === "destroyed") {
            return Promise.resolve();
        }
        log.logic("open", () => ({
            useInput,
            entryDirection,
            wasOpen: this.state.open,
        }));
        this.state.open = true;
        this.dismissed = false;
        this._anchorPosition = this._readAnchorPosition();
        this._addGlobalListeners();
        return this.loadSources(useInput, entryDirection);
    }

    close() {
        log.logic("close", () => ({
            wasOpen: this.state.open,
            pending: Boolean(this.pendingPromise),
        }));
        this.closeDropdown();
        this.debouncedProcessInput.cancel();
        this.pendingPromise?.resolve();
        this.pendingPromise = null;
        this.loadingPromise = null;
    }

    closeDropdown() {
        this.state.open = false;
        this.navigator.clearActiveItem();
        this.navigationRev = 0;
        this.keepLast.cancel();
        if (this._entry) {
            this._entry.applied.resolve();
            this._entry = null;
        }
        this._removeGlobalListeners();
    }

    _readAnchorPosition() {
        const rect = this.inputRef.el?.getBoundingClientRect();
        return rect ? `${rect.top},${rect.left}` : "";
    }

    _addGlobalListeners() {
        if (this._scrollAwayAttached) {
            return;
        }
        window.addEventListener("scroll", this._onScrollAway, true);
        this._scrollAwayAttached = true;
    }

    _removeGlobalListeners() {
        if (!this._scrollAwayAttached) {
            return;
        }
        window.removeEventListener("scroll", this._onScrollAway, true);
        this._scrollAwayAttached = false;
    }

    cancel() {
        if (this.props.autoSelect && this.inputRef.el.value.length) {
            this.setInputValue(this.props.value);
            this.props.onCancel();
        }
        this.inEdition = false;
        this.close();
    }

    /**
     * @param {boolean} useInput
     * @param {number} [entryDirection]
     */
    async loadSources(useInput, entryDirection = 0) {
        const inputValue = this.inputRef.el?.value.trim() ?? "";
        const request = useInput ? inputValue : null;
        const end = log.perf("loadSources", () => ({ request, entryDirection }));
        this.state.sources = this.props.sources.map((pSource) =>
            this.makeSource(pSource),
        );
        this.navigator.clearActiveItem();

        const proms = [];
        for (const [index, pSource] of this.props.sources.entries()) {
            const source = this.state.sources[index];
            const options = this.loadOptions(pSource.options, request ?? "");
            if (options instanceof Promise) {
                source.isLoading = true;
                proms.push(
                    options.then(
                        (options) => {
                            if (!this._isSourceCurrent(source)) {
                                return;
                            }
                            source.options = options.map((option) =>
                                this.makeOption(option),
                            );
                            source.isLoading = false;
                        },
                        (error) => {
                            if (!this._isSourceCurrent(source)) {
                                return;
                            }
                            source.isLoading = false;
                            if (error instanceof SupersededError) {
                                return;
                            }
                            this.reportSourceError(error);
                        },
                    ),
                );
            } else {
                source.options = options.map((option) => this.makeOption(option));
            }
        }

        try {
            await this.keepLast.add(Promise.all(proms));
        } catch (error) {
            if (error instanceof SupersededError) {
                end({ superseded: true });
                return;
            }
            throw error;
        }
        this._loadedRequest = request;
        this._loadedInputValue = inputValue;
        end({ options: this.sources.map((source) => source.options.length) });
        await this._enterLoadedOptions(entryDirection);
    }

    /**
     * @param {{ id: number }} source
     * @returns {boolean}
     */
    _isSourceCurrent(source) {
        return this.state.open && this.sources.some((s) => s.id === source.id);
    }

    /** @returns {any | null} */
    _firstSelectableOption() {
        for (const source of this.sources) {
            if (source.isLoading) {
                continue;
            }
            const option = source.options.find((option) => !option.unselectable);
            if (option) {
                return option;
            }
        }
        return null;
    }

    /**
     * @param {number} direction
     * @returns {Promise<void>}
     */
    _enterLoadedOptions(direction) {
        const willRenderItems =
            this.displayOptions && Boolean(this._firstSelectableOption());
        if (!willRenderItems && !this.navigator.items.length) {
            this.navigator.clearActiveItem();
            return Promise.resolve();
        }
        this._entry?.applied.resolve();
        const applied = /** @type {Deferred<void>} */ (new Deferred());
        this._entry = { direction, applied };
        return applied;
    }

    onNavigationUpdated() {
        if (!this._entry) {
            return;
        }
        const { direction, applied } = this._entry;
        this._entry = null;
        if (direction < 0) {
            this.navigator.activateLast();
        } else {
            this.navigator.activateFirst();
        }
        applied.resolve();
    }

    /** @param {any} error */
    reportSourceError(error) {
        reportUncaught(error);
    }
    get displayOptions() {
        return !this.props.dropdown || (this.isOpened && this.hasOptions);
    }
    loadOptions(options, request) {
        if (typeof options === "function") {
            return options(request);
        } else {
            return options;
        }
    }
    makeOption(option) {
        return {
            cssClass: "",
            data: {},
            ...option,
            id: ++this.nextOptionId,
            unselectable: !option.onSelect,
        };
    }
    makeSource(source) {
        return {
            id: ++this.nextSourceId,
            options: [],
            isLoading: false,
            placeholder: source.placeholder,
            optionSlot: source.optionSlot,
        };
    }

    selectOption(option) {
        this.inEdition = false;
        log.logic("selectOption", () => ({
            label: option?.label,
            unselectable: option?.unselectable,
            resetOnSelect: this.props.resetOnSelect,
        }));
        if (!option || option.unselectable) {
            return;
        }

        if (this.props.resetOnSelect) {
            this.setInputValue("");
        }
        this.isOptionSelected = true;
        this.forceValFromProp = true;
        const selection = option.onSelect();
        this.close();
        this.syncInputAfterSelection(selection);
    }

    /**
     * A selection that leaves the value unchanged updates no prop, so the parent
     * never hands the value back and the input would keep what was typed. A
     * selection that changes it is corrected again by the parent's render,
     * which lands before the next paint.
     *
     * @param {any} selection
     */
    async syncInputAfterSelection(selection) {
        await selection;
        log.logic("syncInputAfterSelection", () => ({
            resync:
                this.forceValFromProp &&
                !this.inEdition &&
                status(this) !== "destroyed",
            forceValFromProp: this.forceValFromProp,
            inEdition: this.inEdition,
            typed: this.inputRef.el?.value,
            value: this.props.value,
        }));
        if (this.forceValFromProp && !this.inEdition && status(this) !== "destroyed") {
            this.forceValFromProp = false;
            this.setInputValue(this.props.value);
        }
    }

    onInputBlur() {
        log.logic("onInputBlur", () => ({
            ignoreBlur: this.ignoreBlur,
            selectOnBlur: this.props.selectOnBlur,
            dismissed: this.dismissed,
            loading: Boolean(this.loadingPromise),
        }));
        if (this.ignoreBlur) {
            this.ignoreBlur = false;
            return;
        }
        if (
            this.props.selectOnBlur &&
            !this.dismissed &&
            !this.isOptionSelected &&
            !this.loadingPromise &&
            this._loadedInputValue === this.inputRef.el.value.trim()
        ) {
            const option = this._firstSelectableOption();
            if (option) {
                this.selectOption(option);
            }
        }
        this.props.onBlur({
            inputValue: this.inputRef.el.value,
        });
        this.inEdition = false;
        this.isOptionSelected = false;
    }
    onInputClick() {
        if (!this.isOpened && this.props.searchOnInputClick) {
            this.open(this.inputRef.el.value.trim() !== this.props.value.trim());
        } else if (this.pendingPromise) {
            this.closeDropdown();
        } else {
            this.close();
        }
    }
    onInputChange(ev) {
        if (this._swallowReplayedChangeEcho(ev)) {
            return;
        }
        this._lastChangeValue = this.targetDropdown.value;
        if (this.ignoreBlur) {
            ev.stopImmediatePropagation();
        }
        this.props.onChange({ inputValue: this.inputRef.el.value });
    }
    onInput() {
        this.inEdition = true;
        if (!this.pendingPromise) {
            this.pendingPromise = new Deferred();
            this.pendingPromise.catch(() => {});
        }
        this.loadingPromise = this.pendingPromise;
        this.debouncedProcessInput();
    }

    onInputFocus() {
        const input = this.targetDropdown;
        this._lastChangeValue = input.value;
        this._replayedChangeValue = null;
        input.setSelectionRange(0, input.value.length);
        this.props.onFocus({ inputValue: this.inputRef.el.value });
    }

    _replayHeldEnterChange() {
        const destroyed = status(this) === "destroyed";
        const value = destroyed ? null : this.targetDropdown.value;
        if (destroyed || value === this._lastChangeValue) {
            log.logic("held enter: nothing to replay", () => ({
                destroyed,
                value,
                lastChange: this._lastChangeValue,
            }));
            return;
        }
        log.logic("held enter: replaying change", () => ({
            value,
            lastChange: this._lastChangeValue,
        }));
        this.targetDropdown.dispatchEvent(new Event("change", { bubbles: true }));
        this._replayedChangeValue = value;
    }

    /**
     * @param {Event} ev
     * @returns {boolean}
     */
    _swallowReplayedChangeEcho(ev) {
        const replayed = this._replayedChangeValue;
        if (replayed === null) {
            return false;
        }
        this._replayedChangeValue = null;
        const value = this.targetDropdown.value;
        if (value !== replayed) {
            return false;
        }
        log.logic("change echoes the replayed one: suppressed", () => ({ value }));
        ev.stopImmediatePropagation();
        return true;
    }

    get autoCompleteRootClass() {
        return mergeClasses(this.props.class, { dropdown: this.props.dropdown });
    }

    get ulDropdownClass() {
        return mergeClasses(this.props.menuCssClass, {
            "dropdown-menu ui-autocomplete": this.props.dropdown,
            "list-group": !this.props.dropdown,
        });
    }

    async onInputKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        const isSelectKey = ["enter", "tab", "shift+tab"].includes(hotkey);
        const holdsEnter = Boolean(this.loadingPromise) && hotkey === "enter";

        if (this.loadingPromise && isSelectKey) {
            log.logic("select key waits for the search", () => ({ hotkey }));
            if (holdsEnter) {
                ev.stopPropagation();
                ev.preventDefault();
            }

            try {
                await this.loadingPromise;
            } catch {}
        }

        switch (hotkey) {
            case "enter":
                if (!this.isOpened || !this.activeOption) {
                    if (holdsEnter) {
                        this._replayHeldEnterChange();
                    }
                    return;
                }
                if (holdsEnter) {
                    log.logic("held enter: selecting the active option", () => ({
                        label: this.activeOption?.label,
                    }));
                }
                this.selectOption(this.activeOption);
                break;
            case "escape":
                if (!this.isOpened) {
                    return;
                }
                this.dismissed = true;
                this.cancel();
                break;
            case "tab":
            case "shift+tab":
                if (!this.isOpened) {
                    return;
                }
                if (
                    this.props.autoSelect &&
                    this.activeOption &&
                    (this.navigationRev > 0 || this.inputRef.el.value.length)
                ) {
                    this.selectOption(this.activeOption);
                }
                this.dismissed = true;
                this.close();
                return;
            case "arrowup":
            case "arrowdown": {
                const direction = hotkey === "arrowdown" ? +1 : -1;
                this.navigationRev++;
                if (this.isOpened) {
                    if (direction > 0) {
                        this.navigator.next();
                    } else {
                        this.navigator.previous();
                    }
                } else {
                    this.open(true, direction);
                }
                break;
            }
            default:
                return;
        }

        ev.stopPropagation();
        ev.preventDefault();
    }

    /** @param {[number, number]} indices */
    onOptionMouseEnter([sourceIndex, optionIndex]) {
        if (
            this.navigator.isMouseArmed &&
            this.sources[sourceIndex].options[optionIndex]?.unselectable
        ) {
            this.navigator.clearActiveItem();
        }
    }
    async onOptionClick(option) {
        const staleOptions =
            typeof this._loadedRequest === "string" &&
            this._loadedRequest !== this.inputRef.el.value.trim();
        if (staleOptions) {
            try {
                await this.loadingPromise;
            } catch {}
            this.inputRef.el?.focus();
            return;
        }
        this.selectOption(option);
        this.inputRef.el?.focus();
    }
    onOptionPointerDown(option, ev) {
        if (option.unselectable) {
            ev.preventDefault();
            return;
        }
        this.ignoreBlur = true;
    }

    externalClose() {
        if (this.isOpened) {
            this.cancel();
        }
    }
}
