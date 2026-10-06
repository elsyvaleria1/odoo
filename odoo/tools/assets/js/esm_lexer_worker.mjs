import { init, parse } from "es-module-lexer";
import { createInterface } from "node:readline";

await init;

// the parent reads this before its first request: a worker that dies before
// it (es-module-lexer not installed) could not start, it did not fail a request
process.stdout.write(JSON.stringify({ ready: true }) + "\n");

let acorn = null;

// A reference in a position a module runs while it is evaluated: at top level,
// in a class heritage, a computed key, a static field or block. Function and
// method bodies and instance fields run later, when a bridge is long filled.
function isReference(parent, key) {
    if (!parent) {
        return true;
    }
    if (parent.type === "MemberExpression" && key === "property" && !parent.computed) {
        return false;
    }
    if (
        (parent.type === "Property" || parent.type === "PropertyDefinition") &&
        key === "key" &&
        !parent.computed
    ) {
        return false;
    }
    return !["LabeledStatement", "BreakStatement", "ContinueStatement"].includes(
        parent.type,
    );
}

function evaluationUses(src) {
    const ast = acorn.parse(src, {
        ecmaVersion: "latest",
        sourceType: "module",
        locations: true,
    });
    const bindings = new Map();
    for (const node of ast.body) {
        if (node.type === "ImportDeclaration") {
            for (const spec of node.specifiers) {
                bindings.set(spec.local.name, node.source.value);
            }
        }
    }
    const uses = [];
    const seen = new Set();
    const visit = (node, parent = null, key = null) => {
        if (!node || typeof node.type !== "string") {
            return;
        }
        switch (node.type) {
            case "ImportDeclaration":
            case "ExportSpecifier":
            case "FunctionDeclaration":
            case "FunctionExpression":
            case "ArrowFunctionExpression":
                return;
            case "MethodDefinition":
                if (node.computed) {
                    visit(node.key, node, "key");
                }
                return;
            case "PropertyDefinition":
                if (node.computed) {
                    visit(node.key, node, "key");
                }
                if (node.static) {
                    visit(node.value, node, "value");
                }
                return;
            case "Identifier": {
                const source = bindings.get(node.name);
                const mark = `${node.name}:${node.loc.start.line}`;
                if (
                    source !== undefined &&
                    isReference(parent, key) &&
                    !seen.has(mark)
                ) {
                    seen.add(mark);
                    uses.push({
                        n: source,
                        name: node.name,
                        line: node.loc.start.line,
                    });
                }
                return;
            }
        }
        for (const [childKey, value] of Object.entries(node)) {
            if (childKey === "loc") {
                continue;
            }
            if (Array.isArray(value)) {
                for (const child of value) {
                    visit(child, node, childKey);
                }
            } else if (value && typeof value.type === "string") {
                visit(value, node, childKey);
            }
        }
    };
    for (const node of ast.body) {
        visit(node);
    }
    return uses;
}

const rl = createInterface({ input: process.stdin, terminal: false });
rl.on("line", async (line) => {
    let req;
    try {
        req = JSON.parse(line);
    } catch {
        return;
    }
    const out = { id: req.id };
    if (req.op === "evaluation_uses") {
        try {
            acorn ??= await import("acorn");
            out.uses = evaluationUses(String(req.src ?? ""));
            out.ok = true;
        } catch (err) {
            out.ok = false;
            out.error = String((err && err.message) || err);
        }
        process.stdout.write(JSON.stringify(out) + "\n");
        return;
    }
    try {
        const src = String(req.src ?? "");
        const [imports, exports] = parse(src);
        const names = [];
        let hasDefault = false;
        for (const e of exports) {
            if (e.n === "default") {
                hasDefault = true;
            } else if (e.n) {
                names.push(e.n);
            }
        }
        const starFrom = [];
        const reexportFrom = [];
        const importRecords = [];
        for (const i of imports) {
            if (i.d >= 0 || !i.n) {
                continue;
            }
            const stmt = src.slice(i.ss, i.se);
            if (/^\s*export\b/.test(stmt)) {
                if (/^\s*export\s*\*\s*from\b/.test(stmt)) {
                    starFrom.push(i.n);
                } else {
                    reexportFrom.push(i.n);
                }
                continue;
            }
            importRecords.push({ n: i.n });
        }
        out.ok = true;
        out.names = names;
        out.hasDefault = hasDefault;
        out.starFrom = starFrom;
        out.reexportFrom = reexportFrom;
        out.imports = importRecords;
        // Dependency checks also need literal dynamic imports, without
        // confusing source-like text in comments or strings with code.
        out.specifiers = [...new Set(imports.map((i) => i.n).filter(Boolean))];
    } catch (err) {
        out.ok = false;
        out.error = String((err && err.message) || err);
    }
    process.stdout.write(JSON.stringify(out) + "\n");
});
