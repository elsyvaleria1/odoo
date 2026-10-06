// @ts-check

import {
    after,
    beforeEach,
    describe,
    expect,
    getFixture,
    mockSendBeacon,
    test,
} from "@odoo/hoot";
import { Deferred, tick } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    allowServiceStartFailure,
    allowTranslations,
    clearRegistry,
    makeMockEnv,
    makeMockServer,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { appContextOf } from "@web/core/app_context";
import { registry } from "@web/core/registry";
import { _resetCascadeWarningCache } from "@web/core/service_container";
import { runInBundleTransaction } from "@web/core/utils/bundle_transaction";
import {
    makeEnv,
    mountComponent,
    serviceContainerOf,
    startMissingServices,
    startServices,
} from "@web/env";

describe.current.tags("headless");

const servicesRegistry = registry.category("services");

beforeEach(async () => {
    clearRegistry(servicesRegistry);
    await makeMockServer();
    _resetCascadeWarningCache();
});

/**
 * @param {string} name
 * @param {string[]} dependencies
 * @param {(env: import("@web/env").OdooEnv, dependencies: Record<string, any>) => any} factory
 */
function registerService(name, dependencies, factory) {
    servicesRegistry.add(name, {
        dependencies,
        start: factory,
    });
}

/**
 * @param {"warn" | "error"} method
 * @returns {any[][]}
 */
function captureConsole(method) {
    const calls = [];
    const original = console[method];
    console[method] = (/** @type {any[]} */ ...args) => calls.push(args);
    after(() => {
        console[method] = original;
    });
    return calls;
}

/** @returns {{ env: any, started: Promise<void> }} */
function startEnv() {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    return { env, started: startServices(env) };
}

test(`can start a service`, async () => {
    registerService("test", [], () => 17);
    const env = await makeMockEnv();
    expect(/** @type {any} */ (env.services).test).toBe(17);
});

test(`a service throwing synchronously is skipped, not fatal`, async () => {
    allowServiceStartFailure("ouch");
    const errors = captureConsole("error");
    registerService("ouch", [], () => {
        throw new Error("boom");
    });
    registerService("fine", [], () => "ok");

    const { env, started } = startEnv();
    await started;

    expect("ouch" in env.services).toBe(false);
    expect(env.services.fine).toBe("ok");
    expect(errors.length).toBe(1);
    expect(String(errors[0][0])).toMatch(/service "ouch" failed to start \(sync\)/);
});

test(`a service rejecting asynchronously is skipped, not fatal`, async () => {
    allowServiceStartFailure("ouch");
    const errors = captureConsole("error");
    registerService("ouch", [], async () => {
        throw new Error("boom");
    });
    registerService("fine", [], () => "ok");

    const { env, started } = startEnv();
    await started;

    expect("ouch" in env.services).toBe(false);
    expect(env.services.fine).toBe("ok");
    expect(errors.length).toBe(1);
    expect(String(errors[0][0])).toMatch(/service "ouch" failed to start \(async\)/);
});

test(`a failed service does not prevent its dependents from being reported`, async () => {
    allowServiceStartFailure("ouch");
    const errors = captureConsole("error");
    const warnings = captureConsole("warn");
    registerService("ouch", [], () => {
        throw new Error("boom");
    });
    registerService("needsOuch", ["ouch"], () => "never");

    const { env, started } = startEnv();
    await started;

    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({});
    expect(errors.length).toBe(1);
    expect(warnings.length).toBe(1);
    expect(warnings[0][0]).toMatch(/Skipped 1 service\(s\)/);
});

test(`can start an asynchronous service`, async () => {
    const deferred = new Deferred();
    const entered = new Deferred();
    registerService("test", [], async () => {
        expect.step("before");
        entered.resolve();
        const result = await deferred;
        expect.step("after");
        return result;
    });

    const { env, started } = startEnv();
    await entered;
    expect.verifySteps(["before"]);

    deferred.resolve(15);
    await started;
    expect.verifySteps(["after"]);
    expect(/** @type {any} */ (env.services).test).toBe(15);
});

test(`can start a service with a dependency`, async () => {
    registerService("aang", ["appa"], () => expect.step("aang"));
    registerService("appa", [], () => expect.step("appa"));

    await makeMockEnv();
    expect.verifySteps(["appa", "aang"]);
});

