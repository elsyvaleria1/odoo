/** @odoo-module native */
import { loadBundle } from "@web/core/assets";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { startMissingServices } from "@web/env";

const actionRegistry = registry.category("actions");

const log = makeLogger("spreadsheet.action_loader");

/**
 * Add a new function client action which loads the spreadsheet bundle, then
 * launch the actual action.
 * The action should be redefine in the bundle with `{ force: true }`
 * and the actual action component or function
 * @param {string} actionName
 * @param {string} [path]
 * @param {string} [displayName]
 */
export function addSpreadsheetActionLazyLoader(actionName, path, displayName) {
    const actionLazyLoader = async (env, action) => {
        log.lifecycle("lazyLoad:start", { actionName });
        const endBundle = log.perf("loadBundle spreadsheet.o_spreadsheet");
        await loadBundle("spreadsheet.o_spreadsheet");
        endBundle({ actionName });

        const endServices = log.perf("startMissingServices");
        await startMissingServices(env);
        endServices({ actionName });

        if (actionRegistry.get(actionName) === actionLazyLoader) {
            log.logic("lazyLoad:actionNotRedefined", { actionName });
            actionRegistry.add(
                actionName,
                () => {
                    const msg = _t("%s couldn't be loaded", actionName);
                    env.services.notification.add(msg, { type: "danger" });
                },
                { force: true },
            );
        }
        log.lifecycle("lazyLoad:done", { actionName });
        return action;
    };
    if (path) {
        actionLazyLoader.path = path;
    }
    if (displayName) {
        actionLazyLoader.displayName = displayName;
    }
    actionRegistry.add(actionName, actionLazyLoader);
}

addSpreadsheetActionLazyLoader("action_download_spreadsheet");
