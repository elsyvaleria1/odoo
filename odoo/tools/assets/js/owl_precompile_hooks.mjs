import { existsSync, statSync } from "node:fs";
import { pathToFileURL } from "node:url";

let roots = {};

export function initialize(data) {
    roots = data.roots;
}

function locate(base) {
    for (const candidate of [base, `${base}.js`, `${base}/index.js`]) {
        if (existsSync(candidate) && statSync(candidate).isFile()) {
            return pathToFileURL(candidate).href;
        }
    }
    return null;
}

export async function resolve(specifier, context, nextResolve) {
    let url = null;
    if (specifier in roots) {
        url = pathToFileURL(roots[specifier]).href;
    } else if (specifier.startsWith("@") && specifier.includes("/")) {
        const slash = specifier.indexOf("/");
        const root = roots[specifier.slice(0, slash)];
        url = root && locate(`${root}${specifier.slice(slash)}`);
    }
    if (url) {
        return { url, format: "module", shortCircuit: true };
    }
    const resolved = await nextResolve(specifier, context);
    if (!resolved.format && resolved.url.endsWith(".js")) {
        return { ...resolved, format: "module" };
    }
    return resolved;
}
