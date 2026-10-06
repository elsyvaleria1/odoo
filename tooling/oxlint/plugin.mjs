// Rules oxlint does not ship natively, loaded through its `jsPlugins`.
//
// `no-restricted-syntax` takes ESLint's option shape unchanged — a bare
// selector string, or `{ selector, message }` — so a selector moves between
// the two linters verbatim. oxlint dispatches esquery selectors to plugin
// visitors itself; this rule only maps each one to its report.

const noRestrictedSyntax = {
    meta: {
        type: "suggestion",
        schema: false,
    },
    create(context) {
        const visitors = {};
        for (const option of context.options) {
            const { selector, message } =
                typeof option === "string"
                    ? { selector: option, message: `Using '${option}' is not allowed.` }
                    : option;
            const previous = visitors[selector];
            visitors[selector] = (node) => {
                previous?.(node);
                context.report({ node, message });
            };
        }
        return visitors;
    },
};

export default {
    meta: { name: "odoo" },
    rules: {
        "no-restricted-syntax": noRestrictedSyntax,
    },
};
