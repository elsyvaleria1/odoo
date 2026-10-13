// @ts-check
/** @odoo-module native */

import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { getPeriodOptions } from "@web/search/utils/dates";
import { isGroupableField } from "@web/search/utils/misc";
import { flattenMenuTree } from "@web/webclient/menus/menu_utils";

/**
 * @typedef {{ menu: any, label: string, phrases: string[], isApp: boolean, appLabel: string, inCurrentApp: boolean, section?: string }} MenuTerm
 * @typedef {{ name: string, label: string, alternates?: string[] }} FilterTerm
 * @typedef {{ name: string, label: string, fieldName: string, generatorIds: string[], alternates?: string[] }} DateFilterTerm
 * @typedef {{ fieldName: string, label: string, isDate: boolean, alternates?: string[] }} GroupByTerm
 * @typedef {{ fieldName: string, label: string, fieldType: string, relation?: string, alternates?: string[] }} SearchFieldTerm
 * @typedef {{ name: string, label: string, type: string, relation?: string, selection?: [any, string][], alternates?: string[] }} FormFieldTerm
 * @typedef {{ label: string, spoken: string[], clickParams: Record<string, any>, alternates?: string[] }} ButtonTerm
 * @typedef {{
 *   viewType: string,
 *   resModel: string,
 *   viewTypes: string[],
 *   filters: FilterTerm[],
 *   dateFilters: DateFilterTerm[],
 *   groupBys: GroupByTerm[],
 *   searchFields: SearchFieldTerm[],
 *   recordCount: number,
 *   form: { fields: FormFieldTerm[], buttons: ButtonTerm[], displayName: string } | null,
 *   reports?: ReportTerm[],
 *   canExport?: boolean,
 * }} ViewTerms
 * @typedef {{ id: number, name: string }} ReportTerm
 * @typedef {{ name: string, category?: string, action: Function }} CommandTerm
 * @typedef {{ label: string, risk: number }} TargetTerm
 * @typedef {{
 *   menus: MenuTerm[],
 *   view: ViewTerms | null,
 *   commands: CommandTerm[],
 *   today: any,
 *   targets?: TargetTerm[],
 *   numbersShown?: boolean,
 *   extensions?: string[],
 *   terms?: import("./terms.js").TermPhrase[],
 * }} Vocabulary
 */

/**
 * @param {any} menuService
 * @returns {MenuTerm[]}
 */
function compileMenus(menuService, alternates = null) {
    /** @param {any} menu */
    const other = (menu) => alternates?.menu(menu.id) || [];
    const { apps, menuItems } = flattenMenuTree(menuService.getMenuAsTree("root"));
    const currentAppId = menuService.getCurrentApp()?.id;
    const appLabels = new Map(apps.map((app) => [app.appID ?? app.id, app.label]));
    /** @type {Map<string, number>} */
    const namesakes = new Map();
    for (const item of menuItems) {
        const key = `${item.appID}/${item.label}`;
        namesakes.set(key, (namesakes.get(key) || 0) + 1);
    }
    return [
        ...apps.map((app) => ({
            menu: app,
            label: app.label,
            phrases: [app.label, ...(app.searchTerms || []), ...other(app)],
            isApp: true,
            appLabel: app.label,
            inCurrentApp: app.id === currentAppId,
        })),
        ...menuItems.map((item) => {
            const appLabel = appLabels.get(item.appID) || "";
            const parent = (item.parents || "").split(" / ").pop() || "";
            return {
                menu: item,
                label: item.label,
                phrases: [
                    item.label,
                    `${parent} ${item.label}`,
                    `${item.label} ${appLabel}`,
                    ...other(item),
                ],
                isApp: false,
                appLabel,
                inCurrentApp: item.appID === currentAppId,
                ...(namesakes.get(`${item.appID}/${item.label}`) > 1 && parent
                    ? { section: parent }
                    : {}),
            };
        }),
    ];
}

/**
 * @param {any} searchModel
 * @param {any} item
 * @returns {string[]}
 */
