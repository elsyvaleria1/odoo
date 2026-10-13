/** @odoo-module native */
import { _t } from "@web/core/translation";
import { isVisible } from "@web/core/utils/dom/ui";
import { Macro } from "@web/core/utils/macro";
import { AlertDialog } from "@web/ui/dialog";

class KnowledgeMacroError extends Error {}

export class AbstractMacro extends Macro {
    /**
     * @param {Object} options
     * @param {HTMLElement} options.targetXmlDoc
     * @param {Array[Object]} options.breadcrumbs
     * @param {Any} options.data
     * @param {Object} options.services
     */
    constructor({ targetXmlDoc, breadcrumbs, data, services }) {
        super({
            name: "restore_record",
            steps: [],
        });
        this.targetXmlDoc = targetXmlDoc;
        this.targetBreadcrumbs = breadcrumbs;
        this.data = data;
        this.services = services;
        this.steps = this.buildSteps();
    }

    blockUI() {
        if (!this.services.ui.isBlocked) {
            this.services.ui.block();
        }
    }

    buildSteps() {
        const steps = this.getSteps();
        if (!steps.length) {
            return [];
        }
        return [
            {
                action: () => this.blockUI(),
            },
            {
                action: async () => {
                    try {
                        await this.services.action.restore(
                            this.targetBreadcrumbs.at(-1).jsId,
                        );
                    } catch {
                        throw new KnowledgeMacroError(
                            _t(
                                "The record that this macro is targeting could not be found.",
                            ),
                        );
                    }
                },
            },
            {
                trigger: () => {
                    const controllerBreadcrumbs =
                        this.services.action.currentController.config.breadcrumbs;
                    if (
                        this.targetBreadcrumbs.at(-1).jsId ===
                        controllerBreadcrumbs.at(-1)?.jsId
                    ) {
                        return this.getFirstVisibleElement(
                            ".o_breadcrumb .o_last_breadcrumb_item",
                        );
                    }
                    return null;
                },
            },
            ...steps,
        ];
    }

    /**
     * @param {Error} error
     */
    onError(error) {
        this.blockUI();
        if (error instanceof KnowledgeMacroError) {
            this.services.dialog.add(AlertDialog, {
                body: error.message,
                title: _t("Error"),
                confirmLabel: _t("Close"),
            });
        } else {
            console.error(error);
        }
    }

    onTimeout() {
        throw new KnowledgeMacroError(_t("The operation could not be completed."));
    }

    /**
     * @param {String|HTMLElement} selector
     * @param {Function} filter
     * @param {boolean} reverse
     * @returns {HTMLElement}
     */
    getFirstVisibleElement(selector, filter = false, reverse = false) {
        const elementsArray =
            typeof selector === "string"
                ? Array.from(document.querySelectorAll(selector))
                : [selector];
        const sel = filter ? elementsArray.filter(filter) : elementsArray;
        for (let i = 0; i < sel.length; i++) {
            i = reverse ? sel.length - 1 - i : i;
            if (isVisible(sel[i])) {
                return sel[i];
            }
        }
        return null;
    }

    /** @returns {Array[Object]} */
    getSteps() {
        return [];
    }

    unblockUI() {
        if (this.services.ui.isBlocked) {
            this.services.ui.unblock();
        }
    }

    validatePage() {
        const controllerBreadcrumbs =
            this.services.action.currentController.config.breadcrumbs;
        if (this.targetBreadcrumbs.at(-1).jsId !== controllerBreadcrumbs.at(-1)?.jsId) {
            throw new KnowledgeMacroError(
                _t("The record that this macro is targeting could not be found."),
            );
        }
    }
    /** @param {String} targetSelector */
    searchInXmlDocNotebookTab(targetSelector) {
        const searchElement = this.targetXmlDoc.querySelector(targetSelector);
        const page = searchElement ? searchElement.closest("page") : undefined;
        const pageName = page ? page.getAttribute("name") : undefined;
        if (!pageName) {
            return;
        }
        const pageEl = this.getFirstVisibleElement(
            `.o_notebook .nav-link[name=${pageName}]:not(.active)`,
        );
        if (pageEl) {
            pageEl.click();
        }
    }
}