test(`get an object containing dependencies as second arg`, async () => {
    registerService("aang", ["appa"], (_, dependencies) => {
        expect.step("aang");
        expect(dependencies).toEqual({ appa: "flying bison" });
    });
    registerService("appa", [], () => {
        expect.step("appa");
        return "flying bison";
    });

    await makeMockEnv();
    expect.verifySteps(["appa", "aang"]);
});

test(`can start two sequentially dependant asynchronous services`, async () => {
    const deferred2 = new Deferred();
    registerService("test2", ["test1"], () => {
        expect.step("test2");
        return deferred2;
    });

    const deferred1 = new Deferred();
    const entered1 = new Deferred();
    registerService("test1", [], () => {
        expect.step("test1");
        entered1.resolve();
        return deferred1;
    });

    registerService("test3", ["test2"], () => {
        expect.step("test3");
    });

    const { started } = startEnv();
    await entered1;
    expect.verifySteps(["test1"]);

    deferred2.resolve();
    await tick();
    expect.verifySteps([]);

    deferred1.resolve();
    await started;
    expect.verifySteps(["test2", "test3"]);
});

test(`can start two independant asynchronous services in parallel`, async () => {
    const deferred1 = new Deferred();
    const entered1 = new Deferred();
    registerService("test1", [], () => {
        expect.step("test1");
        entered1.resolve();
        return deferred1;
    });

    const deferred2 = new Deferred();
    const entered2 = new Deferred();
    registerService("test2", [], () => {
        expect.step("test2");
        entered2.resolve();
        return deferred2;
    });

    registerService("test3", ["test1", "test2"], () => {
        expect.step("test3");
    });

    const { started } = startEnv();
    await Promise.all([entered1, entered2]);
    expect.verifySteps(["test1", "test2"]);

    deferred1.resolve();
    await tick();
    expect.verifySteps([]);

    deferred2.resolve();
    await started;
    expect.verifySteps(["test3"]);
});

test(`startServices: skips a service whose dependency no module registers and reports it (no throw)`, async () => {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    registerService("b", ["a"], () => "b");

    const warnings = [];
    const originalWarn = console.warn;
    console.warn = (...args) => warnings.push(args);
    after(() => {
        console.warn = originalWarn;
    });

    await startServices(env);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({});
    expect(warnings.length).toBe(1);
    expect(warnings[0][0]).toBe(
        '[env] service "b" is not started: no module registers its dependency "a"',
    );

    registerService("a", [], () => "a");
    await startServices(env);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        a: "a",
        b: "b",
    });
});

test(`startMissingServices: starts late-registered services without a registry listener`, async () => {
    const env = makeEnv();
    await startServices(env);
    serviceContainerOf(env).stopListening();
    registerService("provider", [], () => "p");
    registerService("consumer", ["provider"], (_env, deps) => `${deps.provider}-c`);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({});

    await startMissingServices(env);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        provider: "p",
        consumer: "p-c",
    });

    await startMissingServices(env);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        provider: "p",
        consumer: "p-c",
    });
});

test(`a queued startup pass runs even if the in-flight pass rejects`, async () => {
    allowServiceStartFailure("boom");
    const errors = captureConsole("error");
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    const deferredBoom = new Deferred();
    const enteredBoom = new Deferred();
    let boomStarts = 0;
    registerService("boom", [], () => {
        boomStarts++;
        enteredBoom.resolve();
        return boomStarts === 1 ? deferredBoom : "recovered";
    });

    const p1 = startMissingServices(env);
    await enteredBoom;

    registerService("good", [], () => "g");
    const p2 = startMissingServices(env);

    deferredBoom.reject(new Error("boom"));
    await p1;
    await p2;

    expect(Reflect.get(env.services, "good")).toBe("g");
    expect(Reflect.get(env.services, "boom")).toBe("recovered");
    expect(errors.length).toBe(1);
    expect(String(errors[0][0])).toMatch(/service "boom" failed to start \(async\)/);
});

test(`startServices: cascade-skips transitive consumers when a dep is missing`, async () => {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    registerService("c", ["b"], () => "c");
    registerService("b", ["a"], () => "b");

    const warnings = [];
    const originalWarn = console.warn;
    console.warn = (...args) => warnings.push(args);
    after(() => {
        console.warn = originalWarn;
    });

    await startServices(env);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({});
    expect(warnings.length).toBe(1);
    expect(warnings[0][0]).toBe(
        '[env] service "b" is not started: no module registers its dependency "a"; nor are its dependents c',
    );
});