function knownGeneratorIds(searchModel, item) {
    if (!item.optionsParams) {
        return [];
    }
    return getPeriodOptions(searchModel.referenceMoment, item.optionsParams).map(
        (/** @type {any} */ option) => option.id,
    );
}

/**
 * @param {any} searchModel
 * @returns {Pick<ViewTerms, "filters" | "dateFilters" | "groupBys" | "searchFields">}
 */
function compileSearch(searchModel, alternates = null) {
    const items = searchModel.getSearchItems();
    /**
     * @param {keyof import("../alternates.js").ViewAlternates} kind
     * @param {string} key
     */
    const other = (kind, key) => alternates?.[kind]?.[key] || [];
    /** @type {GroupByTerm[]} */
    const groupBys = [];
    const groupedFields = new Set();
    for (const item of items) {
        if (item.type === "groupBy" || item.type === "dateGroupBy") {
            groupBys.push({
                fieldName: item.fieldName,
                label: item.description,
                isDate: item.type === "dateGroupBy",
                alternates: [
                    ...other("groupBys", item.fieldName),
                    ...other("fields", item.fieldName),
                ],
            });
            groupedFields.add(item.fieldName);
        }
    }
    for (const [fieldName, field] of Object.entries(
        searchModel.searchViewFields || {},
    )) {
        if (!groupedFields.has(fieldName) && isGroupableField(fieldName, field)) {
            groupBys.push({
                fieldName,
                label: field.string || fieldName,
                isDate: ["date", "datetime"].includes(field.type),
                alternates: other("fields", fieldName),
            });
        }
    }
    return {
        filters: items
            .filter((/** @type {any} */ item) => item.type === "filter" && item.name)
            .map((/** @type {any} */ item) => ({
                name: item.name,
                label: item.description,
                alternates: other("filters", item.name),
            })),
        dateFilters: items
            .filter(
                (/** @type {any} */ item) => item.type === "dateFilter" && item.name,
            )
            .map((/** @type {any} */ item) => ({
                name: item.name,
                label: item.description,
                fieldName: item.fieldName,
                generatorIds: knownGeneratorIds(searchModel, item),
                alternates: other("dateFilters", item.name),
            })),
        groupBys,
        searchFields: items
            .filter((/** @type {any} */ item) => item.type === "field")
            .map((/** @type {any} */ item) => ({
                fieldName: item.fieldName,
                label: item.description,
                fieldType: item.fieldType,
                relation: searchModel.searchViewFields?.[item.fieldName]?.relation,
                alternates: [
                    ...other("searchFields", item.fieldName),
                    ...other("fields", item.fieldName),
                ],
            })),
    };
}

/**
 * @param {Element} node
 * @param {any} record
 * @returns {boolean}
 */
function isVisible(node, record) {
    const invisible = node.getAttribute("invisible");
    if (!invisible) {
        return true;
    }
    return !evaluateBooleanExpr(invisible, record.evalContextWithVirtualIds);
}

const BUTTON_ATTRIBUTES = [
    "name",
    "type",
    "context",
    "confirm",
    "confirm-title",
    "confirm-label",
    "cancel-label",
    "special",
    "close",
    "args",
];

/**
 * Buttons are read from the arch, not the page: a statusbar or button box
 * folds what does not fit into a dropdown, where the page has no button. A
 * button's `spoken` attribute names phrases, besides its label, that press it:
 * a label a recogniser mishears ("Validar" -> "Balita") gets a phrase it does
 * not ("termina la entrega"), declared beside the label and translated with it.
 *
 * @param {any} archInfo
 * @param {any} record
 * @returns {ButtonTerm[]}
 */
