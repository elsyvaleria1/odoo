/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

const VIEW_TYPE_KEY = "documentsDefaultViewType";

/** @returns {string|null} the view the Documents app last showed on a large screen */
export function preferredDocumentsViewType() {
    try {
        return browser.localStorage.getItem(VIEW_TYPE_KEY);
    } catch {
        return null;
    }
}

/** @param {"kanban"|"list"} viewType */
export function rememberDocumentsViewType(viewType) {
    try {
        if (browser.localStorage.getItem(VIEW_TYPE_KEY) !== viewType) {
            browser.localStorage.setItem(VIEW_TYPE_KEY, viewType);
        }
    } catch {
        // a preference, not state: without storage the app opens on its default view
    }
}

async function documentActionPreference(env, action, options) {
    const nextAction = await env.services.action.loadAction("document.document_action");
    return env.services.action.doAction(
        {
            ...nextAction,
            context: action.context,
            domain: action.domain,
        },
        { ...options, viewType: preferredDocumentsViewType() },
    );
}

registry
    .category("actions")
    .add("document_action_preference", documentActionPreference);
