// @ts-check
/** @odoo-module native */

import { ControllerLifetime } from "@web/core/action_hook";
import { reportUncaught } from "@web/core/errors/error_utils";
import { AppEvent } from "@web/core/events";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { SupersededError } from "@web/core/utils/concurrency";

import { actionStorage } from "./action_storage.js";
import { getActionMode } from "./action_views.js";
import { BlankComponent } from "./blank_component.js";

const actionRegistry = registry.category("actions");

/** @import { Action, ActionManager, Controller } from "./action_service.js" */

/** @type {WeakMap<Controller, ControllerLifetime>} */
const lifetimes = new WeakMap();

/** @param {Controller} controller */
export function lifetimeOf(controller) {
    let lifetime = lifetimes.get(controller);
    if (!lifetime) {
        lifetime = new ControllerLifetime();
        lifetimes.set(controller, lifetime);
    }
    return lifetime;
}

/**
 * @param {Controller[]} controllers
 * @param {Controller[]} stack
 */
export function endUnreachable(controllers, stack) {
    const keptActions = new Set(stack.map((ct) => ct.action));
    const ended = new Set();
    for (const ct of controllers) {
        if (!keptActions.has(ct.action)) {
            ended.add(ct);
            for (const viewController of Object.values(ct.action.controllers ?? {})) {
                ended.add(viewController);
            }
        }
    }
    for (const ct of ended) {
        lifetimeOf(ct).end();
    }
}

/**
 * @param {ActionManager} am
 * @param {Controller[]} nextStack
 */
function replaceStack(am, nextStack) {
    const previous = am.controllerStack;
    am.controllerStack = nextStack;
    endUnreachable(previous, nextStack);
}

export class ActionDispatch {
    /**
     * @param {ActionManager} am
     * @param {Object} params
     * @param {Controller} params.controller
     * @param {Action} params.action
     * @param {Controller[]} params.nextStack
     * @param {Controller[]} [params.baseStack]
     * @param {Controller[]} [params.restoreStackOnError]
     */
    constructor(am, { controller, action, nextStack, baseStack, restoreStackOnError }) {
        this.am = am;
        this.controller = controller;
        this.action = action;
        this.nextStack = nextStack;
        this.baseStack = baseStack ?? am.controllerStack;
        this.restoreStackOnError = restoreStackOnError;
        /** @type {{ current?: Function }} */
        this.removeDialogRef = { current: undefined };
        /** @type {Promise<void>} */
        this.promise = new Promise((resolve, reject) => {
            this._resolve = resolve;
            this._reject = reject;
        });
    }

    /**
     * @param {Object} exporters
     * @param {() => any} exporters.getGlobalState
     * @param {() => any} exporters.getLocalState
     */
    commit({ getGlobalState, getLocalState }) {
        const { am, controller, action, nextStack } = this;
        if (action.target === "new") {
            this._commitDialog();
        } else {
            controller.getGlobalState = getGlobalState;
            controller.getLocalState = getLocalState;
            replaceStack(am, nextStack);
            am.settlePendingDispatch(this);
            am.pushState();

            am.titleService.setParts({ action: controller.displayName });
            actionStorage.setCurrentAction(action._originalAction);
            actionStorage.setLang(user.lang);
        }
        controller.isMounted = true;
        this._resolve();
        am.env.bus.trigger(
            AppEvent.ACTION_MANAGER_UI_UPDATED,
            getActionMode(action, actionRegistry),
        );
    }

    _commitDialog() {
        const { am } = this;
        am.dialog?.remove();
        am.dialog = am.nextDialog;
        am.nextDialog = null;
    }

    /** @returns {Promise<any>} */
    async settled() {
        try {
            return await this.promise;
        } catch (error) {
            if (!(error instanceof SupersededError)) {
                throw error;
            }
        }
    }

    /** @param {{ componentStatus: string }} ctx */
    discard({ componentStatus }) {
        if (!this.controller.isMounted && componentStatus !== "mounted") {
            this._reject(new SupersededError());
            endUnreachable([this.controller], this.am.controllerStack);
        }
    }

    /**
     * @param {Error} error
     * @param {{ componentStatus: string }} ctx
     * @returns {any}
     */
    fail(error, { componentStatus }) {
        const { am, controller, action } = this;
        if (controller.isMounted) {
            reportUncaught(error);
            return;
        }
        if (componentStatus === "mounted") {
            this._reject(new SupersededError());
            am.env.bus.trigger(AppEvent.ACTION_MANAGER_UPDATE, {
                id: am.nextId(),
                Component: BlankComponent,
                componentProps: {
                    onMounted: () => {},
                    withControlPanel: action.type === "ir.actions.act_window",
                },
            });
            reportUncaught(error);
            endUnreachable([controller], am.controllerStack);
            return;
        }
        this._reject(error);
        const settled =
            action.target === "new"
                ? this._releasePendingDialog()
                : this._restoreStack();
        endUnreachable([controller], am.controllerStack);
        return settled;
    }

    _releasePendingDialog() {
        this.removeDialogRef.current?.();
    }

    /** @returns {any} */
    _restoreStack() {
        const { am, controller, baseStack, restoreStackOnError } = this;
        const index = baseStack.findIndex((ct) => ct.jsId === controller.jsId);
        if (index >= 0) {
            replaceStack(am, baseStack);
            return index > 0 ? am.restore(baseStack[index - 1].jsId) : undefined;
        }
        const stack =
            restoreStackOnError?.length &&
            restoreStackOnError.at(-1)?.isMounted &&
            baseStack !== restoreStackOnError
                ? restoreStackOnError
                : baseStack;
        replaceStack(am, stack);
        const lastController = stack.at(-1);
        if (!lastController) {
            am.env.bus.trigger(AppEvent.ACTION_MANAGER_UPDATE, {});
            return;
        }
        if (lastController.jsId !== controller.jsId) {
            return am.restore(lastController.jsId);
        }
    }
}
