/** @odoo-module native */

import { Domain } from "@web/core/domain";
import { searchModelOf } from "@web/core/search_model_hooks";
import { _t } from "@web/core/translation";

import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";

const debugLog = makeGeoLogger("SpatialFilter");

export const POINT_DISTANCES_KM = [1, 5, 25];
const SKETCH_COLOR = "rgba(255, 104, 10, 1)";
const SKETCH_FILL = "rgba(255, 104, 10, 0.15)";

/**
 * @param {string} projectionCode e.g. "EPSG:3857"
 * @returns {number}
 */
export function sridOf(projectionCode) {
    return Number(String(projectionCode).split(":").at(-1));
}

/**
 * Degrees need more digits than metres for the same ground precision.
 *
 * @param {number} srid
 * @returns {(value: number) => string}
 */
function coordinateFormatter(srid) {
    const digits = srid === 4326 ? 7 : 2;
    return (value) => String(Number(value.toFixed(digits)));
}

/**
 * @param {number[][][]} rings linear rings of a polygon, the first one outer
 * @param {number} srid
 * @returns {string}
 */
export function polygonEwkt(rings, srid) {
    const format = coordinateFormatter(srid);
    const text = rings
        .map(
            (ring) =>
                `(${ring.map(([x, y]) => `${format(x)} ${format(y)}`).join(", ")})`,
        )
        .join(", ");
    return `SRID=${srid};POLYGON(${text})`;
}

/**
 * @param {number[]} coordinate
 * @param {number} srid
 * @returns {string}
 */
export function pointEwkt([x, y], srid) {
    const format = coordinateFormatter(srid);
    return `SRID=${srid};POINT(${format(x)} ${format(y)})`;
}

/**
 * @param {string} fieldName
 * @param {string} ewkt
 * @returns {string}
 */
export function areaDomain(fieldName, ewkt) {
    return new Domain([[fieldName, "geo_intersect", ewkt]]).toString();
}

/**
 * @param {string} fieldName
 * @param {string} ewkt
 * @param {number} kilometres
 * @returns {string}
 */
export function nearDomain(fieldName, ewkt, kilometres) {
    return new Domain([
        [
            fieldName,
            "geo_dwithin",
            { geometry: ewkt, distance: kilometres * 1000, unit: "m" },
        ],
    ]).toString();
}

export class GeoengineSpatialFilter {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
        this._draw = null;
        this._layer = null;
        this._menu = null;
        this._onKeyDown = (event) => event.key === "Escape" && this.stop();
    }

    /** @returns {ol.Map} */
    get map() {
        return this.renderer.map;
    }

    /** @returns {boolean} */
    get isDrawing() {
        return this._draw !== null;
    }

    /**
     * The geometry field of the first layer drawing the view's own model: the
     * search filters that model, so another model's layer cannot be filtered.
     *
     * @returns {string|null}
     */
    get geoFieldName() {
        const model = this.renderer.props.model;
        const resModel = model.root.resModel;
        const layer = model.layers.vectors.find(
            (config) =>
                (config.model || resModel) === resModel && config.geo_field_name,
        );
        return layer?.geo_field_name || null;
    }

    createControl() {
        const { element, button } = this.renderer.interactions.createHtmlControl(
            '<i class="fa-solid fa-filter"></i>',
            "spatial-filter-control ol-unselectable ol-control",
        );
        button.title = _t("Filter by place");
        const menu = document.createElement("div");
        menu.className = "o_geoengine_spatial_menu dropdown-menu";
        const items = [
            [_t("Inside an area I draw"), () => this.startDrawing("Polygon")],
            [_t("On the visible map"), () => this.filterVisibleMap()],
            ...POINT_DISTANCES_KM.map((km) => [
                _t("Within %s km of a point I click", km),
                () => this.startDrawing("Point", km),
            ]),
        ];
        for (const [label, action] of items) {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "dropdown-item";
            item.textContent = label;
            item.addEventListener("click", () => {
                menu.classList.remove("show");
                action();
            });
            menu.appendChild(item);
        }
        element.appendChild(menu);
        button.addEventListener("click", () => {
            if (this._draw) {
                this.stop();
                return;
            }
            menu.classList.toggle("show");
        });
        this._menu = menu;
        this._button = button;
        this.map.addControl(new ol.control.Control({ element }));
    }

    filterVisibleMap() {
        const fieldName = this.geoFieldName;
        if (!fieldName) {
            return this._noField();
        }
        const map = this.map;
        const extent = map.getView().calculateExtent(map.getSize());
        return this._apply(
            _t("On the visible map"),
            areaDomain(fieldName, polygonEwkt([extentRing(extent)], this._srid())),
        );
    }

    /**
     * @param {"Polygon"|"Point"} type
     * @param {number} [kilometres]
     */
    startDrawing(type, kilometres) {
        const fieldName = this.geoFieldName;
        if (!fieldName) {
            return this._noField();
        }
        this.stop();
        const source = new ol.source.Vector();
        this._layer = new ol.layer.Vector({
            source,
            zIndex: 9999,
            style: new ol.style.Style({
                fill: new ol.style.Fill({ color: SKETCH_FILL }),
                stroke: new ol.style.Stroke({
                    color: SKETCH_COLOR,
                    width: 2,
                    lineDash: [8, 6],
                }),
                image: new ol.style.Circle({
                    radius: 5,
                    fill: new ol.style.Fill({ color: SKETCH_COLOR }),
                }),
            }),
        });
        this.map.addLayer(this._layer);
        this._draw = new ol.interaction.Draw({ source, type });
        this.map.addInteraction(this._draw);
        this._button?.classList.add("selected-control");
        document.addEventListener("keydown", this._onKeyDown);
        this._draw.on("drawend", (event) => {
            const geometry = event.feature.getGeometry();
            const srid = this._srid();
            const [description, domain] =
                type === "Point"
                    ? [
                          _t("Within %s km of a point", kilometres),
                          nearDomain(
                              fieldName,
                              pointEwkt(geometry.getCoordinates(), srid),
                              kilometres,
                          ),
                      ]
                    : [
                          _t("Inside the drawn area"),
                          areaDomain(
                              fieldName,
                              polygonEwkt(geometry.getCoordinates(), srid),
                          ),
                      ];
            setTimeout(() => this.stop());
            this._apply(description, domain);
        });
    }

    stop() {
        if (this._draw) {
            this.map.removeInteraction(this._draw);
            this._draw = null;
        }
        if (this._layer) {
            this.map.removeLayer(this._layer);
            this._layer = null;
        }
        this._button?.classList.remove("selected-control");
        document.removeEventListener("keydown", this._onKeyDown);
    }

    /**
     * @param {string} description
     * @param {string} domain
     */
    _apply(description, domain) {
        debugLog("spatial filter", { description, domain });
        this._searchModel().createNewFilters([{ description, domain }]);
    }

    _searchModel() {
        return searchModelOf(this.renderer);
    }

    _srid() {
        return sridOf(this.map.getView().getProjection().getCode());
    }

    _noField() {
        this.renderer.notification.add(
            _t("This map draws no geometry of its own records to filter by."),
            { type: "warning" },
        );
    }
}

/**
 * @param {number[]} extent
 * @returns {number[][]}
 */
export function extentRing([minX, minY, maxX, maxY]) {
    return [
        [minX, minY],
        [maxX, minY],
        [maxX, maxY],
        [minX, maxY],
        [minX, minY],
    ];
}