test(`registry UPDATE while missing-dep leftovers exist starts the new service (no false circular throw)`, async () => {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    registerService("b", ["a"], () => "b");

    const warnings = [];
    const originalWarn = console.warn;
    console.warn = (...args) => warnings.push(args);
    after(() => {
        console.warn = originalWarn;
    });

    await startServices(env);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({});

    registerService("standalone", [], () => "s");
    await tick();
    await tick();
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        standalone: "s",
    });
});

test(`startServices: still throws on genuine circular dependency`, async () => {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    registerService("x", ["y"], () => "x");
    registerService("y", ["x"], () => "y");

    await expect(startServices(env)).rejects.toThrow(
        /Circular service dependency detected/,
    );
});

async function captureWarns(/** @type {any} */ body) {
    const captured = [];
    const original = console.warn;
    console.warn = (...args) => captured.push(args);
    try {
        await body();
    } finally {
        console.warn = original;
    }
    return captured;
}

test(`a provider registered after several awaits warns about nothing and starts its consumer`, async () => {
    patchWithCleanup(odoo, { debug: "1" });

    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    const warns = await captureWarns(async () => {
        registerService("late_consumer", ["late_provider"], () => "late_consumer");
        await tick();
        await tick();
        registerService("late_provider", [], () => "late_provider");
        await startServices(env);
    });
    expect(warns).toEqual([]);
    expect(/** @type {Record<string, unknown>} */ (env.services).late_consumer).toBe(
        "late_consumer",
    );
});

test(`a dependency registered later in the same bundle is not reported, and its consumer starts`, async () => {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    const warns = await captureWarns(async () => {
        await runInBundleTransaction(async () => {
            registerService("bundle_consumer", ["bundle_provider"], () => "consumer");
            await startServices(env);
            await tick();
            await tick();
            registerService("bundle_provider", [], () => "provider");
        });
    });
    expect(warns).toEqual([]);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        bundle_consumer: "consumer",
        bundle_provider: "provider",
    });
});

test(`a dependency still unregistered when its bundle settles is reported then, not before`, async () => {
    const warnings = captureConsole("warn");
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    await runInBundleTransaction(async () => {
        registerService("stranded", ["never_registered"], () => "stranded");
        await startServices(env);
        await tick();
        expect(warnings).toEqual([]);
    });
    expect(warnings.length).toBe(1);
    expect(warnings[0][0]).toBe(
        '[env] service "stranded" is not started: no module registers its dependency "never_registered"',
    );
});

/** @param {string} bundle */
function addPageBundleScript(bundle) {
    const script = document.createElement("script");
    script.type = "text/x-inert";
    script.dataset.bridge = bundle;
    getFixture().append(script);
}

test(`a page bundle still evaluating holds the report; its late provider is not reported`, async () => {
    const warnings = captureConsole("warn");
    addPageBundleScript("test.env_late_provider");
    registerService("page_consumer", ["page_provider"], () => "consumer");
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());

    await startServices(env);
    registerService("page_provider", [], () => "provider");
    odoo.loader.registerNativeModules({}, "test.env_late_provider");
    await tick();
    await tick();

    expect(warnings).toEqual([]);
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        page_consumer: "consumer",
        page_provider: "provider",
    });
});

test(`a page bundle still evaluating holds the report of a truly missing dependency until it registers`, async () => {
    const warnings = captureConsole("warn");
    addPageBundleScript("test.env_missing_provider");
    registerService("page_orphan", ["page_nowhere"], () => "orphan");
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());

    await startServices(env);
    await tick();
    expect(warnings).toEqual([]);

    odoo.loader.registerNativeModules({}, "test.env_missing_provider");
    expect(warnings.length).toBe(1);
    expect(warnings[0][0]).toBe(
        '[env] service "page_orphan" is not started: no module registers its dependency "page_nowhere"',
    );
});

test(`a dependency the env provides directly is not reported`, async () => {
    registerService("uses_provided", ["provided"], (_env, deps) => deps.provided);
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    Object.assign(env.services, { provided: "given" });
    const warns = await captureWarns(() => startServices(env));
    expect(warns).toEqual([]);
    expect(/** @type {any} */ (env.services).uses_provided).toBe("given");
});

