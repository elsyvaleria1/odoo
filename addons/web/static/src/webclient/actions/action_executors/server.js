// @ts-check
/** @odoo-module native */

import { makeContext } from "@web/core/context";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

import { nextActionDepth } from "../action_constants.js";
import { withMarkupHelp } from "../action_help.js";

/** @import { ActionManager } from "../action_service.js" */

/** @import { ActionOptions, ServerAction } from "@web/webclient/actions/action_service" */

/**
 * @param {ServerAction} action
 * @param {ActionOptions} options
 * @param {ActionManager} am
 */
export async function executeServerAction(action, options, am) {
    const viewService = am.viewService;
    /** @type {Record<string, any>} */
    const params = {
        action_id: action.id,
        context: makeContext([user.context, action.context]),
    };
    if (viewService) {
        params.view_options = viewService.requestFlags();
        params.view_context = options.additionalContext || {};
        const known = viewService.knownRunViews(action.id);
        if (known) {
            params.views_known = known;
        }
    }
    const runProm = rpc("/web/action/run", params).then((answer) => {
        if (
            !viewService ||
            typeof answer !== "object" ||
            !answer ||
            !("views_request" in answer)
        ) {
            return answer;
        }
        viewService.rememberRunViews(action.id, answer.views_request);
        if ("views" in answer) {
            viewService.offerViews(answer.views_request, answer.views);
        }
        return answer.action;
    });
    let nextAction = await am.navigation.guard(runProm);
    nextAction = nextAction || { type: "ir.actions.act_window_close" };
    withMarkupHelp(nextAction);
    if (typeof nextAction === "object") {
        nextAction.path ||= action.path;
    }
    const depth = nextActionDepth(options);
    return /** @type {any} */ (
        am.doAction(nextAction, { ...options, _actionDepth: depth })
    );
}
