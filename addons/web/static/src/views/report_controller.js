// @ts-check
/** @odoo-module native */

import { Component, proxy, t, toRaw, useProps } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useModelWithSampleData } from "@web/model/model";
import { standardViewProps } from "@web/views/standard_view_props";
import { useViewChassis, ViewLayout } from "@web/views/view_components";
import { computeModelOptions } from "@web/views/view_utils";

export class ReportController extends Component {
    static components = { ViewLayout };
    static props = {
        ...standardViewProps,
        Model: t.function(),
        modelParams: t.object(),
        Renderer: t.function(),
        buttonTemplate: t.string(),
    };
    props = useProps(this.constructor.props);

    /** @type {any} */
    model;
    /** @type {ReturnType<typeof useViewChassis>} */
    chassis;
    /** @type {ReturnType<typeof useSetupAction>} */
    actionState;

    setup() {
        this.viewConfig = useViewConfig();
        this.inDialog = useDialogContext().inDialog;
        this.model = proxy(
            useModelWithSampleData(
                this.props.Model,
                toRaw(this.props.modelParams),
                this.modelOptions,
            ),
        );
        this.chassis = useViewChassis(this, this.chassisHooks);
        this.actionState = useSetupAction({
            rootRef: this.chassis.rootRef,
            getLocalState: () => this.getLocalState(),
            getContext: () => this.getContext(),
        });
    }

    /** @returns {Record<string, () => any>} */
    get chassisHooks() {
        return {};
    }

    /** @returns {Object} */
    get modelOptions() {
        return /** @type {any} */ (
            computeModelOptions(this.viewConfig, this.inDialog, this.props.display)
        );
    }

    /** @returns {Object} */
    getLocalState() {
        return { metaData: this.model.metaData };
    }

    /** @returns {Object} */
    getContext() {
        return {};
    }
}
