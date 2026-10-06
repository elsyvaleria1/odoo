// @ts-check
/** @odoo-module native */

import {
    EventBus,
    onWillStart,
    onWillUpdateProps,
    proxy,
    useProps,
    useScope,
} from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { browser } from "@web/core/browser/browser";
import { SEARCH_KEYS } from "@web/core/constants";
import { useDebugMode } from "@web/core/debug/debug_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { ModelEvent } from "@web/core/events";
import { featureFlag } from "@web/core/feature_flags";
import { RPCError } from "@web/core/network/rpc";
import { defineScope } from "@web/core/scope";
import { useSearchModel } from "@web/core/search_model_hooks";
import { Deferred, Race } from "@web/core/utils/concurrency";
import {
    useIsDestroyed,
    useIsMounted,
    useService,
    useServices,
} from "@web/core/utils/hooks";
import { SignalStore } from "@web/core/utils/reactive";
import { useViewConfig } from "@web/core/view_config_hooks";

import { SampleDataCoordinator } from "./sample_data_coordinator.js";
import { makeSampleORM } from "./sample_server.js";
import { getSearchParamsIssues } from "./search_params_schema.js";

const envScope = defineScope("web/model/model");

const log = makeLogger("web.model");

/**
 * @typedef {{
 * searchModel: ReturnType<typeof useSearchModel> | undefined;
 * config: ReturnType<typeof useViewConfig>;
 * services: Record<string, any>;
 * debug: string;
 * readonly isSmall: boolean;
 * [key: string]: any;
 * }} ViewContext
 */
/** @import { SearchParams } from "@web/model/types" */
/** @import { ServiceFactories as Services } from "services" */
/**
 * @template {Model} [M=Model]
 * @typedef {{new(viewContext: ViewContext, params: Object, services: Object): M; services: string[]; useViewContext(): ViewContext; rendersOnNotify?: boolean; prototype: M; name: string}} ModelConstructor
 */

/** @template {object} [C=ViewContext] */
export class Model extends SignalStore {
    static services = [];

    /** @returns {ViewContext} */
    static useViewContext() {
        const ui = useService("ui");
        return {
            searchModel: useSearchModel(),
            config: useViewConfig(),
            services: useServices(),
            debug: useDebugMode(),
            get isSmall() {
                return ui.isSmall;
            },
        };
    }

    /**
     * @param {C} viewContext
     * @param {Object} params
     * @param {Object} services
     */
    constructor(viewContext, params, services) {
        super();
        this.viewContext = viewContext;
        this.orm = services.orm;
        this.bus = new EventBus();
        this.isReady = false;
        /** @type {number} */
        this.pendingRootLoads = 0;
        /** @type {() => boolean} */
        this.isAlive = params?.isAlive || (() => true);
        /** @type {number} */
        this._updateEpoch = 0;
        /** @type {SampleDataCoordinator} */
        this.sampleData = new SampleDataCoordinator();
        /** @type {any} */
        this.root = undefined;
        /** @type {any} */
        this.metaData = undefined;
        /** @type {any} */
        this.data = undefined;
        /** @type {any} */
        this.config = undefined;
        /** @type {Deferred} */
        this.whenReady = new Deferred();
        this.whenReady.then(() => {
            // Through a proxy of this model, so a component that read
            // `isReady` through its own useState proxy is notified; a bare
            // write on the raw model reaches no subscriber.
            proxy(this).isReady = true;
        });
        this.setup(params, services);
    }

    /**
     * @param {Object} _params
     * @param {Object} _services
     */
    setup(_params, _services) {}

    /** @returns {boolean} */
    get useSampleModel() {
        return this.sampleData.isActive;
    }

    /** @param {boolean} value */
    set useSampleModel(value) {
        this.sampleData.set(value);
    }

    /**
     * True while an already-shown view waits for its root data: a search,
     * a pager move, a sort or a record switch.
     * @returns {boolean}
     */
    get isReloading() {
        return this.isReady && this.pendingRootLoads > 0;
    }

    /**
     * True while a view that painted before its first data waits for it.
     * @returns {boolean}
     */
    get isLoadingFirstData() {
        return !this.isReady && this.pendingRootLoads > 0;
    }

