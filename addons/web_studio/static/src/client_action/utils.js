/** @odoo-module native */
import { useProps } from "@odoo/owl";
import { appScope, useAppContext } from "@web/core/app_context";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { provideServices } from "@web/core/utils/hooks";

export function getFieldsInArch(xmlDoc) {
    const res = [];
    const isInvisible = ["True", "1", "true"];
    xmlDoc.querySelectorAll("field").forEach((el) => {
        if (!el.parentElement.closest("field,groupby")) {
            const invisible =
                el.getAttribute("invisible") || el.getAttribute("column_invisible");
            const dataUsedBy = el.getAttribute("data-used-by");
            if (dataUsedBy) {
                return;
            }
            if (!invisible || !isInvisible.includes(invisible)) {
                res.push(el.getAttribute("name"));
            }
        }
    });
    return res;
}

export function useDialogConfirmation({ confirm, cancel, before, close }) {
    before = before || (() => {});
    confirm = confirm || (() => {});
    cancel = cancel || (() => {});
    if (!close) {
        const props = useProps();
        close = () => props.close();
    }

    let isProtected = false;
    async function canExecute() {
        if (isProtected) {
            return false;
        }
        isProtected = true;
        await before();
        return true;
    }

    async function execute(cb, ...args) {
        let succeeded;
        try {
            succeeded = await cb(...args);
        } catch (e) {
            close();
            throw e;
        }
        if (succeeded === undefined || succeeded) {
            return close();
        }
        isProtected = false;
    }

    async function _confirm(...args) {
        if (!(await canExecute())) {
            return;
        }
        return execute(confirm, ...args);
    }

    async function _cancel(...args) {
        if (!(await canExecute())) {
            return;
        }
        return execute(cancel, ...args);
    }

    useDialogContext().dialogData.dismiss = () => _cancel();

    return { confirm: _confirm, cancel: _cancel };
}

export function memoizeOnce(callback) {
    let key, value;
    return function (...args) {
        if (key === args[0]) {
            return value;
        }
        key = args[0];
        value = callback.call(this, ...args);
        return value;
    };
}

export function provideHostedStudioEnv(env) {
    appScope.provide(env);
}

/**
 * @params
 * @params
 */
function topologicalSort(elems, getDependencies) {
    const result = [];
    const visited = new Set();
    function visit(n) {
        if (visited.has(n)) {
            return;
        }
        visited.add(n);
        if (!elems.includes(n)) {
            return;
        }
        for (const dep of getDependencies(n)) {
            visit(dep);
        }
        result.push(n);
    }

    for (const el of elems) {
        visit(el);
    }

    return result;
}

/** @params */
export function useServicesOverrides(overrides) {
    const services = Object.create(useAppContext().services);

    provideServices(services);
    const env = useAppContext();
    const getDependencies = (name) => overrides[name]?.dependencies || [];
    const topoSorted = topologicalSort(Object.keys(overrides), getDependencies);

    for (const servName of topoSorted) {
        services[servName] = overrides[servName].start(env, services);
    }
}
