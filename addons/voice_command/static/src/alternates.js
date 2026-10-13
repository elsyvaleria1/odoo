// @ts-check
/** @odoo-module native */

import { saidInLanguage } from "./interpreter/pronunciation.js";

/**
 * Every label on screen is stored by Odoo in each installed language; the word
 * a user says is often the other language's label of what they see ("draft"
 * for *Borrador*, "dashboard" for *Tableros*). These are read from the server
 * once per view and once per session for the menus, and kept.
 *
 * @typedef {{
 *   filters: Record<string, string[]>,
 *   dateFilters: Record<string, string[]>,
 *   groupBys: Record<string, string[]>,
 *   searchFields: Record<string, string[]>,
 *   formFields: Record<string, string[]>,
 *   buttons: Record<string, string[]>,
 *   fields: Record<string, string[]>,
 * }} ViewAlternates
 * @typedef {{ menu: (id: number) => string[], view: ViewAlternates | null }} Alternates
 */

const KINDS = /** @type {const} */ ({
    filters: "filters",
    date_filters: "dateFilters",
    group_bys: "groupBys",
    search_fields: "searchFields",
    form_fields: "formFields",
    buttons: "buttons",
    fields: "fields",
});

/** @returns {ViewAlternates} */
function emptyView() {
    return {
        filters: {},
        dateFilters: {},
        groupBys: {},
        searchFields: {},
        formFields: {},
        buttons: {},
        fields: {},
    };
}

/**
 * @param {Record<string, Record<string, any>>} byLang
 * @returns {ViewAlternates}
 */
function mergeView(byLang) {
    const merged = emptyView();
    for (const [lang, labels] of Object.entries(byLang || {})) {
        for (const [kind, key] of Object.entries(KINDS)) {
            for (const [name, value] of Object.entries(labels[kind] || {})) {
                const target = merged[key];
                target[name] = [
                    ...(target[name] || []),
                    ...saidInLanguage(lang, [value].flat()),
                ];
            }
        }
    }
    return merged;
}

/** @param {any} target an active view */
export function viewRequest(target) {
    if (!target?.searchModel?.resModel) {
        return null;
    }
    const viewType = target.config?.viewType;
    /** @type {[number | false, string][]} */
    const views = [[target.searchModel.searchViewId || false, "search"]];
    if (viewType === "form") {
        const formView = (target.config?.views || []).find(
            (/** @type {any} */ [, type]) => type === "form",
        );
        views.push([formView?.[0] || false, "form"]);
    }
    return { resModel: target.searchModel.resModel, views };
}

export class AlternateLabels {
    /** @param {any} orm */
    constructor(orm) {
        this.orm = orm;
        /** @type {Map<string, ViewAlternates>} */
        this.views = new Map();
        /** @type {Map<string, Promise<void>>} */
        this.pending = new Map();
        /** @type {Map<number, string[]>} */
        this.menus = new Map();
        /** @type {Promise<void> | null} */
        this.menusLoaded = null;
    }

    /**
     * @param {any} target
     * @param {number[]} menuIds
     */
    async ensure(target, menuIds) {
        await Promise.all([this.ensureMenus(menuIds), this.ensureView(target)]);
    }

    /** @param {number[]} menuIds */
    ensureMenus(menuIds) {
        if (!this.menusLoaded) {
            this.menusLoaded = this.orm.silent
                .call("voice.labels", "menu_labels", [menuIds])
                .then(
                    (/** @type {Record<string, Record<string, string>>} */ byLang) => {
                        for (const [lang, names] of Object.entries(byLang || {})) {
                            for (const [id, name] of Object.entries(names)) {
                                const key = Number(id);
                                this.menus.set(key, [
                                    ...(this.menus.get(key) || []),
                                    ...saidInLanguage(lang, [name]),
                                ]);
                            }
                        }
                    },
                )
                .catch(() => {});
        }
        return this.menusLoaded;
    }

    /** @param {any} target */
    ensureView(target) {
        const request = viewRequest(target);
        if (!request) {
            return Promise.resolve();
        }
        const key = JSON.stringify(request);
        if (this.views.has(key)) {
            return Promise.resolve();
        }
        if (!this.pending.has(key)) {
            this.pending.set(
                key,
                this.orm.silent
                    .call("voice.labels", "view_labels", [
                        request.resModel,
                        request.views,
                    ])
                    .then((/** @type {any} */ byLang) => {
                        this.views.set(key, mergeView(byLang));
                    })
                    .catch(() => {
                        this.views.set(key, emptyView());
                    }),
            );
        }
        return /** @type {Promise<void>} */ (this.pending.get(key));
    }

    /**
     * @param {any} target
     * @returns {Alternates}
     */
    of(target) {
        const request = viewRequest(target);
        return {
            menu: (id) => this.menus.get(id) || [],
            view: request ? this.views.get(JSON.stringify(request)) || null : null,
        };
    }
}
