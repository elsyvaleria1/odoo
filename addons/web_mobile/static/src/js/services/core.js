/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { parseSearchQuery } from "@web/core/browser/router";
import { uniqueId } from "@web/core/utils/functions";

const available = typeof OdooDeviceUtility !== "undefined";
let DeviceUtility;
const deferreds = {};
export const methods = {};

if (available) {
    DeviceUtility = OdooDeviceUtility;
    delete window.OdooDeviceUtility;
}

/**
 * @param {String} name
 * @param {Object} args
 * @returns {Promise}
 */
function native_invoke(name, args) {
    if (args === undefined) {
        args = {};
    }
    const id = uniqueId();
    args = JSON.stringify(args);
    DeviceUtility.execute(name, args, id);
    return new Promise(function (resolve, reject) {
        deferreds[id] = {
            successCallback: resolve,
            errorCallback: reject,
        };
    });
}

/**
 * @param {String} id
 * @param {Object} result
 */
window.odoo.native_notify = function (id, result) {
    if (Object.hasOwn(deferreds, id)) {
        if (result.success) {
            deferreds[id].successCallback(result);
        } else {
            deferreds[id].errorCallback(result);
        }
        delete deferreds[id];
    }
};

const plugins = available ? JSON.parse(DeviceUtility.list_plugins()) : [];
plugins.forEach((plugin) => {
    methods[plugin.name] = function (args) {
        return native_invoke(plugin.action, args);
    };
});

if (methods.hashChange) {
    let currentSearch;
    browser.addEventListener("popstate", function () {
        const search = parseSearchQuery(browser.location.search);
        if (JSON.stringify(currentSearch) !== JSON.stringify(search)) {
            methods.hashChange(search);
        }
        currentSearch = search;
    });
}

class BackButtonListenerError extends Error {}

class BackButtonManager {
    constructor() {
        this._listeners = new Map();
        this._onGlobalBackButton = this._onGlobalBackButton.bind(this);
    }

    /**
     * @param {object} listener
     * @param {function} func
     * @throws {BackButtonListenerError}
     */
    addListener(listener, func) {
        if (!methods.overrideBackButton) {
            return;
        }
        if (this._listeners.has(listener)) {
            throw new BackButtonListenerError("This listener was already registered.");
        }
        this._listeners.set(listener, func);
        if (this._listeners.size === 1) {
            document.addEventListener("backbutton", this._onGlobalBackButton);
            methods.overrideBackButton({ enabled: true });
        }
    }
    /**
     * @param {object} listener
     * @throws {BackButtonListenerError}
     */
    removeListener(listener) {
        if (!methods.overrideBackButton) {
            return;
        }
        if (!this._listeners.has(listener)) {
            throw new BackButtonListenerError(
                "This listener has already been unregistered.",
            );
        }
        this._listeners.delete(listener);
        if (this._listeners.size === 0) {
            document.removeEventListener("backbutton", this._onGlobalBackButton);
            methods.overrideBackButton({ enabled: false });
        }
    }

    /** @param {Event} ev */
    _onGlobalBackButton(ev) {
        const [listener, func] = [...this._listeners].pop();
        if (listener) {
            func(ev);
        }
    }
}

const backButtonManager = new BackButtonManager();

export default {
    BackButtonManager,
    BackButtonListenerError,
    backButtonManager,
    methods,
};