function compileButtons(archInfo, record) {
    /** @type {ButtonTerm[]} */
    const buttons = [];
    const selector = "header button[name], div[name='button_box'] button[name]";
    for (const node of archInfo.xmlDoc.querySelectorAll(selector)) {
        const type = node.getAttribute("type");
        if (!["object", "action"].includes(type) || !isVisible(node, record)) {
            continue;
        }
        const label = (node.getAttribute("string") || node.textContent || "").trim();
        if (!label) {
            continue;
        }
        /** @type {Record<string, any>} */
        const clickParams = {};
        for (const attribute of BUTTON_ATTRIBUTES) {
            if (node.hasAttribute(attribute)) {
                clickParams[attribute] = node.getAttribute(attribute);
            }
        }
        const spoken = (node.getAttribute("spoken") || "")
            .split(";")
            .map((phrase) => phrase.trim())
            .filter(Boolean);
        buttons.push({ label, spoken, clickParams });
    }
    return buttons;
}

/**
 * @param {any} controller
 * @returns {ViewTerms["form"]}
 */
function compileForm(controller, alternates = null) {
    const record = controller?.model?.root;
    const archInfo = controller?.archInfo;
    if (!record || !archInfo?.fieldNodes) {
        return null;
    }
    /** @type {FormFieldTerm[]} */
    const fields = [];
    const seen = new Set();
    for (const node of Object.values(archInfo.fieldNodes)) {
        const field = record.fields[node.name];
        if (!field || seen.has(node.name) || record.isFieldReadonly(node.name)) {
            continue;
        }
        if (
            node.invisible &&
            evaluateBooleanExpr(node.invisible, record.evalContextWithVirtualIds)
        ) {
            continue;
        }
        seen.add(node.name);
        fields.push({
            name: node.name,
            label: node.string || field.string || node.name,
            type: field.type,
            relation: field.relation,
            selection: field.selection,
            alternates: [
                ...(alternates?.formFields[node.name] || []),
                ...(alternates?.fields[node.name] || []),
            ],
        });
    }
    return {
        fields,
        buttons: archInfo.xmlDoc
            ? compileButtons(archInfo, record).map((button) => ({
                  ...button,
                  alternates: alternates?.buttons[button.clickParams.name] || [],
              }))
            : [],
        displayName: record.data.display_name || "",
    };
}

/**
 * @param {import("@web/views/active_view").ActiveView | null} activeView
 * @returns {ViewTerms | null}
 */
function compileView(activeView, alternates = null) {
    if (!activeView) {
        return null;
    }
    const { config, searchModel, controller } = activeView;
    const viewType = config.viewType || "";
    return {
        viewType,
        resModel: searchModel.resModel,
        viewTypes: (config.viewSwitcherEntries || []).map(
            (/** @type {any} */ v) => v.type,
        ),
        ...compileSearch(searchModel, alternates),
        recordCount: controller?.model?.root?.records?.length ?? 0,
        form: viewType === "form" ? compileForm(controller, alternates) : null,
        reports: viewType === "form" ? compileReports(controller) : [],
        canExport:
            viewType !== "form" && typeof controller?.exportRecords === "function",
    };
}

/**
 * The reports of the record's print menu. One bound with a domain is valid for
 * some records only, which the print menu asks the server; it is left out.
 *
 * @param {any} controller
 * @returns {ReportTerm[]}
 */
function compileReports(controller) {
    const reports = controller?.props?.info?.actionMenus?.print || [];
    return reports
        .filter((/** @type {any} */ report) => !("domain" in report))
        .map((/** @type {any} */ report) => ({ id: report.id, name: report.name }));
}

/**
 * What the user can name right now: every menu, the view in front of them
 * unless the home menu covers it, and the commands in scope.
 *
 * @param {{ menu: any, activeView: any, homeMenu?: any, commands?: CommandTerm[], today: any, alternates?: import("../alternates.js").Alternates | null, terms?: import("./terms.js").TermPhrase[] }} sources
 * @returns {Vocabulary}
 */
export function compileVocabulary({
    menu,
    activeView,
    homeMenu,
    commands = [],
    today,
    alternates = null,
    terms = [],
}) {
    return {
        menus: compileMenus(menu, alternates),
        view: homeMenu?.hasHomeMenu ? null : compileView(activeView, alternates?.view),
        commands,
        today,
        terms,
    };
}
