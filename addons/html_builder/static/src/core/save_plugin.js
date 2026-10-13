/** @odoo-module native */
import { escapeTextNodes } from "@html_builder/utils/escaping";
import { Plugin } from "@html_editor/plugin";
import { withSequence } from "@html_editor/utils/resource";
import { groupBy } from "@web/core/utils/collections/arrays";
import { uniqueId } from "@web/core/utils/functions";

/** @typedef {import("plugins").CSSSelector} CSSSelector */
/**
 * @typedef { Object } SaveShared
 * @property { SavePlugin['save'] } save
 * @property { SavePlugin['saveView'] } saveView
 * @property { SavePlugin['ignoreDirty'] } ignoreDirty
 * @property { SavePlugin['groupElements'] } groupElements
 */

/**
 * @typedef {(() => void)[]} after_save_handlers
 * @typedef {((el?: HTMLElement) => Promise<void>)[]} before_save_handlers
 * @typedef {((groupedEls: Object.<string, HTMLElement[]>) => Promise<void>)[]} pre_save_handlers
 * @typedef {((el: HTMLElement) => Promise<void>)[]} save_element_handlers
 * @typedef {(() => Promise<boolean>)[]} save_handlers
 * @typedef {((cleanedEls: HTMLElement[]) => Promise<boolean>)[]} save_elements_overrides
 * @typedef {(() => HTMLElement[] | NodeList)[]} get_dirty_els
 * @typedef {CSSSelector[]} savable_selectors
 */

export class SavePlugin extends Plugin {
    static id = "savePlugin";
    static shared = ["save", "saveView", "ignoreDirty", "groupElements"];
    static dependencies = ["history"];

    /** @type {import("plugins").BuilderResources} */
    resources = {
        handleNewRecords: this.handleMutations.bind(this),
        start_edition_handlers: this.startObserving.bind(this),
        savable_selectors: [
            "#wrapwrap .oe_structure[data-oe-xpath][data-oe-id]",
            "#wrapwrap [data-oe-field]:not([data-oe-sanitize-prevent-edition])",
            "#wrapwrap .s_cover[data-res-model]",
        ],
        clean_for_save_handlers: [],
        save_element_handlers: [this.saveView.bind(this)],
        get_dirty_els: () => this.editable.querySelectorAll(".o_dirty"),
        on_prepare_drag_handlers: withSequence(0, this.ignoreDirty.bind(this)),
    };

    setup() {
        this.canObserve = false;
        this.savableSelector = this.getResource("savable_selectors").join(", ");
    }

    groupElements(toGroupEls) {
        return groupBy(toGroupEls, (toGroupEl) => {
            const model = toGroupEl.dataset.oeModel;
            const recordId = toGroupEl.dataset.oeId;
            const field = toGroupEl.dataset.oeField;

            if (!model) {
                return uniqueId("special-element-to-save-");
            }

            return `${model}::${recordId}::${field}`;
        });
    }

    async save({ shouldSkipAfterSaveHandlers = async () => true } = {}) {
        let skipAfterSaveHandlers;
        try {
            await Promise.all(
                this.getResource("before_save_handlers").map((handler) => handler()),
            );
            await this._save();
            skipAfterSaveHandlers = await shouldSkipAfterSaveHandlers();
        } finally {
            if (!skipAfterSaveHandlers) {
                this.getResource("after_save_handlers").forEach((handler) => handler());
            }
        }
    }
    async _save() {
        const dirtyEls = [];
        for (const getDirtyEls of this.getResource("get_dirty_els")) {
            dirtyEls.push(...getDirtyEls());
        }
        const groupedElements = this.groupElements(dirtyEls);
        const preSaveHandlers = [];
        for (const preSaveHandler of this.getResource("pre_save_handlers")) {
            preSaveHandlers.push(preSaveHandler(groupedElements));
        }
        await Promise.all(preSaveHandlers);
        const saveProms = Object.values(groupedElements).map(async (dirtyEls) => {
            const cleanedEls = dirtyEls.map((dirtyEl) => {
                const cleanedEl = dirtyEl.cloneNode(true);
                cleanedEl.classList.remove("o_dirty");
                this.dispatchTo("clean_for_save_handlers", { root: cleanedEl });
                return cleanedEl;
            });
            const markSaved = () =>
                dirtyEls.forEach((el) => el.classList.remove("o_dirty"));
            for (const saveElementsOverride of this.getResource(
                "save_elements_overrides",
            )) {
                if (await saveElementsOverride(cleanedEls)) {
                    markSaved();
                    return;
                }
            }
            for (const cleanedEl of cleanedEls) {
                for (const saveElementHandler of this.getResource(
                    "save_element_handlers",
                )) {
                    await saveElementHandler(cleanedEl);
                }
            }
            markSaved();
        });
        const willSaves = this.getResource("save_handlers").map((c) => c());
        const results = await Promise.allSettled(saveProms.concat(willSaves));
        const failure = results.find((result) => result.status === "rejected");
        if (failure) {
            throw failure.reason;
        }
        this.dependencies.history.reset();
    }

    /** @param {HTMLElement} el */
    saveView(el, delayTranslations = true) {
        const viewID = Number(el.dataset["oeId"]);
        if (!viewID) {
            return;
        }

        let context = {};
        if (this.services.website) {
            const delay = delayTranslations ? { delay_translations: true } : {};
            context = {
                website_id: this.services.website.currentWebsite.id,
                lang: this.services.website.currentWebsite.metadata.lang,
                ...delay,
            };
        }

        escapeTextNodes(el);
        return this.services.orm.call(
            "ir.ui.view",
            "save",
            [
                viewID,
                el.outerHTML,
                (!el.dataset["oeExpression"] && el.dataset["oeXpath"]) || null,
            ],
            { context },
        );
    }

    startObserving() {
        this.canObserve = true;
    }
    /**
     * @param {Object} records
     * @param {String} currentOperation
     */
    handleMutations(records, currentOperation) {
        if (!this.canObserve) {
            return;
        }
        if (currentOperation === "undo" || currentOperation === "redo") {
            return;
        }
        for (const record of records) {
            if (record.attributeName === "contenteditable") {
                continue;
            }
            let targetEl = record.target;
            if (!targetEl.isConnected) {
                continue;
            }
            if (targetEl.nodeType !== Node.ELEMENT_NODE) {
                targetEl = targetEl.parentElement;
            }
            if (!targetEl) {
                continue;
            }
            const savableEl = targetEl.closest(this.savableSelector);
            if (
                !savableEl ||
                savableEl.classList.contains("o_dirty") ||
                savableEl.hasAttribute("data-oe-readonly")
            ) {
                continue;
            }
            savableEl.classList.add("o_dirty");
        }
    }

    /** @returns {Function} */
    ignoreDirty() {
        this.canObserve = false;
        return () => {
            this.canObserve = true;
        };
    }
}