test(`unregistered-dependency report: deduped across startServices calls with the same shape`, async () => {
    registerService("dedup_b", ["dedup_a"], () => "dedup_b");

    const env1 = makeEnv();
    after(() => serviceContainerOf(env1).stopListening());
    const env2 = makeEnv();
    after(() => serviceContainerOf(env2).stopListening());

    const warns = await captureWarns(async () => {
        await startServices(env1);
        await startServices(env2);
    });
    expect(warns.length).toBe(1);
    expect(warns[0][0]).toMatch(/dedup_b/);
});

test(`unregistered-dependency report: re-fires when the shape changes`, async () => {
    registerService("shape_b", ["shape_a"], () => "shape_b");

    const env1 = makeEnv();
    after(() => serviceContainerOf(env1).stopListening());
    const warns = await captureWarns(async () => {
        await startServices(env1);

        registerService("shape_d", ["shape_c"], () => "shape_d");
        const env2 = makeEnv();
        after(() => serviceContainerOf(env2).stopListening());
        await startServices(env2);
    });
    expect(warns.length).toBe(2);
    expect(warns[0][0]).toMatch(/shape_b/);
    expect(warns[1][0]).toMatch(/shape_d/);
});

test(`startServices: waits for all synchronous code before attempting to start services`, async () => {
    const env = makeEnv();
    after(() => serviceContainerOf(env).stopListening());
    registerService("b", ["a"], () => "b");

    const serviceStartingPromise = startServices(env);
    registerService("a", [], () => "a");

    await serviceStartingPromise;
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        a: "a",
        b: "b",
    });
});

test(`mountComponent creates an env and sets the application as root when no env is provided`, async () => {
    allowTranslations();
    registerService("my_service", [], () => "a");

    class Root extends Component {
        static template = xml`Root`;
        static props = null;
        props = useProps(this.constructor.props);
    }
    const app = await mountComponent(Root, getFixture());
    const env = appContextOf(app);
    after(() => {
        delete odoo.__WOWL_DEBUG__;
        serviceContainerOf(env).stopListening();
    });
    expect(/** @type {Record<string, unknown>} */ (env.services)).toEqual({
        my_service: "a",
    });
    expect(odoo.__WOWL_DEBUG__.root).toBeInstanceOf(Root);
    expect(getFixture()).toHaveText("Root");
});

test(`mountComponent uses the env when provided and doesn't start the services`, async () => {
    allowTranslations();
    registerService("my_service", [], () => {
        expect.step("starting myService");
        return "a";
    });

    const env = makeEnv();
    expect.verifySteps([]);
    await startServices(env);
    after(() => serviceContainerOf(env).stopListening());
    expect.verifySteps(["starting myService"]);

    class Root extends Component {
        static template = xml`Root`;
        static props = null;
        props = useProps(this.constructor.props);
    }

    const app = await mountComponent(Root, getFixture(), { env });
    expect.verifySteps([]);
    expect(appContextOf(app).services).toBe(env.services);
    expect(odoo.__WOWL_DEBUG__).toBe(undefined);
    expect(getFixture()).toHaveText("Root");
});

test(`mountComponent: can pass props to the root component`, async () => {
    class Root extends Component {
        static template = xml`<t t-out="this.props.text"/>`;
        static props = null;
        props = useProps(this.constructor.props);
    }

    const app = await mountComponent(Root, getFixture(), {
        props: { text: "text from props" },
    });
    after(() => {
        delete odoo.__WOWL_DEBUG__;
        serviceContainerOf(appContextOf(app)).stopListening();
    });
    expect(getFixture()).toHaveText("text from props");
});

test(`env.isReady is resolved after services are loaded`, async () => {
    const deferred = new Deferred();

    const entered = new Deferred();
    registerService("test", [], async (env) => {
        expect.step("before");
        env.isReady.then(() => {
            expect.step("env ready");
        });
        entered.resolve();

        const result = await deferred;
        expect.step("after");
        return result;
    });

    const { started } = startEnv();
    await entered;
    expect.verifySteps(["before"]);

    deferred.resolve();
    await started;
    await Promise.resolve();
    expect.verifySteps(["after", "env ready"]);
});

