/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { DomainSelectorDialog } from "@web/components/domain_selector_dialog";
import { useDebugMode } from "@web/core/debug/debug_context";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs";

import { makeGeoLogger } from "../../geo_debug.js";
import { FeaturesList } from "./features_list.js";

const debugLog = makeGeoLogger("LayersPanel");

const LAYER_ACTIONS = {
    DOMAIN_CHANGED: "onDomainChanged",
    VISIBLE_CHANGED: "onVisibleChanged",
    LAYER_CHANGED: "onLayerChanged",
    SEQUENCE_CHANGED: "onSequenceChanged",
};

/**
 * @extends Component
 */
export class LayersPanel extends Component {
    static template = "geoengine.LayersPanel";
    static props = {
        model: t.object(),
        archInfo: t.object().optional({}),
        onLayerVisibility: t.function().optional(() => () => {}),
        onLayerOrder: t.function().optional(() => () => {}),
        onLayersChanged: t.function().optional(() => () => {}),
        onRasterChanged: t.function().optional(() => () => {}),
        onZoomToRecord: t.function().optional(() => () => {}),
        onZoomToRecords: t.function().optional(() => () => {}),
    };
    static components = { CheckBox, FeaturesList };
    props = useProps(this.constructor.props);

    get geoLayers() {
        return this.props.model.layers;
    }

    get numberOfLayers() {
        return this.geoLayers.vectors.length + this.geoLayers.rasters.length;
    }

    setup() {
        this.debug = useDebugMode();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.view = useService("view");
        this.notification = useService("notification");
        this.state = proxy({ isFolded: false });
        this.addDialog = useOwnedDialogs();

        onWillStart(async () => {
            await this.loadIsAdmin();
            this._displayValidationMessages(this.props.model.getLayerValidation());
        });

        let dataRowId = "";
        this.rootRef = elementRef();
        useSortable({
            ref: this.rootRef,
            elements: ".item",
            handle: ".fa-sort",
            onDragStart: (params) => {
                const { element } = params;
                dataRowId = element.dataset.id;
                this.sortStart(params);
            },
            onDragEnd: (params) => this.sortStop(params),
            onDrop: (params) => this.sort(dataRowId, params),
        });
    }

    /**
     * @param {Object} vector
     * @returns {string}
     */
    layerProblem(vector) {
        const status = this.props.model.getLayerStatus(vector.resId);
        return status?.error || status?.warning || "";
    }

    /**
     * @returns {Object}
     */
    get featuresList() {
        const archInfo = this.props.archInfo;
        return {
            enabled: Boolean(archInfo.featuresList),
            displayField: archInfo.featuresListField || "display_name",
            groupByField: archInfo.featuresListGroupBy || null,
        };
    }

    /**
     * @param {Object} params
     */
    sortStart({ element }) {
        element.classList.add("shadow");
    }

    /**
     * @param {Object} params
     */
    sortStop({ element }) {
        element.classList.remove("shadow");
    }

    /**
     * @returns {Promise<void>}
     */
    async loadIsAdmin() {
        this.isGeoengineAdmin = await user.hasGroup("geoengine.group_geoengine_admin");
    }

    /**
     * @param {Object} validation
     */
    _displayValidationMessages(validation) {
        if (!validation) {
            return;
        }

        if (validation.errors && validation.errors.length > 0) {
            const errorMessages = validation.errors.map((err) => `• ${err}`).join("\n");
            this.notification.add(
                _t(
                    "Map Configuration Error\n\n%s\n\nThe map may not function correctly. Please fix these issues in Settings → Technical → User Interface → Views.",
                    errorMessages,
                ),
                {
                    type: "danger",
                    sticky: true,
                    className: "o_geoengine_config_error",
                },
            );
        }

        if (validation.warnings && validation.warnings.length > 0) {
            const warningMessages = validation.warnings
                .map((warn) => `• ${warn}`)
                .join("\n");
            this.notification.add(
                _t(
                    "Map Configuration Warning\n\n%s\n\nThe map will work but some features may be suboptimal.",
                    warningMessages,
                ),
                {
                    type: "warning",
                    className: "o_geoengine_config_warning",
                },
            );
        }

        if (validation.info && validation.info.length > 0) {
            const infoMessages = validation.info.map((info) => `• ${info}`).join("\n");
            this.notification.add(_t("Map Configuration Info\n\n%s", infoMessages), {
                type: "info",
                className: "o_geoengine_config_info",
            });
        }
    }

    async sort(dataRowId, { previous }) {
        const refId = previous ? previous.dataset.id : null;
        this.resequence(dataRowId, refId);
        const ordered = this.geoLayers.vectors;
        if (this.isGeoengineAdmin) {
            await this._persistSequences(ordered);
        }
        for (const [index, layer] of ordered.entries()) {
            await this.onVectorChange(layer, LAYER_ACTIONS.SEQUENCE_CHANGED, index + 1);
        }
    }

    /**
     * @param {Object[]} ordered
     * @returns {Promise<void>}
     */
    async _persistSequences(ordered) {
        const changed = ordered
            .map((layer, index) => [layer, index + 1])
            .filter(([layer, sequence]) => layer.sequence !== sequence);
        if (!changed.length) {
            return;
        }
        try {
            await Promise.all(
                changed.map(([layer, sequence]) =>
                    this.orm.write("geoengine.vector.layer", [layer.resId], {
                        sequence,
                    }),
                ),
            );
        } catch (error) {
            this.notification.add(
                _t(
                    "The new layer order could not be saved: %s",
                    error.message || error,
                ),
                { title: _t("Layer order"), type: "warning" },
            );
        }
    }

