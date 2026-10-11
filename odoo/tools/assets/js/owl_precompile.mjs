import { parse } from "acorn";
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { text } from "node:stream/consumers";
import xpath from "xpath";

const request = JSON.parse(await text(process.stdin));
const webStatic = request.web_static.replace(/\/$/, "");

const { window } = new JSDOM("<!DOCTYPE html><html><head></head><body></body></html>", {
    url: "http://localhost/",
    pretendToBeVisual: true,
});

window.Document.prototype.createExpression = function createExpression(expression) {
    const parsed = xpath.parse(expression);
    return {
        evaluate(context) {
            const nodes = parsed.select({ node: context });
            if (!Array.isArray(nodes)) {
                throw new window.TypeError("The result is not a node set");
            }
            return {
                snapshotLength: nodes.length,
                snapshotItem: (i) => nodes[i] ?? null,
            };
        },
    };
};
const serializer = new window.XMLSerializer();
const innerHTML = Object.getOwnPropertyDescriptor(
    window.Element.prototype,
    "innerHTML",
);
Object.defineProperty(window.Element.prototype, "innerHTML", {
    ...innerHTML,
    get() {
        if (this.ownerDocument.contentType === "text/html") {
            return innerHTML.get.call(this);
        }
        return Array.from(this.childNodes, (node) =>
            serializer.serializeToString(node),
        ).join("");
    },
});
window.fetch = globalThis.fetch;
window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
});
for (const key of Object.getOwnPropertyNames(window)) {
    if (!(key in globalThis)) {
        globalThis[key] = window[key];
    }
}
globalThis.window = window;
globalThis.document = window.document;
globalThis.odoo = { debug: "", __session_info__: {} };

register("./owl_precompile_hooks.mjs", import.meta.url, {
    data: {
        roots: {
            "@odoo/owl": `${webStatic}/lib/owl/owl.es.js`,
            "@web": `${webStatic}/src`,
        },
    },
});

const { TemplateSet } = await import("@odoo/owl");
const { TemplateRegistry, inlineTemplateKey } = await import("@web/core/templates");
const { loadTranslationTerms, translatedTerms, translationLoaded } =
    await import("@web/core/translation");
const { makeAppConfig } = await import("@web/env");

loadTranslationTerms(request.modules);
translatedTerms[translationLoaded] = true;

function replay(registrations, registerTemplate, registerTemplateExtension) {
    new Function(
        "registerTemplate",
        "registerTemplateExtension",
        "checkPrimaryTemplateParents",
        "registerTemplateBundle",
        registrations,
    )(
        registerTemplate,
        registerTemplateExtension,
        () => {},
        (_bundle, _checksum, _params, register) => register?.(),
    );
}

/**
 * The registry a page holds once this bundle registered its templates, after
 * what the page registered first, and the names the bundle registered or
 * extended; with no page, every name counts.
 *
 * @param {string | null} pageRegistrations
 */
function registryAfter(pageRegistrations) {
    const registry = new TemplateRegistry();
    if (pageRegistrations !== null) {
        replay(
            pageRegistrations,
            registry.registerTemplate.bind(registry),
            registry.registerTemplateExtension.bind(registry),
        );
    }
    const touched = new Set();
    replay(
        request.registrations,
        (name, url, templateString) => {
            touched.add(name);
            return registry.registerTemplate(name, url, templateString);
        },
        (inheritFrom, url, templateString) => {
            touched.add(inheritFrom);
            return registry.registerTemplateExtension(inheritFrom, url, templateString);
        },
    );
    return { registry, touched: pageRegistrations === null ? null : touched };
}

/**
 * The inline templates of a module, as `xml` receives them: a tagged
 * template without substitutions hands it the raw text.
 *
 * @param {string} url
 * @param {string} content
 * @returns {string[]}
 */
