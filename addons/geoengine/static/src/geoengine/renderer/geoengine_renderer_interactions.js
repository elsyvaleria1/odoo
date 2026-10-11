/** @odoo-module native */

import { getFieldCodec } from "@web/core/field_codec";
import { _t } from "@web/core/translation";
import { viewConfigOf } from "@web/core/view_config_hooks";

import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";
import {
    editCommandOf,
    EditHistory,
    partCount,
    ProblemMarker,
} from "./geoengine_edit_session.js";

const debugLog = makeGeoLogger("RendererInteractions");

export class GeoengineRendererInteractions {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
        this.tool = "select";
        this.history = new EditHistory();
        this._problemMarker = null;
        this._checkTicket = 0;
        this._beforeModify = new Map();
        this._shapeEdit = null;
        this._shapeDraw = null;
        this._shapeClick = null;
        this._onKeyDown = this._onKeyDown.bind(this);
    }

    refreshForLayers() {
        if (this.tool === "select") {
            this.registerInteraction();
            return;
        }
        debugLog("refreshForLayers() - keeping the active tool", this.tool);
        this.renderer.modifyClick?.getFeatures().clear();
        this.renderer.mapTools.attachSnap(this.renderer.vectorLayersResult);
    }

    _leaveSelection() {
        this.removeSelectInteraction();
        this._removeWebGLInteractions();
    }

    registerInteraction() {
        this._removeWebGLInteractions();
        this.removeSelectInteraction();

        if (this._needsPixelInteractions()) {
            debugLog("Registering pixel-hit interactions (WebGL or tiled layers)");
            this._registerWebGLInteractions();
        } else {
            debugLog("Registering Canvas-based interactions");
            this._registerCanvasInteractions();
        }
    }

    /**
     * WebGL and vector tile layers are hit by pixel: neither keeps the
     * feature objects ol.interaction.Select needs.
     *
     * @returns {boolean}
     */
    /**
     * A click that places a measurement or a spatial filter's vertex is not
     * a click on the feature under it.
     *
     * @returns {boolean}
     */
    _isSketching() {
        return Boolean(
            this.renderer.mapTools?.isMeasuring ||
            this.renderer.spatialFilter?.isDrawing,
        );
    }

    _needsPixelInteractions() {
        return (this.renderer.vectorLayersResult || []).some((layer) =>
            ["webgl", "tiles"].includes(layer.get("renderStrategy")),
        );
    }
    _registerCanvasInteractions() {
        this.renderer.selectPointerMove = new ol.interaction.Select({
            condition: ol.events.condition.pointerMove,
            style: (feature) => this.renderer.styling.selectStyle(feature),
        });
        this.renderer.selectClick = new ol.interaction.Select({
            condition: (event) =>
                ol.events.condition.click(event) && !this._isSketching(),
            style: (feature) => this.renderer.styling.selectStyle(feature),
        });

        this.renderer.selectClick.on("select", (e) => {
            const features = e.target.getFeatures();
            const clickCoord = e.mapBrowserEvent?.coordinate;
            this.updateInfoBox(features, clickCoord);
        });
        this.renderer.map.addInteraction(this.renderer.selectClick);
        this.renderer.map.addInteraction(this.renderer.selectPointerMove);
    }

    _registerWebGLInteractions() {
        const map = this.renderer.map;

        this._highlightedFeatureId = null;

        this._webglClickHandler = (event) => {
            if (this._isSketching()) {
                return;
            }
            const result = map.forEachFeatureAtPixel(
                event.pixel,
                (feature, layer) => ({ feature, layer }),
                {
                    hitTolerance: 5,
                },
            );

            if (result && result.feature) {
                const fakeCollection = {
                    item: (index) => (index === 0 ? result.feature : undefined),
                    getLength: () => 1,
                };
                this.updateInfoBox(fakeCollection, event.coordinate);
            } else {
                this.hidePopup();
            }
        };

        this._webglMoveHandler = (event) => {
            const result = map.forEachFeatureAtPixel(
                event.pixel,
                (feature, layer) => ({ feature, layer }),
                {
                    hitTolerance: 5,
                },
            );

            const featureId = result?.feature?.getId();

            if (this._highlightedFeatureId !== featureId) {
                this._highlightedFeatureId = featureId;

                map.getTargetElement().style.cursor = featureId ? "pointer" : "";

                this._updateWebGLHighlight(result?.layer, featureId);
            }
        };

        map.on("click", this._webglClickHandler);
        map.on("pointermove", this._webglMoveHandler);
    }

    _updateWebGLHighlight(layer, featureId) {
        if (this.renderer.vectorLayersResult) {
            for (const vLayer of this.renderer.vectorLayersResult) {
                const strategy = vLayer.get("renderStrategy");
                if (strategy === "webgl") {
                    if (typeof vLayer.updateStyleVariables === "function") {
                        vLayer.updateStyleVariables({
                            highlightedId: featureId ?? -1,
                        });
                    }
                }
            }
        }
    }

    _removeWebGLInteractions() {
        const map = this.renderer.map;
        if (map) {
            if (this._webglClickHandler) {
                map.un("click", this._webglClickHandler);
                this._webglClickHandler = null;
            }
            if (this._webglMoveHandler) {
                map.un("pointermove", this._webglMoveHandler);
                this._webglMoveHandler = null;
            }
        }
        this._highlightedFeatureId = null;
    }

    /**
     * @param {ol.Collection} features
     * @param {number[]} [clickCoord]
     */
    updateInfoBox(features, clickCoord) {
        const feature = features.item(0);
        const members = feature?.get("features");
        if (members?.length > 1) {
            this.hidePopup();
            this._zoomToCluster(members);
            return;
        }
        if (feature?.get("heatCell")) {
            this.hidePopup();
            return;
        }
        if (feature?.get("tiled")) {
            this._showTiledFeature(feature, clickCoord);
            return;
        }
        if (feature !== undefined) {
            const attributes = feature.get("attributes");
            const root = this.renderer.props.model.root;
            const resModel = feature.get("model") || root.resModel;
            let archInfo = this.renderer.props.archInfo;
            let model = root;
            if (resModel !== root.resModel) {
                const related = this.renderer.props.model.relatedModels?.get(resModel);
                archInfo = related?.archInfo || archInfo;
                model = null;
            }
            this.mountGeoengineRecord({
                archInfo,
                templateDocs: archInfo.templateDocs,
                model,
                attributes,
                resModel,
            });

            const coord =
                clickCoord || ol.extent.getCenter(feature.getGeometry().getExtent());
            this.renderer.overlay.setPosition(coord);

            this._panPopupIntoView();
        } else {
            this.hidePopup();
        }
    }

    /**
     * A tiled feature carries its record's id and styled values only: a cell
     * of several records zooms in, a record is read before its popup opens.
     *
     * @param {ol.Feature} feature
     * @param {number[]} [clickCoord]
     */
    async _showTiledFeature(feature, clickCoord) {
        const coord =
            clickCoord || ol.extent.getCenter(feature.getGeometry().getExtent());
        const view = this.renderer.map.getView();
        if (feature.get("cell")) {
            await this._showCellRecords(feature, coord);
            return;
        }
        if (feature.get("count") > 1 || feature.getId() === undefined) {
            this.hidePopup();
            debugLog("Zooming into a tile cell of", feature.get("count"), "records");
            view.animate({ center: coord, zoom: view.getZoom() + 2, duration: 250 });
            return;
        }
        await this.showTiledRecord(feature.get("model"), feature.getId(), coord);
    }

    /**
     * Records stacked in one fine-grid cell cannot be told apart by zooming:
     * their names are listed, and picking one opens its popup.
     *
     * @param {ol.Feature} feature
     * @param {number[]} coord
     */
    async _showCellRecords(feature, coord) {
        const model = this.renderer.props.model;
        const result = await model.readCellRecords(
            feature.get("layerId"),
            feature.get("cell"),
        );
        this.hidePopup();
        this.renderer.state.popupList = {
            key: (this.renderer.state.popupList?.key || 0) + 1,
            count: feature.get("count"),
            more: result.more,
            records: result.records,
            resModel: feature.get("model"),
            coord,
        };
        this.renderer.overlay.setPosition(coord);
        this._panPopupIntoView();
    }

    /**
     * @param {string} resModel
     * @param {number} resId
     * @param {number[]} coord
     */
    async showTiledRecord(resModel, resId, coord) {
        const model = this.renderer.props.model;
        const row = await model.readTiledRecord(resModel, resId);
        if (!row) {
            this.hidePopup();
            return;
        }
        const archInfo =
            resModel === model.root.resModel
                ? this.renderer.props.archInfo
                : model.relatedModels?.get(resModel)?.archInfo ||
                  this.renderer.props.archInfo;
        this.renderer.state.popupList = null;
        this.mountGeoengineRecord({
            archInfo,
            templateDocs: archInfo.templateDocs,
            record: this._recordFromRow(row, resModel, archInfo),
        });
        this.renderer.overlay.setPosition(coord);
        this._panPopupIntoView();
    }

    /**
     * A feature can be reshaped when its layer is not read-only, it draws the
     * view's own records, and the view loads the field it is drawn from: a
     * change to a field the record does not load would not be saved.
     *
     * @param {ol.Feature} feature
     * @returns {boolean}
     */
    _isEditableFeature(feature) {
        const root = this.renderer.props.model.root;
        return (
            feature.get("editable") === true &&
            feature.get("model") === root.resModel &&
            feature.get("geoField") in root.activeFields
        );
    }

    /**
     * A popup record for a row read from the server rather than loaded by the
     * view: its values are deserialized with the layer model's field
     * definitions, so the info box formats them as it formats a record.
     *
     * @param {Object} row
     * @param {string} resModel
     * @param {Object} archInfo
     * @returns {Object}
     */
    _recordFromRow(row, resModel, archInfo) {
        const model = this.renderer.props.model;
        const fields =
            model.relatedModels?.get(resModel)?.fields ||
            (resModel === model.root.resModel && model.root.fields) ||
            {};
        const values = Object.fromEntries(
            Object.entries(row).map(([name, value]) => [
                name,
                fields[name] && value !== false
                    ? getFieldCodec(fields[name].type).deserialize(value, fields[name])
                    : value,
            ]),
        );
        return {
            _values: values,
            resId: values.id ?? null,
            resModel,
            fieldNames: [
                ...new Set([
                    ...Object.keys(values),
                    ...Object.keys(archInfo?.fieldNodes || {}),
                ]),
            ],
            fields,
            context: {},
        };
    }

    /**
     * @param {ol.Feature[]} members
     */
    _zoomToCluster(members) {
        const [first, ...rest] = members;
        const extent = rest.reduce(
            (combined, member) =>
                ol.extent.extend(combined, member.getGeometry().getExtent()),
            first.getGeometry().getExtent().slice(),
        );
        debugLog("Zooming into a cluster of", members.length, "features");
        this.renderer.map.getView().fit(extent, {
            padding: [60, 60, 60, 60],
            duration: 250,
            maxZoom: this.renderer.map.getView().getZoom() + 4,
        });
    }

    /**
     * @param {Object} params
     * @param {Object} params.archInfo
     * @param {Object} params.templateDocs
     * @param {Object} params.model
     * @param {Object} params.attributes
     * @param {string} [params.resModel]
     * @param {Object} [params.record]
     */
    mountGeoengineRecord({
        archInfo,
        templateDocs,
        model,
        attributes,
        resModel,
        record,
    }) {
        if (record === undefined) {
            this.renderer.record = model?.records?.find(
                (element) => element.savedData.id === attributes.id,
            );

            if (!this.renderer.record) {
                this.renderer.record = this._recordFromRow(
                    attributes || {},
                    resModel || this.renderer.props.model.root.resModel,
                    archInfo,
                );
            }
        } else {
            this.renderer.record = record;
        }

        this.renderer.state.popup = {
            key: (this.renderer.state.popup?.key || 0) + 1,
            archInfo,
            record: this.renderer.record,
            templates: templateDocs,
        };
    }

    /**
     * @param {Object} record
     */
    onDisplayPopupRecord(record) {
        const feature = this.findFeatureById(record.resId ?? record.id);
        if (feature) {
            this.mountGeoengineRecord({
                archInfo: this.renderer.props.archInfo,
                templateDocs: this.renderer.props.archInfo.templateDocs,
                record,
            });
            const coord = ol.extent.getCenter(feature.getGeometry().getExtent());
            this.renderer.overlay.setPosition(coord);
            const mapView = this.renderer.map.getView();
            if (mapView) {
                mapView.animate(
                    {
                        center: feature.getGeometry().getFirstCoordinate(),
                        duration: 500,
                    },
                    () => {
                        this._panPopupIntoView();
                    },
                );
            }
        }
    }

    /**
     * @param {number|string} recordId
     * @returns {ol.Feature|null}
     */
    findFeatureById(recordId) {
        if (recordId === undefined || recordId === null) {
            return null;
        }
        for (const layer of this.renderer.vectorLayersResult || []) {
            const feature = layer.getSource()?.getFeatureById?.(recordId);
            if (feature) {
                return feature;
            }
        }
        return null;
    }

    _panPopupIntoView() {
        requestAnimationFrame(() => {
            const popupEl = this.renderer.popupRef.el;
            if (popupEl && this.renderer.overlay) {
                const height = popupEl.offsetHeight || 100;
                const width = popupEl.offsetWidth || 200;
                const verticalMargin = height + 50;
                const horizontalMargin = width / 2 + 60;
                const margin = Math.max(verticalMargin, horizontalMargin);
                this.renderer.overlay.panIntoView({
                    animation: { duration: 250 },
                    margin: margin,
                });
            }
        });
    }

    /**
     * @param {Object} record
     */
    zoomOnFeature(record) {
        const recordId = record.resId || record.id;
        if (!recordId) {
            console.warn(
                "[GeoengineRendererInteractions] No record ID available for zoom",
            );
            return;
        }

        const feature = this.findFeatureById(recordId);
        if (!feature) {
            console.warn(
                "[GeoengineRendererInteractions] Feature not found for record:",
                recordId,
            );
            return;
        }

        const geometry = feature.getGeometry();
        if (!geometry) {
            console.warn(
                "[GeoengineRendererInteractions] Feature has no geometry:",
                recordId,
            );
            return;
        }

        const mapView = this.renderer.map.getView();
        if (mapView) {
            mapView.fit(geometry, {
                maxZoom: 16,
                padding: [100, 100, 100, 100],
                duration: 500,
            });
        }
    }

    /**
     * @param {Object[]} records
     */
    zoomToRecords(records) {
        let combined = null;
        for (const record of records || []) {
            const feature = this.findFeatureById(record.resId ?? record.id);
            const extent = feature?.getGeometry()?.getExtent();
            if (!extent || ol.extent.isEmpty(extent)) {
                continue;
            }
            combined = combined ? ol.extent.extend(combined, extent) : extent.slice();
        }
        if (!combined) {
            debugLog("zoomToRecords: nothing rendered for this group");
            return;
        }
        this.renderer.map.getView().fit(combined, {
            maxZoom: 16,
            padding: [100, 100, 100, 100],
            duration: 500,
        });
    }

    clickToHidePopup() {
        this.hidePopup();
    }

    hidePopup() {
        this.renderer.overlay.setPosition(undefined);
        this.renderer.state.popup = null;
        this.renderer.state.popupList = null;
        this.renderer.record = null;
    }

    onInfoBoxClicked() {
        if (!this.renderer.record) {
            console.warn(
                "[GeoengineRendererInteractions] No record available for info box click",
            );
            return;
        }

        const rootModel = this.renderer.props.model.root.resModel;
        const resModel = this.renderer.record.resModel || rootModel;
        const viewIds =
            resModel === rootModel ? viewConfigOf(this.renderer).views || [] : [];
        const formView = viewIds.find(([, type]) => type === "form");
        this.renderer.props.openRecord(
            resModel,
            this.renderer.record.resId,
            formView ? formView[0] : false,
        );
    }

    /**
     * @param {"draw"|"modify"|"select"} tool
     */
    _enterTool(tool) {
        this._stopShapeEdit();
        this.tool = tool;
        this.history.clear();
        this._problemMarker?.clear();
        document.removeEventListener("keydown", this._onKeyDown);
        if (tool !== "select") {
            document.addEventListener("keydown", this._onKeyDown);
        }
        this._refreshUndoButtons();
    }

    /**
     * @param {KeyboardEvent} event
     */
    _onKeyDown(event) {
        const sketching = this._shapeDraw ?? this.renderer.drawInteraction;
        const command = editCommandOf(event, this._shapeEdit ? "draw" : this.tool);
        if (!command) {
            return;
        }
        if (command === "abort") {
            if (this._shapeEdit) {
                this._stopShapeEdit();
            } else {
                sketching?.abortDrawing();
            }
            return;
        }
        event.preventDefault();
        if (command === "remove-last-point") {
            sketching?.removeLastPoint();
        } else if (command === "undo") {
            this.undo();
        } else {
            this.redo();
        }
    }

    async undo() {
        const step = this.history.undo();
        this._refreshUndoButtons();
        if (step) {
            await this._restoreStep(step, step.before);
        }
    }

    async redo() {
        const step = this.history.redo();
        this._refreshUndoButtons();
        if (step) {
            await this._restoreStep(step, step.after);
        }
    }

    /**
     * @param {import("./geoengine_edit_session.js").EditStep} step
     * @param {ol.geom.Geometry} geometry
     */
    async _restoreStep(step, geometry) {
        const feature = this._featureOf(step.resId, step.geoField);
        feature?.setGeometry(geometry.clone());
        await this._writeGeometry(step.resId, step.geoField, geometry);
    }

    /**
     * @param {number} resId
     * @param {string} geoField
     * @returns {ol.Feature|undefined}
     */
    _featureOf(resId, geoField) {
        for (const layer of this.renderer.vectorLayersResult || []) {
            const source = layer.getSource?.();
            const features = (source?.getSource?.() ?? source)?.getFeatures?.() ?? [];
            const feature = features.find(
                (candidate) =>
                    candidate.getId() === resId &&
                    candidate.get("geoField") === geoField,
            );
            if (feature) {
                return feature;
            }
        }
        return undefined;
    }

    /**
     * Writes a reshaped geometry to its record, then shows whether the server
     * can store it as drawn.
     *
     * @param {number} resId
     * @param {string} geoField
     * @param {ol.geom.Geometry} geometry
     */
    async _writeGeometry(resId, geoField, geometry) {
        const root = this.renderer.props.model.root;
        const record = root.records.find((el) => el.resId === resId);
        if (!record) {
            debugLog("a reshaped feature with no record", resId);
            return;
        }
        await record.switchMode("edit");
        await this.renderer.props.updateRecord(
            this.serializeGeometry(geometry),
            geoField,
        );
        await this._checkGeometry(root.resModel, geoField, geometry);
    }

    /**
     * @param {string} resModel
     * @param {string} geoField
     * @param {string} value
     * @param {ol.geom.Geometry} geometry
     * @returns {Promise<boolean>}
     */
    async _isStorable(resModel, geoField, value, geometry) {
        return !(await this._checkGeometry(resModel, geoField, geometry, value));
    }

    /**
     * Asks the server what would keep the shape from being stored as drawn,
     * marks the place and says why. A check overtaken by a later edit is
     * not shown.
     *
     * @param {string} resModel
     * @param {string} geoField
     * @param {ol.geom.Geometry} geometry
     * @param {string} [value]
     * @returns {Promise<{message: string, location: Array<number>|null}|null>}
     */
    async _checkGeometry(resModel, geoField, geometry, value) {
        const ticket = ++this._checkTicket;
        let problem;
        try {
            problem = await this.renderer.props.model.orm.silent.call(
                resModel,
                "get_geometry_problem",
                [geoField, value ?? this.serializeGeometry(geometry)],
            );
        } catch (error) {
            debugLog("geometry check failed; saving will check again", error);
            return null;
        }
        if (ticket !== this._checkTicket) {
            return problem;
        }
        if (!problem) {
            this._problemMarker?.clear();
            return null;
        }
        this._problemMarker ??= new ProblemMarker(this.renderer.map);
        this._problemMarker.show(problem.location, geometry);
        this.renderer.notification.add(problem.message, {
            title: _t("This shape cannot be stored as drawn"),
            type: "warning",
        });
        return problem;
    }

    createUndoControl() {
        const element = document.createElement("div");
        element.className = "undo-control ol-unselectable ol-control";
        const button = (icon, title, action) => {
            const node = document.createElement("button");
            node.type = "button";
            node.title = title;
            node.innerHTML = `<i class="fa-solid ${icon}"></i>`;
            node.addEventListener("click", action);
            element.appendChild(node);
            return node;
        };
        this._undoButton = button("fa-rotate-left", _t("Undo (Ctrl+Z)"), () =>
            this.undo(),
        );
        this._redoButton = button("fa-rotate-right", _t("Redo (Ctrl+Y)"), () =>
            this.redo(),
        );
        this._shapeButtons = {
            add_area: button("fa-square-plus", _t("Add an area to the shape"), () =>
                this._startShapeEdit("add_area"),
            ),
            cut_area: button("fa-scissors", _t("Cut an area out of the shape"), () =>
                this._startShapeEdit("cut_area"),
            ),
            remove_part: button("fa-eraser", _t("Remove one part of the shape"), () =>
                this._startShapeEdit("remove_part"),
            ),
            split: button(
                "fa-object-ungroup",
                _t("Split the shape along a line into records"),
                () => this._startShapeEdit("split"),
            ),
            merge: button(
                "fa-object-group",
                _t("Merge the selected shapes into the first one selected"),
                () => this._mergeSelectedShapes(),
            ),
        };
        this._undoControl = element;
        this.renderer.map.addControl(new ol.control.Control({ element }));
        this._refreshUndoButtons();
    }

    _refreshUndoButtons() {
        if (!this._undoControl) {
            return;
        }
        this._undoControl.hidden = this.tool !== "modify";
        this._undoButton.disabled = !this.history.canUndo;
        this._redoButton.disabled = !this.history.canRedo;
        const geometry = this._selectedFeature()?.getGeometry();
        const areal = /Polygon/.test(geometry?.getType() ?? "");
        this._shapeButtons.add_area.disabled = !areal;
        this._shapeButtons.cut_area.disabled = !areal;
        this._shapeButtons.remove_part.disabled = partCount(geometry) < 2;
        this._shapeButtons.split.disabled = !areal;
        this._shapeButtons.merge.disabled = this._mergeableFeatures().length < 2;
        for (const [edit, node] of Object.entries(this._shapeButtons)) {
            node.classList.toggle("selected-control", this._shapeEdit === edit);
        }
    }

    /**
     * @returns {ol.Feature|undefined}
     */
    _selectedFeature() {
        return this.renderer.modifyClick?.getFeatures().item(0);
    }

    /**
     * The selected features, in the order they were selected, when they all
     * draw the same field.
     *
     * @returns {Array<ol.Feature>}
     */
    _mergeableFeatures() {
        const features = this.renderer.modifyClick?.getFeatures().getArray() ?? [];
        const fields = new Set(features.map((feature) => feature.get("geoField")));
        return fields.size === 1 ? features : [];
    }

    /**
     * Starts an edit of the selected shape: a drawn area to add or cut out,
     * a click on the part to remove, or a line to split it along. Reshaping
     * pauses meanwhile.
     *
     * @param {"add_area"|"cut_area"|"remove_part"|"split"} edit
     */
    _startShapeEdit(edit) {
        const feature = this._selectedFeature();
        this._stopShapeEdit();
        if (!feature) {
            return;
        }
        this._shapeEdit = edit;
        this.renderer.modifyInteraction?.setActive(false);
        this.renderer.modifyClick?.setActive(false);
        if (edit === "remove_part") {
            this._shapeClick = (event) =>
                this._applyShapeEdit(
                    feature,
                    edit,
                    new ol.geom.Point(event.coordinate),
                );
            this.renderer.map.once("click", this._shapeClick);
        } else {
            this._shapeDraw = new ol.interaction.Draw({
                type: edit === "split" ? "LineString" : "Polygon",
                stopClick: true,
            });
            this._shapeDraw.on("drawend", (event) => {
                const sketch = event.feature.getGeometry();
                if (edit === "split") {
                    this._splitShape(feature, sketch);
                } else {
                    this._applyShapeEdit(feature, edit, sketch);
                }
            });
            this.renderer.map.addInteraction(this._shapeDraw);
        }
        this._refreshUndoButtons();
    }

    _stopShapeEdit() {
        if (this._shapeDraw) {
            this.renderer.map.removeInteraction(this._shapeDraw);
            this._shapeDraw = null;
        }
        if (this._shapeClick) {
            this.renderer.map.un("click", this._shapeClick);
            this._shapeClick = null;
        }
        this._shapeEdit = null;
        this.renderer.modifyInteraction?.setActive(true);
        this.renderer.modifyClick?.setActive(true);
        this._refreshUndoButtons();
    }

    /**
     * Runs a record action that creates or archives records: the edited
     * record is saved first, the view reloads after, and the reshapes made
     * before can no longer be undone.
     *
     * @param {Array<number>} resIds
     * @param {string} method
     * @param {Array} args
     */
    async _runShapeAction(resIds, method, args) {
        const root = this.renderer.props.model.root;
        if (root.editedRecord && !(await root.editedRecord.save())) {
            return;
        }
        let action;
        try {
            action = await this.renderer.props.model.orm.silent.call(
                root.resModel,
                method,
                [resIds, ...args],
            );
        } catch (error) {
            this.renderer.notification.add(
                error.data?.message ?? error.message ?? String(error),
                { title: _t("The shapes were not changed"), type: "warning" },
            );
            return;
        }
        this.history.clear();
        this.renderer.modifyClick?.getFeatures().clear();
        await root.load();
        if (action) {
            await this.renderer.action.doAction(action);
        }
        this._refreshUndoButtons();
    }

    /**
     * @param {ol.Feature} feature
     * @param {ol.geom.LineString} line
     */
    async _splitShape(feature, line) {
        setTimeout(() => this._stopShapeEdit());
        await this._runShapeAction([feature.getId()], "action_split_shape", [
            feature.get("geoField"),
            this.serializeGeometry(line),
        ]);
    }

    async _mergeSelectedShapes() {
        const features = this._mergeableFeatures();
        if (features.length < 2) {
            return;
        }
        await this._runShapeAction(
            features.map((feature) => feature.getId()),
            "action_merge_shapes",
            [features[0].get("geoField")],
        );
    }

    /**
     * Asks the server for the selected shape after the edit, then writes it
     * to the record as a reshape: it is checked and can be undone.
     *
     * @param {ol.Feature} feature
     * @param {"add_area"|"cut_area"|"remove_part"} edit
     * @param {ol.geom.Geometry} sketch
     */
    async _applyShapeEdit(feature, edit, sketch) {
        setTimeout(() => this._stopShapeEdit());
        const geoField = feature.get("geoField");
        const before = feature.getGeometry().clone();
        let edited;
        try {
            edited = await this.renderer.props.model.orm.silent.call(
                this.renderer.props.model.root.resModel,
                "get_edited_shape",
                [
                    geoField,
                    this.serializeGeometry(before),
                    this.serializeGeometry(sketch),
                    edit,
                ],
            );
        } catch (error) {
            this.renderer.notification.add(
                error.data?.message ?? error.message ?? String(error),
                { title: _t("The shape was not changed"), type: "warning" },
            );
            return;
        }
        const after = new ol.format.GeoJSON().readGeometry(edited);
        feature.setGeometry(after);
        this.renderer.state.isModified = true;
        this.history.record({
            resId: feature.getId(),
            geoField,
            before,
            after: after.clone(),
        });
        this._refreshUndoButtons();
        await this._writeGeometry(feature.getId(), geoField, after);
    }

    teardown() {
        document.removeEventListener("keydown", this._onKeyDown);
        this._problemMarker?.destroy();
        this._problemMarker = null;
        this.history.clear();
    }

    createEditControl() {
        const { element, button } = this.createHtmlControl(
            '<i class="fa-solid fa-wand-magic-sparkles"></i>',
            "edit-control ol-unselectable ol-control",
        );

        button.addEventListener("click", () => {
            this.hidePopup();
            this.addSelectedClassToButton(button);
            this.removeDrawInteraction();
            this._leaveSelection();
            this._enterTool("modify");

            if (
                this.renderer.modifyClick === undefined &&
                this.renderer.modifyInteraction === undefined
            ) {
                this.renderer.modifyClick = new ol.interaction.Select({
                    condition: ol.events.condition.click,
                    filter: (feature) => this._isEditableFeature(feature),
                });
                this.renderer.modifyInteraction = new ol.interaction.Modify({
                    features: this.renderer.modifyClick.getFeatures(),
                });
                this.renderer.modifyInteraction.on("modifystart", (ev) => {
                    this._beforeModify = new Map(
                        ev.features
                            .getArray()
                            .map((feature) => [feature, feature.getGeometry().clone()]),
                    );
                });
                this.renderer.modifyInteraction.on("modifyend", async (ev) => {
                    this.renderer.state.isModified = true;
                    const [feature] = ev.features.getArray();
                    const before = this._beforeModify.get(feature);
                    if (before) {
                        this.history.record({
                            resId: feature.getId(),
                            geoField: feature.get("geoField"),
                            before,
                            after: feature.getGeometry().clone(),
                        });
                        this._refreshUndoButtons();
                    }
                    await this._writeGeometry(
                        feature.getId(),
                        feature.get("geoField"),
                        feature.getGeometry(),
                    );
                });
                this.renderer.modifyClick.on("select", () =>
                    this._refreshUndoButtons(),
                );
                this.renderer.map.addInteraction(this.renderer.modifyClick);
                this.renderer.map.addInteraction(this.renderer.modifyInteraction);
                this.renderer.mapTools.attachSnap(this.renderer.vectorLayersResult);
            }
        });

        const EditControl = new ol.control.Control({
            element: element,
        });
        this.renderer.map.addControl(EditControl);
    }

    createDrawControl() {
        const { element, button } = this.createHtmlControl(
            '<i class="fa-solid fa-pencil"></i>',
            "draw-control ol-unselectable ol-control",
        );
        button.addEventListener("click", () => {
            this.hidePopup();
            this.addSelectedClassToButton(button);
            this.removeModifyInteraction();
            this._leaveSelection();
            this._enterTool("draw");
            if (this.renderer.props.model.root.editedRecord !== undefined) {
                this.renderer.props.onClickDiscard();
            }
            if (this.renderer.drawInteraction === undefined) {
                const key = this.renderer.props.geoFieldKey;

                if (!key) {
                    console.warn(
                        "[GeoengineRendererInteractions] No geometry field found for drawing",
                    );
                    return;
                }

                const geoField = this.renderer.props.model.root.fields[key];
                if (!geoField?.geo_type) {
                    console.warn(
                        "[GeoengineRendererInteractions] Geometry field missing geo_type configuration",
                    );
                    return;
                }

                this.renderer.drawInteraction = new ol.interaction.Draw({
                    type: geoField.geo_type,
                    stopClick: true,
                });
                this.renderer.map.addInteraction(this.renderer.drawInteraction);
                this.renderer.mapTools.attachSnap(this.renderer.vectorLayersResult);
                this.renderer.drawInteraction.on("drawstart", () => {
                    this.renderer.props.onDrawStart();
                });

                this.renderer.drawInteraction.on("drawend", async (ev) => {
                    const geometry = ev.feature.getGeometry();
                    const value = this.serializeGeometry(geometry);
                    const resModel = this.renderer.props.model.root.resModel;
                    if (await this._isStorable(resModel, key, value, geometry)) {
                        this.renderer.props.createRecord(resModel, key, value);
                    }
                });
            }
        });

        const DrawControl = new ol.control.Control({
            element: element,
        });
        this.renderer.map.addControl(DrawControl);
    }

    createSelectControl() {
        const { element, button } = this.createHtmlControl(
            '<i class="fa-solid fa-mouse-pointer"></i>',
            "select-control ol-unselectable ol-control",
        );
        this.addSelectedClassToButton(button);

        button.addEventListener("click", () => {
            this.addSelectedClassToButton(button);
            this.removeDrawInteraction();
            this.removeModifyInteraction();
            this._enterTool("select");
            if (this.renderer.props.model.root.editedRecord !== undefined) {
                this.renderer.props.onClickDiscard();
            }
            this.registerInteraction();
        });

        const SelectControl = new ol.control.Control({
            element: element,
        });
        this.renderer.map.addControl(SelectControl);
    }

    /**
     * @param {HTMLElement} button
     */
    addSelectedClassToButton(button) {
        const scope = this.renderer.map?.getTargetElement() || document;
        scope
            .querySelectorAll(".selected-control")
            .forEach((el) => el.classList.remove("selected-control"));
        button.classList.add("selected-control");
    }

    removeDrawInteraction() {
        if (this.renderer.drawInteraction !== undefined) {
            this.renderer.map.removeInteraction(this.renderer.drawInteraction);
            this.renderer.drawInteraction = undefined;
            this.renderer.mapTools.detachSnap();
        }
    }

    removeModifyInteraction() {
        if (
            this.renderer.modifyClick !== undefined &&
            this.renderer.modifyInteraction !== undefined
        ) {
            this.renderer.map.removeInteraction(this.renderer.modifyClick);
            this.renderer.map.removeInteraction(this.renderer.modifyInteraction);
            this.renderer.modifyClick = undefined;
            this.renderer.modifyInteraction = undefined;
            this.renderer.mapTools.detachSnap();
        }
    }

    removeSelectInteraction() {
        if (
            this.renderer.selectClick !== undefined &&
            this.renderer.selectPointerMove !== undefined
        ) {
            this.renderer.map.removeInteraction(this.renderer.selectClick);
            this.renderer.map.removeInteraction(this.renderer.selectPointerMove);
            this.renderer.selectClick = undefined;
            this.renderer.selectPointerMove = undefined;
        }
    }

    /**
     * @param {ol.geom.Geometry} geometry
     * @returns {string}
     */
    serializeGeometry(geometry) {
        const projection = this.renderer.map.getView().getProjection();
        const code = projection.getCode();
        const geojson = JSON.parse(
            new ol.format.GeoJSON().writeGeometry(geometry, {
                dataProjection: projection,
                featureProjection: projection,
            }),
        );
        geojson.crs = { type: "name", properties: { name: code } };
        return JSON.stringify(geojson);
    }

    /**
     * @param {string} innerHTML
     * @param {string} className
     * @returns {Object}
     */
    createHtmlControl(innerHTML, className) {
        const button = document.createElement("button");
        button.innerHTML = innerHTML;
        const element = document.createElement("div");
        element.className = className;
        element.appendChild(button);
        return { element, button };
    }
}
