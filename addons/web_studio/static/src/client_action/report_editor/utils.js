/** @odoo-module native */
const PAPER_TO_CSS = {
    margin_top: "padding-top",
    margin_left: "padding-left",
    margin_right: "padding-right",
    print_page_width: "width",
    print_page_height: "min-height",
};

export function getCssFromPaperFormat(paperFormat, unit = "mm") {
    return Object.entries(paperFormat)
        .map((f) => `${PAPER_TO_CSS[f[0]]}:${f[1]}${unit}`)
        .join(";");
}

export function humanReadableError(error) {
    if (error.data) {
        error = error.data;
    }
    let viewError;
    const context = error.context || {};
    if (context.view) {
        // see @ def _prepare_view_error.
        viewError = {
            viewModel: context.view.model,
            completeName: context.xmlid
                ? `${context.name} (${context.xmlid})`
                : context.name,
            resIds: context.view.ids,
            model: context["view.model"],
            parentIds: context["view.parent"].ids,
        };
    }
    return {
        ...error,
        traceback: error.debug,
        viewError,
    };
}

export function visitNode(el, callback) {
    const iterators = [[el]];
    while (iterators.length) {
        const it = iterators.pop();
        for (const _el of it) {
            const doChildren = callback(_el);
            if (doChildren === false) {
                continue;
            }
            iterators.push(_el.children);
        }
    }
}
