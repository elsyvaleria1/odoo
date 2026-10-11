/** @odoo-module native */

import { useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { sortBy } from "@web/core/utils/collections/arrays";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { SIDEBAR_SAFE_FIELDS } from "@web_studio/client_action/view_editor/editors/sidebar_safe_fields";

export const hookPositionTolerance = 50;

export function cleanHooks(el) {
    for (const hookEl of el.querySelectorAll(".o_web_studio_nearest_hook")) {
        hookEl.classList.remove("o_web_studio_nearest_hook");
    }
}

export function getActiveHook(el) {
    return el.querySelector(".o_web_studio_nearest_hook");
}

export function isToXpathEquivalentFromXpath(position, toXpath, fromXpath) {
    if (toXpath === fromXpath) {
        return true;
    }
    const toParts = toXpath.split("/");
    const fromParts = fromXpath.split("/");

    if (toParts.slice(0, -1).join("/") !== fromParts.slice(0, -1).join("/")) {
        return false;
    }

    const nodeIdxRegExp = /(\w+)(\[(\d+)\])?/;
    const toMatch = toParts[toParts.length - 1].match(nodeIdxRegExp);
    const fromMatch = fromParts[fromParts.length - 1].match(nodeIdxRegExp);

    if (fromMatch[1] !== toMatch[1]) {
        return false;
    }

    if (
        position === "after" &&
        parseInt(toMatch[3] || 1) + 1 === parseInt(fromMatch[3] || 1)
    ) {
        return true;
    }
    return false;
}

export function getHooks(el) {
    return [...el.querySelectorAll(".o_web_studio_hook")];
}

export function randomName(baseName) {
    const random =
        Math.floor(Math.random() * 10000).toString(32) +
        "_" +
        Number(new Date()).toString(32);
    return `${baseName}_${random}`;
}

export function studioIsVisible(props) {
    return props.studioIsVisible !== undefined ? props.studioIsVisible : true;
}

export function cleanClickedElements(mainEl) {
    for (const el of mainEl.querySelectorAll(".o-web-studio-editor--element-clicked")) {
        el.classList.remove("o-web-studio-editor--element-clicked");
    }
}

export function useStudioRef(ref, onClick) {
    const props = useProps();
    useLayoutEffect(
        (el) => {
            if (el) {
                el.setAttribute("data-studio-xpath", props.studioXpath);
            }
        },
        () => [ref.el],
    );

    if (onClick) {
        const handler = onClick;
        useLayoutEffect(
            (el) => {
                if (el) {
                    el.addEventListener("click", handler, { capture: true });
                    return () => {
                        el.removeEventListener("click", handler);
                    };
                }
            },
            () => [ref.el],
        );
    }
}

export function makeModelErrorResilient(ModelClass, activeActions = { create: true }) {
    function logError(debug) {
        if (!debug) {
            return;
        }
        console.warn(
            "The onchange triggered an error. It may indicate either a faulty call to onchange, or a faulty model python side",
        );
    }
    return class ResilientModel extends ModelClass {
        setup() {
            super.setup(...arguments);
            const orm = this.orm;
            const debug = this.viewContext.debug;
            this.orm = Object.assign(Object.create(orm), {
                async call(model, method) {
                    if (method === "onchange") {
                        if (activeActions.create) {
                            try {
                                return await orm.call.call(orm, ...arguments);
                            } catch {
                                logError(debug);
                            }
                        }
                        return { value: {} };
                    }
                    return orm.call.call(orm, ...arguments);
                },
            });
        }
    };
}

export function getWowlFieldWidgets(
    fieldType,
    currentKey = "",
    blacklistedKeys = [],
    debug = false,
) {
    const wowlFieldRegistry = registry.category("fields");
    const widgets = [];
    for (const [widgetKey, Component] of wowlFieldRegistry.getEntries()) {
        if (widgetKey !== currentKey) {
            if (
                !Component.supportedTypes ||
                !Component.supportedTypes.includes(fieldType)
            ) {
                continue;
            }
            if (widgetKey.includes(".") || blacklistedKeys.includes(widgetKey)) {
                continue;
            }
            if (!debug && !SIDEBAR_SAFE_FIELDS.includes(widgetKey)) {
                continue;
            }
        }
        widgets.push([widgetKey, Component.displayName]);
    }
    return sortBy(widgets, (el) => el[1] || el[0]);
}

export function xpathToLegacyXpathInfo(xpath) {
    const xpathInfo = [];
    const matches = xpath.matchAll(/\/?(\w+|\*)(\[(\d+)\])?/g);
    for (const m of matches) {
        const info = {
            tag: m[1],
            indice: parseInt(m[3] || 1),
        };
        xpathInfo.push(info);
    }
    return xpathInfo;
}

export function fieldsToChoices(fields, availableTypes, filterCallback) {
    let values = Object.values(fields);
    if (filterCallback) {
        values = values.filter(filterCallback);
    }
    if (availableTypes) {
        values = values.filter((f) => availableTypes.includes(f.type));
    }
    return values.map((field) => ({
        label: odoo.debug
            ? `${field.string} (${field.name})`
            : field.string || field.name,
        value: field.name,
    }));
}

export function getStudioNoFetchFields(_fieldNodes, xml) {
    let fieldNames = [];
    const fieldNodes = [];
    if (_fieldNodes && !xml) {
        Object.entries(_fieldNodes)
            .filter(([fNode, field]) => field.attrs && field.attrs.studio_no_fetch)
            .forEach(([fNode, field]) => {
                fieldNames.push(field.name);
                fieldNodes.push(fNode);
            });
    }
    if (xml && !_fieldNodes) {
        fieldNames = Array.from(xml.querySelectorAll(`field[studio_no_fetch="1"]`)).map(
            (n) => n.getAttribute("name"),
        );
    }
    return {
        fieldNames,
        fieldNodes,
    };
}

export function useModelConfigFetchInvisible(model) {
    function fixActiveFields(activeFields) {
        const stack = [activeFields];
        while (stack.length) {
            const activeFields = stack.pop();
            for (const activeField of Object.values(activeFields)) {
                if ("related" in activeField) {
                    stack.push(activeField.related.activeFields);
                }
                delete activeField.invisible;
            }
        }
        return activeFields;
    }

    const load = model.load;
    model.load = (...args) => {
        fixActiveFields(model.config.activeFields);
        return load.call(model, ...args);
    };
}

export function getCurrencyField(fieldsGet) {
    const field = Object.entries(fieldsGet).find(
        ([fName, fInfo]) =>
            fInfo.type === "many2one" && fInfo.relation === "res.currency",
    );
    if (field) {
        return field[0];
    }
}