    /**
     * @template T
     * @param {Promise<T>} load
     * @returns {Promise<T>}
     */
    async trackRootLoad(load) {
        const observed = proxy(this);
        observed.pendingRootLoads++;
        log.pipeline("rootLoad", () => ({ pending: this.pendingRootLoads }));
        try {
            return await load;
        } finally {
            observed.pendingRootLoads--;
            log.pipeline("rootLoaded", () => ({ pending: this.pendingRootLoads }));
        }
    }

    /** @param {Partial<SearchParams>} [_params] */
    async load(_params) {}

    /** @returns {boolean} */
    hasData() {
        return true;
    }

    /** @returns {Record<string, Record<string, any>>} */
    getSampleRelatedModels() {
        return {};
    }

    /** @returns {Promise<void> | void} */
    settleBeforeReload() {}

    /** @returns {number} */
    get updateEpoch() {
        return this._updateEpoch;
    }

    notify() {
        // through the proxy: a caller may hold the raw model, and only a
        // proxied write reaches what reads the epoch (a model's raw data)
        proxy(this)._updateEpoch++;
        this.bus.trigger(ModelEvent.UPDATE);
    }
}

/**
 * @template {Model} M
 * @param {M} model
 * @returns {M}
 */
export function useReactiveModel(model) {
    return proxy(model);
}

/** @param {Model} model */
export function provideViewModel(model) {
    envScope.provide({ model });
}

/** @returns {any} */
export function useViewModel() {
    return envScope.use().model;
}

/** @param {any} component */
export function viewModelOf(component) {
    return envScope.readFrom(component).model;
}

/**
 * @param {Record<string, unknown>} props
 * @returns {Object}
 */
function getSearchParams(props) {
    const params = {};
    for (const key of SEARCH_KEYS) {
        if (props[key] !== undefined) {
            params[key] = props[key];
        }
    }
    if (_isSearchParamsValidationEnabled()) {
        const issues = getSearchParamsIssues(params);
        if (issues.length) {
            console.warn(
                `[search-params] ${issues.length} issue(s) at useModel boundary:\n  - ` +
                    issues.join("\n  - "),
            );
        }
    }
    return params;
}

/** @returns {boolean} */
function _isSearchParamsValidationEnabled() {
    return (
        Boolean(odoo.debug) ||
        Boolean(featureFlag("search_params_validation", { default: false }))
    );
}

/**
 * @param {ModelConstructor} ModelClass
 * @returns {Record<string, any>}
 */
function useModelServices(ModelClass) {
    /** @type {Record<string, any>} */
    const services = {};
    for (const key of ModelClass.services) {
        services[key] = useService(/** @type {any} */ (key));
    }
    services.orm = services.orm || useService("orm");
    return services;
}

/**
 * @param {Model} model
 * @param {Record<string, unknown>} props
 * @returns {Promise<any> | any}
 */
function reloadFromProps(model, props) {
    log.lifecycle("reloadFromProps", () => ({
        model: model.constructor.name,
        params: getSearchParams(props),
    }));
    const load = () => model.load(getSearchParams(props));
    const settling = model.settleBeforeReload();
    return settling ? settling.then(load) : load();
}

/**
 * @template {Model} M
 * @param {ModelConstructor<M>} ModelClass
 * @param {(props: Record<string, any>) => Object} buildParams
 * @returns {{ props: Record<string, any>, viewContext: ViewContext, isMounted: () => boolean, model: M }}
 */
function makeModel(ModelClass, buildParams) {
    const props = useProps();
    const viewContext = ModelClass.useViewContext();
    const isDestroyed = useIsDestroyed();
    const isMounted = useIsMounted();
    const componentName = useScope().componentName;
    const services = useModelServices(ModelClass);
    const params = buildParams(props);
    const isAlive = params?.isAlive || (() => !isDestroyed());
    const model = new ModelClass(viewContext, { ...params, isAlive }, services);
    model.isAlive = isAlive;
    log.lifecycle("makeModel", () => ({
        model: ModelClass.name,
        component: componentName,
        services: Object.keys(services),
    }));
    return { props, viewContext, isMounted, model };
}

/**
 * @template {Model} M
 * @param {ModelConstructor<M>} ModelClass
 * @param {Object} params
 * @param {Object} [options]
 * @param {Function} [options.beforeFirstLoad]
 * @returns {M}
 */
