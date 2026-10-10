// @ts-check

import { after, describe, expect, getFixture, test } from "@odoo/hoot";
import { App, Component, TemplateSet, xml } from "@odoo/owl";
import { patchTranslations, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { assets } from "@web/core/assets";
import {
    precompiledTemplatesService,
    precompiledTemplatesUrl,
} from "@web/core/precompiled_templates";
import { TemplateCompileCache } from "@web/core/template_compile_cache";
import {
    getCompiledDevTemplate,
    getCompiledTemplate,
    getTemplate,
    inlineTemplateKey,
    TemplateRegistry,
    templates,
} from "@web/core/templates";
import { appTranslateFn } from "@web/core/translation";
import { makeAppConfig } from "@web/env";
import { session } from "@web/session";

describe.current.tags("headless");

const URL_A = "/addon_a/static/src/a.xml";
const URL_B = "/addon_b/static/src/b.xml";
const URL_C = "/addon_c/static/src/c.xml";

/** @param {TemplateRegistry} registry */
function registerBundle(registry) {
    registry.registerTemplate(
        "pc.Parent",
        URL_A,
        `<div t-name="pc.Parent" class="parent"><span title="Greeting">Hello</span></div>`,
    );
    registry.registerTemplateExtension(
        "pc.Parent",
        URL_B,
        `<t t-inherit="pc.Parent" t-inherit-mode="extension"><xpath expr="//span" position="after"><b>World</b></xpath></t>`,
    );
    registry.registerTemplate(
        "pc.Child",
        URL_B,
        `<t t-name="pc.Child" t-inherit="pc.Parent"><xpath expr="//b" position="replace"><i>Child</i></xpath></t>`,
    );
}

/**
 * What the server ships: every template of the bundle, resolved and signed
 * by a registry that saw exactly the bundle.
 */
function precompileBundle({ dev = false } = {}) {
    const server = new TemplateRegistry();
    registerBundle(server);
    const compiler = /** @type {any} */ (
        new TemplateSet(/** @type {any} */ (makeAppConfig(undefined, { dev })))
    );
    /** @type {Record<string, [string, string[], any]>} */
    const compiled = {};
    for (const name of Object.keys(server.templates)) {
        const fn = compiler._compileTemplate(name, server.getTemplate(name));
        const chain = server.inheritanceChain(name);
        compiled[name] = [
            /** @type {string} */ (server.resolutionSignature(chain)),
            chain,
            fn,
        ];
    }
    return compiled;
}

function pageWithBundle() {
    const page = new TemplateRegistry();
    registerBundle(page);
    page.registerCompiledTemplates(precompileBundle());
    return page;
}

/**
 * @param {(name: string) => any} source
 * @param {string} template
 */
async function render(source, template) {
    class Root extends Component {
        static template = template;
    }
    const target = document.createElement("div");
    getFixture().append(target);
    const app = new App(
        /** @type {any} */ ({
            ...makeAppConfig(undefined, { dev: false }),
            getTemplate: source,
        }),
    );
    after(() => app.destroy());
    await app.createRoot(Root).mount(target);
    return target.innerHTML;
}

test("a precompiled template is served without resolving it in the browser", () => {
    const page = pageWithBundle();
    for (const name of ["pc.Parent", "pc.Child"]) {
        expect(page.getCompiledTemplate(name)).toBe(page.compiled.prod.named[name].fn);
    }
    expect(page.processedTemplates.size).toBe(0);
    expect(Object.keys(page.parsedTemplates)).toEqual([]);
});

test("an extension registered after the bundle sends its target back to the browser compiler", () => {
    const page = pageWithBundle();
    page.registerTemplateExtension(
        "pc.Parent",
        URL_C,
        `<t t-inherit="pc.Parent" t-inherit-mode="extension"><xpath expr="//span" position="before"><em>Late</em></xpath></t>`,
    );
    const parent = page.getCompiledTemplate("pc.Parent");
    expect(parent).toBeInstanceOf(Element);
    expect(/** @type {Element} */ (parent).outerHTML).toInclude(">Late</em>");
    // a primary child resolves its parent as of its own block, which the late
    // extension follows: the browser would compile exactly what was shipped
    expect(page.getCompiledTemplate("pc.Child")).toBe(
        page.compiled.prod.named["pc.Child"].fn,
    );
    expect(
        /** @type {Element} */ (page.getTemplate("pc.Child")).outerHTML,
    ).not.toInclude("Late");
});

test("a bundle loaded into the page keeps its resolution of a shared template, whichever artifact lands last", () => {
    const late = `<t t-inherit="pc.Parent" t-inherit-mode="extension"><xpath expr="//span" position="before"><em>Late</em></xpath></t>`;
    // the lazy bundle's server compiled pc.Parent after the page's bundle
    const server = new TemplateRegistry();
    registerBundle(server);
    server.registerTemplateExtension("pc.Parent", URL_C, late);
    const compiler = /** @type {any} */ (
        new TemplateSet(/** @type {any} */ (makeAppConfig(undefined, { dev: false })))
    );
    const chain = server.inheritanceChain("pc.Parent");
    const lazyFn = compiler._compileTemplate(
        "pc.Parent",
        server.getTemplate("pc.Parent"),
    );
    const page = new TemplateRegistry();
    registerBundle(page);
    page.registerTemplateExtension("pc.Parent", URL_C, late);
    page.registerCompiledTemplates({
        "pc.Parent": [
            /** @type {string} */ (server.resolutionSignature(chain)),
            chain,
            lazyFn,
        ],
    });
    page.registerCompiledTemplates(precompileBundle());
    expect(page.getCompiledTemplate("pc.Parent")).toBe(lazyFn);
});

test("an extension the server never saw, registered before the bundle, is not skipped", () => {
    const page = new TemplateRegistry();
    page.registerTemplate(
        "pc.Parent",
        URL_A,
        `<div t-name="pc.Parent" class="parent"><span title="Greeting">Hello</span></div>`,
    );
    page.registerTemplateExtension(
        "pc.Parent",
        URL_C,
        `<t t-inherit="pc.Parent" t-inherit-mode="extension"><xpath expr="//span" position="before"><em>Early</em></xpath></t>`,
    );
    registerBundle(page);
    page.registerCompiledTemplates(precompileBundle());
    for (const name of ["pc.Parent", "pc.Child"]) {
        const template = page.getCompiledTemplate(name);
        expect(template).toBeInstanceOf(Element);
        expect(/** @type {Element} */ (template).outerHTML).toInclude("Early");
    }
});

test("a template processor or a url filter disables what they would change", () => {
    const processed = pageWithBundle();
    processed.registerTemplateProcessor(() => {});
    expect(processed.getCompiledTemplate("pc.Child")).toBeInstanceOf(Element);

    const filtered = pageWithBundle();
    filtered.setUrlFilters([(url) => url !== URL_B]);
    const parent = filtered.getCompiledTemplate("pc.Parent");
    expect(parent).toBeInstanceOf(Element);
    expect(/** @type {Element} */ (parent).outerHTML).not.toInclude("World");
});

test("a template the page did not register is left to OWL", () => {
    const page = pageWithBundle();
    expect(page.getCompiledTemplate("pc.Unknown")).toBe(null);
});

test("precompiled and browser-compiled templates render the same translated markup", async () => {
    patchTranslations({ addon_a: { Hello: "Bonjour", Greeting: "Salutation" } });
    const page = pageWithBundle();
    const runtime = new TemplateRegistry();
    registerBundle(runtime);
    for (const name of ["pc.Parent", "pc.Child"]) {
        const precompiled = await render((n) => page.getCompiledTemplate(n), name);
        const compiled = await render((n) => runtime.getTemplate(n), name);
        expect(precompiled).toBe(compiled);
        expect(precompiled).toInclude("Bonjour");
        expect(precompiled).toInclude(`title="Salutation"`);
    }
    expect(page.processedTemplates.size).toBe(0);
});

test("a precompiled template never reaches the browser's compile cache", async () => {
    const page = pageWithBundle();
    class Root extends Component {
        static template = "pc.Child";
    }
    const app = /** @type {any} */ (
        new App(
            /** @type {any} */ ({
                ...makeAppConfig(undefined, { dev: false }),
                getTemplate: (/** @type {string} */ name) =>
                    page.getCompiledTemplate(name),
            }),
        )
    );
    after(() => app.destroy());
    const cache = new TemplateCompileCache({ db: null, scope: "owl/en_US/-" });
    cache.install(app);
    await app.createRoot(Root).mount(getFixture());
    expect(getFixture()).toHaveInnerHTML(
        `<span title="Greeting">Hello</span><i>Child</i>`,
    );
    expect(cache.misses).toBe(0);
    expect(cache.code.size).toBe(0);
});

test("only an app compiling with the default options takes precompiled templates", () => {
    expect(makeAppConfig(undefined, { dev: false }).getTemplate).toBe(
        getCompiledTemplate,
    );
    expect(makeAppConfig(undefined, { dev: true }).getTemplate).toBe(
        getCompiledDevTemplate,
    );
    expect(
        makeAppConfig(undefined, {
            dev: false,
            translateFn: (/** @type {string} */ s) => s,
        }).getTemplate,
    ).toBe(getTemplate);
    expect(
        makeAppConfig(undefined, {
            dev: false,
            translatableAttributes: ["data-tooltip"],
        }).getTemplate,
    ).toBe(getTemplate);
    expect(makeAppConfig(undefined, { dev: false }).translateFn).toBe(appTranslateFn);
});

test("the precompiled artifact is addressed by bundle, checksum, language, translations, dev mode and assets params", () => {
    const localization = { code: "fr_BE", translationsHash: "f00d" };
    expect(
        precompiledTemplatesUrl("web.assets_web", "0123456789abcdef", localization),
    ).toBe("/web/assets/owl/0123456789abcdef/fr_BE/f00d/web.assets_web.js");
    expect(
        precompiledTemplatesUrl(
            "web.assets_web",
            "0123456789abcdef",
            localization,
            true,
        ),
    ).toBe("/web/assets/owl/0123456789abcdef/fr_BE/f00d/web.assets_web.dev.js");
    expect(
        precompiledTemplatesUrl(
            "web.assets_frontend_lazy",
            "0123",
            localization,
            false,
            {
                website_id: 2,
            },
        ),
    ).toBe(
        "/web/assets/owl/0123/fr_BE/f00d/web.assets_frontend_lazy.js?assets_params=%7B%22website_id%22%3A2%7D",
    );
});

test("an inline xml template is served by its content, whatever name xml gave it", async () => {
    const source = `<p class="inline" title="Greeting">Hello <t t-out="1 + 1"/></p>`;
    const name = xml`<p class="inline" title="Greeting">Hello <t t-out="1 + 1"/></p>`;
    const compiler = /** @type {any} */ (
        new TemplateSet(/** @type {any} */ (makeAppConfig(undefined, { dev: false })))
    );
    const page = new TemplateRegistry();
    const fn = compiler._compileTemplate("server", source);
    page.registerCompiledTemplates({}, { [inlineTemplateKey(source)]: fn });

    expect(page.getCompiledTemplate(name)).toBe(fn);
    expect(page.getCompiledTemplate(name, true)).toBe(null);
    expect(page.getCompiledTemplate(xml`<p>other</p>`)).toBe(null);

    class Root extends Component {
        static template = name;
    }
    const app = /** @type {any} */ (
        new App(
            /** @type {any} */ ({
                ...makeAppConfig(undefined, { dev: false }),
                getTemplate: (/** @type {string} */ n) => page.getCompiledTemplate(n),
            }),
        )
    );
    after(() => app.destroy());
    const compile = app._compileTemplate;
    let compiled = 0;
    app._compileTemplate = (/** @type {any[]} */ ...args) => {
        compiled++;
        return compile.apply(app, args);
    };
    await app.createRoot(Root).mount(getFixture());
    expect(getFixture()).toHaveInnerHTML(
        `<p class="inline" title="Greeting">Hello 2</p>`,
    );
    expect(compiled).toBe(0);
});

test("a dev-mode app takes the templates compiled in dev mode, and only those", () => {
    const page = new TemplateRegistry();
    registerBundle(page);
    page.registerCompiledTemplates(precompileBundle());
    const dev = precompileBundle({ dev: true });
    expect(page.getCompiledTemplate("pc.Parent", true)).toBeInstanceOf(Element);
    page.registerCompiledTemplates(dev, {}, { dev: true });
    expect(page.getCompiledTemplate("pc.Parent", true)).toBe(dev["pc.Parent"][2]);
    expect(page.getCompiledTemplate("pc.Parent")).toBe(
        page.compiled.prod.named["pc.Parent"].fn,
    );
    expect(page.getCompiledTemplate("pc.Parent")).not.toBe(dev["pc.Parent"][2]);
});

test("a bundle's compiled templates are awaited once a listener loads them", async () => {
    const page = new TemplateRegistry();
    /** @type {() => void} */
    let arrive = () => {};
    page.bundleListeners.add(
        () =>
            new Promise((resolve) => {
                arrive = () => resolve(undefined);
            }),
    );
    page.registerTemplateBundle("pc.bundle", "0123456789abcdef");
    let settled = false;
    const loaded = page.compiledTemplatesLoaded().then(() => {
        settled = true;
    });
    await Promise.resolve();
    expect(settled).toBe(false);
    arrive();
    await loaded;
    expect(settled).toBe(true);
    expect(page.compiledLoads.size).toBe(0);
});

test("a lazy bundle's registrations wait for its compiled templates", async () => {
    const page = pageWithBundle();
    /** @type {() => void} */
    let arrive = () => {};
    page.bundleListeners.add(
        () =>
            new Promise((resolve) => {
                arrive = () => resolve(undefined);
            }),
    );
    page.registerTemplateBundle("pc.lazy", "0123456789abcdef", {}, () =>
        page.registerTemplateExtension(
            "pc.Parent",
            URL_C,
            `<t t-inherit="pc.Parent" t-inherit-mode="extension"><xpath expr="//span" position="before"><em>Late</em></xpath></t>`,
        ),
    );
    const loaded = page.compiledTemplatesLoaded();
    await Promise.resolve();
    expect(page.getCompiledTemplate("pc.Parent")).toBe(
        page.compiled.prod.named["pc.Parent"].fn,
    );
    arrive();
    await loaded;
    expect(
        /** @type {Element} */ (page.getCompiledTemplate("pc.Parent")).outerHTML,
    ).toInclude(">Late</em>");
});

test("a bundle registers at once when no listener loads its compiled templates", () => {
    const page = new TemplateRegistry();
    page.registerTemplateBundle("pc.bundle", "0123456789abcdef", {}, () =>
        registerBundle(page),
    );
    expect(Object.keys(page.templates)).toEqual(["pc.Parent", "pc.Child"]);
    expect(page.compiledLoads.size).toBe(0);
});

test("a page whose server has no precompiler neither asks for an artifact nor waits", async () => {
    patchWithCleanup(session, {
        precompiled_templates: false,
        await_precompiled_templates: true,
    });
    const listeners = templates.bundleListeners.size;
    await precompiledTemplatesService.start(
        { debug: "" },
        { localization: { code: "en_US", translationsHash: "0123456789abcdef" } },
    );
    expect(templates.bundleListeners.size).toBe(listeners);
});

test("a page that compiles in the browser has OWL's compiler before the service starts", async () => {
    const compiler = TemplateSet.compiler;
    /** @type {string[][]} */
    const loaded = [];
    patchWithCleanup(TemplateSet, { compiler: null });
    patchWithCleanup(assets, {
        async loadESMBundle(specifiers) {
            loaded.push(specifiers);
            TemplateSet.compiler = compiler;
        },
    });
    patchWithCleanup(session, { await_precompiled_templates: false });
    await precompiledTemplatesService.start(
        { debug: "1" },
        { localization: { code: "en_US", translationsHash: "0123456789abcdef" } },
    );
    expect(loaded).toEqual([["@odoo/owl/compiler"]]);
    expect(TemplateSet.compiler).toBe(compiler);
});

test("a page of another site reads the compiled templates from the server's origin", async () => {
    // a live chat embedded on a customer's site: session.origin is the server
    /** @type {string[]} */
    const requested = [];
    patchWithCleanup(assets, {
        async loadJS(url) {
            requested.push(url);
        },
    });
    patchWithCleanup(session, {
        origin: "https://odoo.example",
        await_precompiled_templates: true,
    });
    const listeners = new Set(templates.bundleListeners);
    templates.bundles.set("im_livechat.assets_embed_test", {
        checksum: "0123",
        params: {},
    });
    after(() => {
        templates.bundles.delete("im_livechat.assets_embed_test");
        for (const listener of templates.bundleListeners) {
            if (!listeners.has(listener)) {
                templates.bundleListeners.delete(listener);
            }
        }
    });
    await precompiledTemplatesService.start(
        { debug: "" },
        { localization: { code: "en_US", translationsHash: "f00d" } },
    );
    expect(requested).toInclude(
        "https://odoo.example/web/assets/owl/0123/en_US/f00d/im_livechat.assets_embed_test.js",
    );
    expect(
        requested.filter(
            (url) => !url.startsWith("https://odoo.example/web/assets/owl/"),
        ),
    ).toEqual([]);
});
