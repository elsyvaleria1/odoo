// Every patch(target, extension) call of the given sources, with the target
// named by the module that exports it and the keys the extension defines.
// argv[2]: a JSON file of [{addon, module, path}], module being "@addon/path" without ".js";
// stdout: {patches: [{addon, path, line, target, keys}], errors: [...]}.
// A target or an extension it cannot name statically is reported with
// target or keys null: the caller decides what that means.
import { parse } from "acorn";
import { readFileSync } from "node:fs";
import { posix } from "node:path";
import process from "node:process";

const PATCH_MODULE = "@web/core/utils/patch";

function resolveSpecifier(fromModule, spec) {
    if (!spec.startsWith(".")) {
        return spec.replace(/\.js$/, "");
    }
    return posix
        .normalize(posix.join(posix.dirname(fromModule), spec))
        .replace(/\.js$/, "");
}

function propertyName(prop) {
    if (prop.type !== "Property" && prop.type !== "MethodDefinition") {
        return null;
    }
    if (prop.computed) {
        return null;
    }
    if (prop.key.type === "Identifier") {
        return prop.key.name;
    }
    if (prop.key.type === "Literal") {
        return String(prop.key.value);
    }
    return null;
}

function objectKeys(node) {
    const keys = [];
    for (const prop of node.properties) {
        const name = propertyName(prop);
        if (name === null) {
            // a spread or a computed key: what it adds is unknown
            return null;
        }
        keys.push(name);
    }
    return [...new Set(keys)].sort();
}