    /**
     * @param {*} dataRowId
     * @param {*} refId
     */
    resequence(dataRowId, refId) {
        const indexOf = (id) =>
            this.geoLayers.vectors.findIndex((r) => String(r.id) === String(id));

        const fromIndex = indexOf(dataRowId);
        if (fromIndex === -1) {
            debugLog("resequence: no layer with id", dataRowId);
            return;
        }
        let toIndex = 0;
        if (refId !== null && refId !== undefined) {
            const targetIndex = indexOf(refId);
            if (targetIndex === -1) {
                return;
            }
            toIndex = fromIndex > targetIndex ? targetIndex + 1 : targetIndex;
        }
        const [record] = this.geoLayers.vectors.splice(fromIndex, 1);
        this.geoLayers.vectors.splice(toIndex, 0, record);
    }
    /**
     * An overlay is shown or hidden on its own; a base map replaces the one
     * shown, and overlays stay as they are.
     *
     * @param {Object} layer
     * @param {boolean} checked
     */
    onRasterChange(layer, checked) {
        debugLog("onRasterChange", {
            name: layer.name,
            overlay: layer.overlay,
            checked,
        });
        if (layer.overlay) {
            layer.isVisible = checked;
        } else {
            for (const raster of this.geoLayers.rasters) {
                if (!raster.overlay) {
                    raster.isVisible = raster.id === layer.id;
                }
            }
        }
        this.props.onRasterChanged(false);
    }

    /**
     * @param {Object} layer
     * @param {Object} values
     */
    onRasterSaved(layer, values) {
        Object.assign(layer, values);
        this.props.onRasterChanged(true);
    }

    /**
     * @param {Object} vector
     * @param {boolean} checked
     */
    onCheckboxChange(vector, checked) {
        debugLog("CheckBox onChange fired:", {
            vectorName: vector.name,
            vectorId: vector.resId,
            checked: checked,
            previousValue: vector.isVisible,
        });
        this.onVectorChange(vector, LAYER_ACTIONS.VISIBLE_CHANGED, checked);
    }

    /**
     * @param {Object} layer
     * @param {string} action
     * @param {*} value
     * @returns {Promise<void>}
     */
    async onVectorChange(layer, action, value) {
        debugLog("onVectorChange", { layer: layer.name, action, value });

        const vectorLayer = this.geoLayers.vectors.find(
            (lay) => lay.resId === layer.resId,
        );
        if (!vectorLayer) {
            debugLog("No layer with resId", layer.resId);
            return;
        }

        let needsReload = false;
        switch (action) {
            case LAYER_ACTIONS.DOMAIN_CHANGED:
            case LAYER_ACTIONS.LAYER_CHANGED:
                needsReload = true;
                break;
            case LAYER_ACTIONS.VISIBLE_CHANGED:
                vectorLayer.isVisible = value;
                this.props.onLayerVisibility(vectorLayer.resId, value);
                break;
            case LAYER_ACTIONS.SEQUENCE_CHANGED:
                vectorLayer.sequence = value;
                this.props.onLayerOrder(vectorLayer.resId, value);
                break;
            default:
                debugLog("Unknown action: " + action);
                return;
        }

        if (needsReload) {
            await this.props.onLayersChanged();
        }
    }

    /**
     * @param {Object} vector
     */
    onEditFilterButtonSelected(vector) {
        this.addDialog(DomainSelectorDialog, {
            resModel: vector.model,
            domain: vector.model_domain || "[]",
            readonly: false,
            isDebugMode: Boolean(this.debug),
            onConfirm: (value) => this.onEditFilterDomainChanged(vector, value),
            title: _t("Domain editing"),
        });
    }

    /**
     * @param {Object} vector
     * @param {string} value
     * @returns {Promise<void>}
     */
    async onEditFilterDomainChanged(vector, value) {
        if (!this.isGeoengineAdmin) {
            await this.props.model.overrideLayerDomain(vector.resId, value);
            return;
        }
        try {
            await this.orm.write("geoengine.vector.layer", [vector.resId], {
                model_domain: value,
            });
        } catch (error) {
            this.notification.add(
                _t("The filter could not be saved: %s", error.message || error),
                { title: _t("Layer filter"), type: "warning" },
            );
            return;
        }
        this.props.model.layerDomainOverrides.delete(vector.resId);
        await this.onVectorChange(vector, LAYER_ACTIONS.DOMAIN_CHANGED, value);
    }

    async onEditButtonSelected(vector) {
        const view = await rpc("/web/action/load", {
            action_id: "geoengine.geo_vector_geoengine_view_action",
        });

        this.addDialog(FormViewDialog, {
            resModel: vector.resModel,
            title: _t("Editing vector layer"),
            viewId: view.view_id[0],
            resId: vector.resId,
            onRecordSaved: (record) =>
                this.onVectorChange(vector, LAYER_ACTIONS.LAYER_CHANGED, record.data),
        });
    }

    async onEditRasterButtonSelected(layer) {
        const view = await rpc("/web/action/load", {
            action_id: "geoengine.geo_engine_form_view_raster_action",
        });
        this.addDialog(FormViewDialog, {
            resModel: "geoengine.raster.layer",
            title: _t("Editing Raster Layer"),
            viewId: view.view_id[0],
            resId: layer.id,
            onRecordSaved: (record) => this.onRasterSaved(layer, record.data),
        });
    }

    fold() {
        this.state.isFolded = !this.state.isFolded;
    }

    /**
     * @returns {Promise<void>}
     */
    async openNewRaster() {
        this.actionService.doAction("geoengine.geo_raster_layer_list_action");
    }
}