function inlineTemplates(url, content) {
    let ast;
    try {
        ast = parse(content, { ecmaVersion: "latest", sourceType: "module" });
    } catch (error) {
        inlineFailures[url] = `unparsable: ${error.message}`;
        return [];
    }
    const found = [];
    const stack = [ast];
    while (stack.length) {
        const node = stack.pop();
        if (
            node.type === "TaggedTemplateExpression" &&
            !node.quasi.expressions.length &&
            (node.tag.type === "Identifier"
                ? node.tag.name === "xml"
                : node.tag.type === "MemberExpression" &&
                  !node.tag.computed &&
                  node.tag.property.name === "xml")
        ) {
            found.push(node.quasi.quasis[0].value.raw);
        }
        for (const value of Object.values(node)) {
            if (Array.isArray(value)) {
                for (const child of value) {
                    if (child && typeof child.type === "string") {
                        stack.push(child);
                    }
                }
            } else if (value && typeof value.type === "string") {
                stack.push(value);
            }
        }
    }
    return found;
}

/** @param {unknown} error */
function describe(error) {
    return String(
        (process.env.OWL_PRECOMPILE_STACK && error?.stack) || error?.message || error,
    ).slice(0, 2000);
}

/** @param {Function} fn */
function asFunction(fn) {
    const source = fn.toString();
    const code = source.slice(source.indexOf("{") + 1, source.lastIndexOf("}"));
    return `function (app, bdom, helpers) {${code}}`;
}

const dev = Boolean(request.dev);
const compiler = new TemplateSet(makeAppConfig(undefined, { dev }));
const entrySets = [];
const failures = {};
const inlineFailures = {};
const started = performance.now();
const pages = request.page_registrations?.length ? request.page_registrations : [null];
for (const [index, page] of pages.entries()) {
    let registry, touched;
    try {
        ({ registry, touched } = registryAfter(page));
    } catch (error) {
        failures[`page ${index}`] = describe(error);
        continue;
    }
    const entries = [];
    for (const name of Object.keys(registry.templates)) {
        try {
            const chain = registry.inheritanceChain(name);
            if (touched && !chain.some((link) => touched.has(link))) {
                continue;
            }
            const fn = compiler._compileTemplate(name, registry.getTemplate(name));
            const signature = registry.resolutionSignature(chain);
            entries.push(
                `${JSON.stringify(name)}: [${JSON.stringify(signature)}, ${JSON.stringify(chain)}, ${asFunction(fn)}],`,
            );
        } catch (error) {
            failures[name] = describe(error);
        }
    }
    entrySets.push(entries);
}
const owlPath = `${webStatic}/lib/owl/owl.es.js`;
const sources = [
    { url: "/web/static/lib/owl/owl.es.js", content: readFileSync(owlPath, "utf-8") },
    ...(request.sources || []),
];
const inlineEntries = new Map();
for (const { url, content } of sources) {
    for (const template of inlineTemplates(url, content)) {
        const key = inlineTemplateKey(template);
        if (inlineEntries.has(key)) {
            continue;
        }
        try {
            const fn = compiler._compileTemplate(`${url}:${key}`, template);
            inlineEntries.set(key, `${JSON.stringify(key)}: ${asFunction(fn)},`);
        } catch (error) {
            inlineFailures[`${url}:${key}`] = describe(error);
        }
    }
}
const registerCompiled =
    'odoo.loader.modules.get("@web/core/templates").registerCompiledTemplates({';
const [first = [], ...others] = entrySets;
const script = [
    ...others.flatMap((entries) => [
        registerCompiled,
        ...entries,
        `}, {}, { dev: ${dev} });`,
    ]),
    registerCompiled,
    ...first,
    "}, {",
    ...inlineEntries.values(),
    `}, { dev: ${dev} });`,
    "",
].join("\n");
process.stdout.write(
    JSON.stringify({
        script,
        compiled: entrySets.reduce((count, entries) => count + entries.length, 0),
        inline: inlineEntries.size,
        failures: { ...failures, ...inlineFailures },
        elapsed_ms: Math.round(performance.now() - started),
    }),
);