const teardownProbe = { destroyed: 0 };

test("service disposers run when the test env is torn down", async () => {
    registry.category("services").add("zz_teardown_probe", {
        start() {
            return {
                destroy() {
                    teardownProbe.destroyed++;
                },
            };
        },
    });
    await makeMockEnv();
    expect(teardownProbe.destroyed).toBe(0);
});

test("the previous test's service disposer actually ran", async () => {
    expect(teardownProbe.destroyed).toBe(1);
});

describe("service-start beacon", () => {
    /** @returns {Blob[]} */
    function spyBeacon() {
        const blobs = [];
        mockSendBeacon((_url, blob) => {
            blobs.push(blob);
            return true;
        });
        return blobs;
    }

    /** @param {Blob} blob */
    async function payloadOf(blob) {
        return JSON.parse(await blob.text());
    }

    test("a service throwing synchronously is beaconed", async () => {
        allowServiceStartFailure("beacon-sync-fail");
        const errors = captureConsole("error");
        const blobs = spyBeacon();
        registerService("beacon-sync-fail", [], () => {
            throw new TypeError("cannot read subscribe of undefined");
        });

        const { started } = startEnv();
        await started;

        expect(blobs).toHaveLength(1);
        const payload = await payloadOf(blobs[0]);
        expect(payload.kind).toBe("service_start");
        expect(payload.message).toBe(
            'service "beacon-sync-fail" failed to start (sync)',
        );
        expect(payload.cause).toInclude("cannot read subscribe of undefined");
        expect(errors.length).toBe(1);
    });

    test("a service rejecting asynchronously is beaconed", async () => {
        allowServiceStartFailure("beacon-async-fail");
        const blobs = spyBeacon();
        registerService("beacon-async-fail", [], async () => {
            throw new RangeError("nope");
        });

        const { started } = startEnv();
        await started;

        expect(blobs).toHaveLength(1);
        const payload = await payloadOf(blobs[0]);
        expect(payload.kind).toBe("service_start");
        expect(payload.message).toBe(
            'service "beacon-async-fail" failed to start (async)',
        );
        expect(payload.cause).toInclude("RangeError: nope");
    });

    test("dependents skipped by a failed service are NOT beaconed", async () => {
        allowServiceStartFailure("beacon-base-fail");
        const blobs = spyBeacon();
        registerService("beacon-base-fail", [], () => {
            throw new Error("base down");
        });
        registerService("beacon-dependent", ["beacon-base-fail"], () => "never");

        const { env, started } = startEnv();
        await started;

        expect(blobs).toHaveLength(1);
        expect((await payloadOf(blobs[0])).message).toInclude("beacon-base-fail");
        expect("beacon-dependent" in env.services).toBe(false);
    });

    test("a dependency no module registers is beaconed as a service that did not start", async () => {
        captureConsole("warn");
        const blobs = spyBeacon();
        registerService("beacon-orphan", ["beacon-nowhere"], () => "never");

        const { started } = startEnv();
        await started;

        expect(blobs).toHaveLength(1);
        const payload = await payloadOf(blobs[0]);
        expect(payload.kind).toBe("service_start");
        expect(payload.message).toBe(
            'service "beacon-orphan" is not started: no module registers its dependency "beacon-nowhere"',
        );
    });

    test("a failed service still lets the app boot", async () => {
        allowServiceStartFailure("beacon-boot-fail");
        spyBeacon();
        registerService("beacon-boot-fail", [], () => {
            throw new Error("down");
        });
        registerService("beacon-boot-fine", [], () => "ok");

        const { env, started } = startEnv();
        await expect(started).resolves.toBe(undefined);
        expect(env.services["beacon-boot-fine"]).toBe("ok");
    });
});

test(`makeAppConfig carries the directives and globals every root needs, overrides last`, async () => {
    const { makeAppConfig, customDirectives, globalValues } = await import("@web/env");
    const config = makeAppConfig(undefined, { name: "probe", dev: false });
    expect(config.customDirectives).toBe(customDirectives);
    expect(config.globalValues).toBe(globalValues);
    expect(config.name).toBe("probe");
    expect(config.dev).toBe(false);
    expect(typeof config.getTemplate).toBe("function");
    expect(typeof config.translateFn).toBe("function");
    expect(config.translatableAttributes).toEqual(["data-tooltip"]);
});
