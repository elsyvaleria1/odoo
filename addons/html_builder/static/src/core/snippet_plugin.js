/** @odoo-module native */

import { Plugin } from "@html_editor/plugin";

export class SnippetPlugin extends Plugin {
    static id = "snippetPlugin";

    /** @type {import("plugins").BuilderResources} */
    resources = {
        before_setup_editor_handlers: this.injectMissingSnippetNames.bind(this),
    };

    injectMissingSnippetNames() {
        for (const snippetEl of this.editable.querySelectorAll(
            "[data-snippet]:not([data-name])",
        )) {
            const snippetInfo = this.config.snippetModel.getOriginalSnippet(
                snippetEl.dataset.snippet,
            );
            if (snippetInfo?.title) {
                snippetEl.dataset.name = snippetInfo.title;
            }
        }
    }
}