function scan({ addon, module, path }) {
    const source = readFileSync(path, "utf8");
    if (!source.includes("patch(") && !source.includes("export")) {
        return { found: [], exported: {} };
    }
    const ast = parse(source, {
        ecmaVersion: "latest",
        sourceType: "module",
        allowHashBang: true,
        locations: true,
    });
    const imports = new Map();
    const localObjects = new Map();
    const localNames = new Set();
    // a function whose body is an object literal, or returns one
    const localFactories = new Map();
    // const reg = registry.category("c"): its entries are named by "c"
    const localRegistries = new Map();
    const exportedNames = new Set();
    const destructured = new Map();
    const returnedObject = (fn) => {
        if (fn.body.type === "ObjectExpression") {
            return fn.body;
        }
        const statements = fn.body.type === "BlockStatement" ? fn.body.body : [];
        const returned = statements.filter((st) => st.type === "ReturnStatement");
        return returned.length === 1 &&
            returned[0].argument?.type === "ObjectExpression"
            ? returned[0].argument
            : null;
    };
    for (const node of ast.body) {
        if (node.type === "ImportDeclaration") {
            const from = resolveSpecifier(module, node.source.value);
            for (const spec of node.specifiers) {
                const imported =
                    spec.type === "ImportSpecifier"
                        ? (spec.imported.name ?? spec.imported.value)
                        : spec.type === "ImportDefaultSpecifier"
                          ? "default"
                          : "*";
                imports.set(spec.local.name, { from, imported });
            }
            continue;
        }
        const declaration =
            node.type === "ExportNamedDeclaration" ? node.declaration : node;
        if (node.type === "ExportNamedDeclaration" && !node.source) {
            for (const spec of node.specifiers) {
                exportedNames.add(spec.local.name);
            }
        }
        if (!declaration) {
            continue;
        }
        const exported = node.type === "ExportNamedDeclaration";
        if (declaration.type === "VariableDeclaration") {
            for (const decl of declaration.declarations) {
                // const { a, b: c } = X: a is X.a, c is X.b
                if (decl.id.type === "ObjectPattern" && decl.init) {
                    for (const prop of decl.id.properties) {
                        const key = propertyName(prop);
                        if (key && prop.value.type === "Identifier") {
                            destructured.set(prop.value.name, {
                                source: decl.init,
                                key,
                            });
                        }
                    }
                    continue;
                }
                if (decl.id.type !== "Identifier") {
                    continue;
                }
                localNames.add(decl.id.name);
                if (exported) {
                    exportedNames.add(decl.id.name);
                }
                if (
                    decl.init?.type === "CallExpression" &&
                    decl.init.callee.type === "MemberExpression" &&
                    decl.init.callee.property.name === "category" &&
                    decl.init.arguments[0]?.type === "Literal" &&
                    decl.init.callee.object.type === "Identifier" &&
                    imports.get(decl.init.callee.object.name)?.from ===
                        "@web/core/registry"
                ) {
                    localRegistries.set(decl.id.name, decl.init.arguments[0].value);
                }
                if (decl.init?.type === "ObjectExpression") {
                    localObjects.set(decl.id.name, decl.init);
                } else if (
                    decl.init?.type === "ArrowFunctionExpression" ||
                    decl.init?.type === "FunctionExpression"
                ) {
                    const object = returnedObject(decl.init);
                    if (object) {
                        localFactories.set(decl.id.name, object);
                    }
                }
            }
        } else if (
            (declaration.type === "ClassDeclaration" ||
                declaration.type === "FunctionDeclaration") &&
            declaration.id
        ) {
            localNames.add(declaration.id.name);
            if (exported) {
                exportedNames.add(declaration.id.name);
            }
            if (declaration.type === "FunctionDeclaration") {
                const object = returnedObject(declaration);
                if (object) {
                    localFactories.set(declaration.id.name, object);
                }
            }
        }
    }
    const patchNames = new Set(
        [...imports]
            .filter(([, i]) => i.from === PATCH_MODULE && i.imported === "patch")
            .map(([local]) => local),
    );
    // what another module's patch may import as its extension
    const exported = { registries: {} };
    for (const name of exportedNames) {
        if (localRegistries.has(name)) {
            exported.registries[name] = localRegistries.get(name);
        }
        const object = localObjects.get(name) ?? localFactories.get(name);
        if (object) {
            exported[name] = objectKeys(object);
        }
    }
    if (!patchNames.size) {
        return { found: [], exported };
    }
    // a member of a namespace import is the export of that name, so
    // `ns.components.X` and `import { components }` name one target
    const member = (owner, key) =>
        owner.endsWith(":*") ? `${owner.slice(0, -1)}${key}` : `${owner}.${key}`;
    const nameOf = (node) => {
        if (node.type === "Identifier" && destructured.has(node.name)) {
            const { source, key } = destructured.get(node.name);
            const owner = nameOf(source);
            return owner && member(owner, key);
        }
        if (node.type === "Identifier") {
            const imported = imports.get(node.name);
            if (imported) {
                return `${imported.from}:${imported.imported}`;
            }
            return localNames.has(node.name) ? `${module}:${node.name}` : null;
        }
        if (
            node.type === "MemberExpression" &&
            !node.computed &&
            node.property.type === "Identifier"
        ) {
            const owner = nameOf(node.object);
            return owner && member(owner, node.property.name);
        }
        // registry.category("c").get("k"): the entry, named by its keys
        const literal = (arg) =>
            arg?.type === "Literal" && typeof arg.value === "string";
        if (
            node.type === "CallExpression" &&
            node.callee.type === "MemberExpression" &&
            node.callee.property.name === "get" &&
            literal(node.arguments[0]) &&
            node.callee.object.type === "Identifier" &&
            localRegistries.has(node.callee.object.name)
        ) {
            return `registry:${localRegistries.get(node.callee.object.name)}/${node.arguments[0].value}`;
        }
        if (
            node.type === "CallExpression" &&
            node.callee.type === "MemberExpression" &&
            node.callee.property.name === "get" &&
            literal(node.arguments[0]) &&
            node.callee.object.type === "Identifier" &&
            imports.has(node.callee.object.name)
        ) {
            return {
                ref: imports.get(node.callee.object.name),
                entry: node.arguments[0].value,
            };
        }
        if (
            node.type === "CallExpression" &&
            node.callee.type === "MemberExpression" &&
            node.callee.property.name === "get" &&
            literal(node.arguments[0]) &&
            node.callee.object.type === "CallExpression" &&
            node.callee.object.callee.type === "MemberExpression" &&
            node.callee.object.callee.property.name === "category" &&
            literal(node.callee.object.arguments[0]) &&
            node.callee.object.callee.object.type === "Identifier" &&
            imports.get(node.callee.object.callee.object.name)?.from ===
                "@web/core/registry"
        ) {
            return `registry:${node.callee.object.arguments[0].value}/${node.arguments[0].value}`;
        }
        return null;
    };
    const keysOf = (node) => {
        if (node.type === "ObjectExpression") {
            return objectKeys(node);
        }
        if (node.type === "Identifier" && localObjects.has(node.name)) {
            return objectKeys(localObjects.get(node.name));
        }
        if (
            node.type === "CallExpression" &&
            node.callee.type === "Identifier" &&
            localFactories.has(node.callee.name)
        ) {
            return objectKeys(localFactories.get(node.callee.name));
        }
        // imported: resolved once every module's exports are known
        const ref =
            node.type === "Identifier"
                ? imports.get(node.name)
                : node.type === "CallExpression" && node.callee.type === "Identifier"
                  ? imports.get(node.callee.name)
                  : null;
        return ref ? { ref } : null;
    };
    const found = [];
    const visit = (node) => {
        if (!node || typeof node.type !== "string") {
            return;
        }
        if (
            node.type === "CallExpression" &&
            node.callee.type === "Identifier" &&
            patchNames.has(node.callee.name) &&
            node.arguments.length >= 2
        ) {
            found.push({
                addon,
                path,
                line: node.loc.start.line,
                target: nameOf(node.arguments[0]),
                keys: keysOf(node.arguments[1]),
            });
        }
        for (const key of Object.keys(node)) {
            const child = node[key];
            if (Array.isArray(child)) {
                child.forEach(visit);
            } else if (child && typeof child === "object" && key !== "loc") {
                visit(child);
            }
        }
    };
    visit(ast);
    return { found, exported };
}

const files = JSON.parse(readFileSync(process.argv[2], "utf8"));
const patches = [];
const errors = [];
const exportsByModule = new Map();
for (const file of files) {
    try {
        const { found, exported } = scan(file);
        patches.push(...found);
        exportsByModule.set(file.module, exported);
    } catch (error) {
        errors.push({ path: file.path, error: String(error.message ?? error) });
    }
}
for (const patch of patches) {
    if (patch.target && patch.target.ref) {
        const { from, imported } = patch.target.ref;
        const category = exportsByModule.get(from)?.registries?.[imported];
        patch.target = category ? `registry:${category}/${patch.target.entry}` : null;
    }
    if (patch.keys && patch.keys.ref) {
        const { from, imported } = patch.keys.ref;
        patch.keys = exportsByModule.get(from)?.[imported] ?? null;
    }
}
process.stdout.write(JSON.stringify({ patches, errors }));
