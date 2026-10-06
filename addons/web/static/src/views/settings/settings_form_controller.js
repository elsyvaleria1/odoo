// @ts-check
/** @odoo-module native */

import { proxy } from "@odoo/owl";
import { useActionCallbackRecorders } from "@web/core/action_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewButtonContext } from "@web/core/view_button_context_hooks";
import { formView } from "@web/views/form/form_view";
import { provideSettingsSearchContext } from "@web/views/settings/settings_search_context";
import { recordResParams } from "@web/views/view_button/view_button";

import { SettingsConfirmationDialog } from "./settings_confirmation_dialog.js";
import { SettingsFormRenderer } from "./settings_form_renderer.js";

const log = makeLogger("web.view.settings");

export class SettingsFormController extends formView.Controller {
    static template = "web.SettingsFormView";
    static components = {
        ...formView.Controller.components,
        Renderer: SettingsFormRenderer,
    };

    setup() {
        super.setup();
        this.actionCallbacks = useActionCallbackRecorders();
        this.viewButtonContext = useViewButtonContext();
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
        this.state = proxy({ displayNoContent: false });
        this.searchState = proxy({ value: "" });
        this.canCreate = false;
        provideSettingsSearchContext({ searchState: this.searchState });
        useLayoutEffect(
            () => {
                if (this.searchState.value) {
                    this.state.displayNoContent = !this.rootRef.el.querySelector(
                        ".app_settings_block:not(.d-none) .o_settings_container:not(.d-none)",
                    );
                } else {
                    this.state.displayNoContent = false;
                }
            },
            () => [this.searchState.value],
        );
        useLayoutEffect(
            () => {
                if (this.actionCallbacks.__getLocalState__) {
                    this.actionCallbacks.__getLocalState__.remove(this);
                }
            },
            () => [],
        );

        this.initialApp =
            "module" in this.props.context ? this.props.context.module : "";
    }

    get modelParams() {
        const headerFields = Object.values(this.archInfo.fieldNodes)
            .filter((fieldNode) => fieldNode.options.isHeaderField)
            .map((fieldNode) => fieldNode.name);
        return {
            ...super.modelParams,
            headerFields,
            onChangeHeaderFields: () => this._confirmSave(),
        };
    }

    /** @override */
    /** @param {Record<string, any>} clickParams */
    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "cancel") {
            return true;
        }
        if (
            (await this.model.root.isDirty()) &&
            clickParams.name !== "execute" &&
            !clickParams.noSaveDialog
        ) {
            return this._confirmSave();
        } else {
            return this.saveCoordinator.requestSave({ errorMode: "rethrow" });
        }
    }

    displayName() {
        return _t("Settings");
    }

    /** @param {{ forceLeave?: boolean }} [options] */
    async beforeLeave({ forceLeave } = {}) {
        if (forceLeave) {
            return;
        }
        const dirty = await this.model.root.isDirty();
        if (dirty) {
            return this._confirmSave();
        }
    }

    /** @param {any} [_ev] */
    async beforeUnload(_ev) {}

    /** @returns {Promise<any> | undefined} */
    beforeVisibilityChange() {
        return undefined;
    }

    /**
     * @param {any} [_params]
     * @returns {Promise<any>}
     */
    async save(_params) {
        await this.viewButtonContext.onClickViewButton(
            this.viewButtonParams({ name: "execute", type: "object" }),
        );
    }

    async discard() {
        log.logic("discard:cancelButton");
        await this.viewButtonContext.onClickViewButton(
            this.viewButtonParams({
                name: "cancel",
                type: "object",
                special: "cancel",
            }),
        );
        log.logic("discard:settled");
    }

    /** @param {Record<string, any>} clickParams */
    viewButtonParams(clickParams) {
        return { clickParams, getResParams: () => recordResParams(this.model.root) };
    }

    async _confirmSave() {
        let _continue = true;
        await /** @type {Promise<void>} */ (
            new Promise((resolve) => {
                /** @type {any} */ (this.dialogService).add(
                    SettingsConfirmationDialog,
                    {
                        body: _t("Would you like to save your changes?"),
                        confirm: async () => {
                            _continue = false;
                            try {
                                await this.save();
                            } finally {
                                resolve();
                            }
                        },
                        cancel: async () => {
                            _continue = false;
                            try {
                                await this.saveCoordinator.requestDiscard();
                                await this.saveCoordinator.requestSave({
                                    errorMode: "rethrow",
                                });
                                _continue = true;
                            } finally {
                                resolve();
                            }
                        },
                        stayHere: () => {
                            _continue = false;
                            resolve();
                        },
                        dismiss: () => {
                            _continue = false;
                            resolve();
                        },
                    },
                );
            })
        );
        return _continue;
    }
}
