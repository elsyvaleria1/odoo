/** @odoo-module **/

import { loadGeoLibs, ol } from "@geoengine/lib/geo_libs";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

const ESRI_TILE_BASE = "https://server.arcgisonline.com/ArcGIS/rest/services";
const ESRI_ATTRIBUTION =
    "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community";

const HYBRID_LABELS_URL =
    "https://{a-d}.basemaps.cartocdn.com/rastertiles/dark_only_labels/{z}/{x}/{y}.png";
const HYBRID_LABELS_ATTRIBUTION = "© OpenStreetMap contributors © CARTO";

const SATELLITE_IMAGERY_MAX_ZOOM = 18;
const SATELLITE_LABEL_MAX_ZOOM = 19;
const MAP_MAX_ZOOM = 19;

export class PolygonDrawDialog extends Component {
    static template = "device_gps_geoengine.PolygonDrawDialog";
    static components = { Dialog };
    static props = {
        initialPoints: t.array().optional([]),
        currentRecordId: t.or([t.number(), t.boolean()]).optional(false),
        readonly: t.boolean().optional(false),
        onConfirm: t.function().optional(),
        onClear: t.function().optional(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.mapRef = elementRef();
        this.map = null;
        this.vectorSource = null;
        this.drawInteraction = null;
        this.existingSource = null;
        this.existingLayer = null;
        this.existingLoaded = false;

        this.orm = useService("orm");

        this.streetsLayer = null;
        this.satelliteLayer = null;
        this.satelliteLabelLayers = [];

        this.state = proxy({
            showExisting: false,
            baseMap: "streets",
        });

        onWillStart(() => loadGeoLibs());
        onMounted(() => this._initMap());
        onWillUnmount(() => this._destroyMap());
    }

    _initMap() {
        this.streetsLayer = new ol.layer.Tile({
            source: new ol.source.OSM(),
            visible: this.state.baseMap === "streets",
        });

        this.satelliteLayer = new ol.layer.Tile({
            source: new ol.source.XYZ({
                url: `${ESRI_TILE_BASE}/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
                attributions: ESRI_ATTRIBUTION,
                maxZoom: SATELLITE_IMAGERY_MAX_ZOOM,
            }),
            visible: this.state.baseMap === "satellite",
        });

        this.satelliteLabelLayers = [
            new ol.layer.Tile({
                source: new ol.source.XYZ({
                    url: HYBRID_LABELS_URL,
                    attributions: HYBRID_LABELS_ATTRIBUTION,
                    maxZoom: SATELLITE_LABEL_MAX_ZOOM,
                }),
                visible: this.state.baseMap === "satellite",
                className: "o_geofence_hybrid_labels",
            }),
        ];

        this.existingSource = new ol.source.Vector();
        this.existingLayer = new ol.layer.Vector({
            source: this.existingSource,
            style: new ol.style.Style({
                fill: new ol.style.Fill({ color: "rgba(128, 128, 128, 0.15)" }),
                stroke: new ol.style.Stroke({ color: "#666666", width: 1.5 }),
            }),
            visible: false,
        });

        this.vectorSource = new ol.source.Vector();
        const vectorLayer = new ol.layer.Vector({
            source: this.vectorSource,
            style: new ol.style.Style({
                fill: new ol.style.Fill({ color: "rgba(255, 0, 0, 0.25)" }),
                stroke: new ol.style.Stroke({ color: "#ff0000", width: 2 }),
            }),
        });

        const defaultCenter = ol.proj.fromLonLat([-100.0, 23.0]);

        this.map = new ol.Map({
            target: this.mapRef.el,
            layers: [
                this.streetsLayer,
                this.satelliteLayer,
                ...this.satelliteLabelLayers,
                this.existingLayer,
                vectorLayer,
            ],
            view: new ol.View({
                center: defaultCenter,
                zoom: 5,
                maxZoom: MAP_MAX_ZOOM,
            }),
        });

        if (this.props.initialPoints.length >= 3) {
            this._loadInitialPolygon();
        }

        if (!this.props.readonly) {
            this._activateDraw();
        }
    }

    _loadInitialPolygon() {
        const ring3857 = this.props.initialPoints.map(([lat, lon]) =>
            ol.proj.fromLonLat([lon, lat]),
        );
        const polygon = new ol.geom.Polygon([ring3857]);
        const feature = new ol.Feature({ geometry: polygon });
        this.vectorSource.addFeature(feature);

        this.map.getView().fit(polygon.getExtent(), {
            padding: [40, 40, 40, 40],
            maxZoom: 18,
        });
    }

    _activateDraw() {
        this.drawInteraction = new ol.interaction.Draw({
            source: this.vectorSource,
            type: "Polygon",
        });
        this.drawInteraction.on("drawstart", () => {
            this.vectorSource.clear();
        });
        this.map.addInteraction(this.drawInteraction);
    }

    _destroyMap() {
        if (this.map) {
            this.map.setTarget(null);
            this.map = null;
        }
    }

    onChangeBaseMap(ev) {
        const value = ev.target.value;
        if (value !== "streets" && value !== "satellite") {
            return;
        }
        this.state.baseMap = value;
        this.streetsLayer.setVisible(value === "streets");
        this.satelliteLayer.setVisible(value === "satellite");
        this.satelliteLabelLayers.forEach((layer) =>
            layer.setVisible(value === "satellite"),
        );
    }

    async onToggleShowExisting(ev) {
        this.state.showExisting = ev.target.checked;
        this.existingLayer.setVisible(this.state.showExisting);
        if (this.state.showExisting && !this.existingLoaded) {
            await this._loadExistingGeofences();
            this.existingLoaded = true;
        }
    }

    async _loadExistingGeofences() {
        const domain = [
            ["active", "=", true],
            ["geofence_type", "in", ["polygon", "rectangle"]],
            ["polygon_points", "!=", false],
        ];
        if (this.props.currentRecordId) {
            domain.push(["id", "!=", this.props.currentRecordId]);
        }

        let records;
        try {
            records = await this.orm.searchRead("device.geo.fence", domain, [
                "id",
                "name",
                "polygon_points",
            ]);
        } catch (error) {
            console.warn("[polygon_draw] failed to load existing geofences:", error);
            return;
        }

        for (const record of records) {
            let points;
            try {
                points = JSON.parse(record.polygon_points);
            } catch {
                continue;
            }
            if (!Array.isArray(points) || points.length < 3) {
                continue;
            }

            const ring3857 = points.map(([lat, lon]) => ol.proj.fromLonLat([lon, lat]));
            const polygon = new ol.geom.Polygon([ring3857]);
            const feature = new ol.Feature({ geometry: polygon, name: record.name });
            this.existingSource.addFeature(feature);
        }
    }

    onClickClear() {
        this.vectorSource.clear();
    }

    onClickSave() {
        const features = this.vectorSource.getFeatures();
        if (features.length === 0) {
            this.props.onClear?.();
            this.props.close();
            return;
        }

        const geometry = features[0].getGeometry();
        if (!(geometry instanceof ol.geom.Polygon)) {
            this.props.close();
            return;
        }

        const ring3857 = geometry.getCoordinates()[0];

        const ringOpen =
            ring3857.length > 1 &&
            ring3857[0][0] === ring3857[ring3857.length - 1][0] &&
            ring3857[0][1] === ring3857[ring3857.length - 1][1]
                ? ring3857.slice(0, -1)
                : ring3857;

        const points = ringOpen.map((coord) => {
            const [lon, lat] = ol.proj.toLonLat(coord);
            return [lat, lon];
        });

        this.props.onConfirm?.(points);
        this.props.close();
    }

    onClickCancel() {
        this.props.close();
    }
}
