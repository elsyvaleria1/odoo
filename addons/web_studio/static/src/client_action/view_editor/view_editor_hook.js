/** @odoo-module native */
import { onWillDestroy, onWillStart, proxy } from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { useIsDestroyed, useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import {
    useEditorBreadcrumbs,
    useEditorMenuItem,
} from "@web_studio/client_action/editor/edition_flow";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import { viewTypeToString } from "@web_studio/studio_service";

import { ViewEditorModel } from "./view_editor_model.js";
import { provideViewEditorModel } from "./view_editor_model_context.js";
import { ViewEditorSnackbar } from "./view_editor_snackbar.js";

export function useViewEditorModel(viewRef, { initialState }) {
    const env = {
        editionFlow: useStudioEditorContext().editionFlow,
        services: useAppContext().services,
        config: useViewConfig(),
    };

    const services = Object.fromEntries(
        ["orm", "ui", "notification"].map((sName) => [sName, useService(sName)]),
    );
    services.studio = { ...env.services.studio };
    services.dialog = { add: useOwnedDialogs() };

    const editionFlow = proxy(env.editionFlow);
    useEditorBreadcrumbs({ name: viewTypeToString(services.studio.editedViewType) });

    const viewEditorModel = new ViewEditorModel({
        env,
        services,
        editionFlow,
        viewRef,
        initialState,
    });
    provideViewEditorModel(viewEditorModel);

    const { _snackBar, _operations } = viewEditorModel;
    useEditorMenuItem({
        component: ViewEditorSnackbar,
        props: { operations: _operations, saveIndicator: _snackBar },
    });

    const isDestroyed = useIsDestroyed();
    onWillStart(
        async () =>
            new Promise((resolve, reject) => {
                viewEditorModel
                    .load()
                    .then(resolve)
                    .catch((error) => {
                        if (!isDestroyed()) {
                            reject(error);
                        }
                    });
            }),
    );

    onWillDestroy(() => {
        viewEditorModel.isInEdition = false;
    });
    return proxy(viewEditorModel);
}

export function useSnackbarWrapper(fn) {
    const env = {
        viewEditorModel: useCurrentViewEditorModel(),
    };
    return env.viewEditorModel._decorateFunction(fn);
}
