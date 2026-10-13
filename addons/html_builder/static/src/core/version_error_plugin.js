/** @odoo-module native */

import { Plugin } from "@html_editor/plugin";
import { _t } from "@web/core/translation";

export class VersionErrorPlugin extends Plugin {
    static id = "versionError";
    static shared = ["checkNotifyOutdatedSnippet"];
    static dependencies = [];

    resources = {};

    /**
     * @param {HTMLElement} el
     * @returns {boolean}
     */
    isSnippetUpToDate(el) {
        const snippetEl = el?.closest?.("[data-snippet]");
        if (!snippetEl) {
            return true;
        }
        const snippetKey = snippetEl.dataset.snippet;
        const snippet = this.config.snippetModel.getOriginalSnippet(snippetKey);
        if (!snippet) {
            return true;
        }
        const {
            vcss: originalVcss,
            vxml: originalVxml,
            vjs: originalVjs,
        } = snippet.content.dataset;
        const { vcss: elVcss, vxml: elVxml, vjs: elVjs } = snippetEl.dataset;
        return (
            originalVcss === elVcss && originalVxml === elVxml && originalVjs === elVjs
        );
    }

    /**
     * @param {HTMLElement} editingElement
     * @return {Boolean}
     */
    checkNotifyOutdatedSnippet(editingElement) {
        if (!this.isSnippetUpToDate(editingElement)) {
            this.closeExistingNotification?.();
            this.closeExistingNotification = this.services.notification.add(
                _t(
                    "It might have caused problem during the editing. Please drag the new version from the snippet panel to update it.",
                ),
                {
                    type: "warning",
                    title: _t("This snippet is outdated"),
                    sticky: true,
                },
            );
            return true;
        }
        return false;
    }
}