export function useModel(ModelClass, params, options = {}) {
    const { props, model } = makeModel(ModelClass, () => params);
    onWillStart(async () => {
        await options.beforeFirstLoad?.();
        await model.load(getSearchParams(props));
        model.whenReady.resolve();
    });
    onWillUpdateProps((nextProps) => reloadFromProps(model, nextProps));
    return model;
}

/**
 * @param {Promise<unknown>} load
 * @param {number | undefined} deadline a `performance.now()` instant
 * @param {() => void} onDeadline called if the deadline comes before the load settles
 * @returns {Promise<void>} settled as the load is, or resolved at the deadline
 */
function loadOrDeadline(load, deadline, onDeadline) {
    const remaining = (deadline ?? 0) - browser.performance.now();
    if (!(remaining > 0)) {
        onDeadline();
        return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
        const timer = browser.setTimeout(() => {
            onDeadline();
            resolve();
        }, remaining);
        load.then(
            () => {
                browser.clearTimeout(timer);
                resolve();
            },
            (error) => {
                browser.clearTimeout(timer);
                reject(error);
            },
        );
    });
}

/**
 * @template {Model} M
 * @param {ModelConstructor<M>} ModelClass
 * @param {Object} params
 * @param {Object} [options]
 * @param {boolean} [options.lazy=false] paint without the data once
 *  `paintDeadline` has passed, instead of waiting for it
 * @param {number} [options.paintDeadline] a `performance.now()` instant; a
 *  lazy model that has its data by then paints once, with it
 * @returns {M}
 */
export function useModelWithSampleData(ModelClass, params, options = {}) {
    if (!(ModelClass.prototype instanceof Model)) {
        throw new Error(`the model class should extend Model`);
    }
    const {
        props: componentProps,
        viewContext,
        isMounted,
        model,
    } = makeModel(ModelClass, (props) => ({
        ...params,
        canUseSampleModel: Boolean(props.useSampleModel),
    }));

    const globalState = componentProps.globalState || {};
    const localState = componentProps.state || {};
    let useSampleModel =
        componentProps.useSampleModel &&
        (!("useSampleModel" in globalState) || globalState.useSampleModel);
    if (useSampleModel && model.hasData === Model.prototype.hasData) {
        console.warn(
            `${ModelClass.name} asks for sample data but does not override hasData().` +
                ` Model.hasData() answers true unconditionally, so the sample model is` +
                ` never loaded and the view stays empty.`,
        );
    }
    model.useSampleModel = false;
    const orm = model.orm;
    let sampleORM = localState.sampleORM;
    if (sampleORM) {
        Object.setPrototypeOf(sampleORM, orm);
    }

    /** @param {Record<string, unknown>} props */
    async function _load(props) {
        const settling = model.settleBeforeReload();
        if (settling) {
            await settling;
        }
        const searchParams = getSearchParams(props);
        await model.load(searchParams);
        if (useSampleModel && !model.hasData()) {
            sampleORM =
                sampleORM ||
                makeSampleORM(componentProps.resModel, componentProps.fields, orm, {
                    ...componentProps.relatedModels,
                    ...model.getSampleRelatedModels(),
                });
            model.orm = sampleORM;
            try {
                await model.load(searchParams);
            } finally {
                model.orm = orm;
            }
            model.useSampleModel = true;
        } else {
            useSampleModel = false;
            model.useSampleModel = useSampleModel;
        }
        model.whenReady.resolve();
        if (isMounted()) {
            model.notify();
        }
    }
    const race = new Race();
    const load = (props) => race.add(_load(props));
    onWillStart(() => {
        const prom = load(componentProps);
        if (!options.lazy) {
            return prom;
        }
        viewContext.config?.claimLoadingFeedback?.();
        let paintedWithoutData = false;
        prom.catch((e) => {
            if (!paintedWithoutData) {
                // nothing was painted: the mount fails with it, like any other
                return;
            }
            if (e instanceof RPCError) {
                viewContext.config.historyBack();
            }
            throw e;
        });
        return loadOrDeadline(prom, options.paintDeadline, () => {
            paintedWithoutData = true;
        });
    });
    onWillUpdateProps((nextProps) => {
        useSampleModel = false;
        load(nextProps);
    });

    useSetupAction({
        getGlobalState() {
            if (componentProps.useSampleModel) {
                return { useSampleModel };
            }
        },
        getLocalState: () => ({ sampleORM }),
    });

    return model;
}
