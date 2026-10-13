/** @odoo-module native */
import { Component, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { isCtrlOrCmdKey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { L } from "@web/core/lib/leaflet";
import { _t } from "@web/core/translation";
import { delay } from "@web/core/utils/concurrency";
import { useSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { renderToString } from "@web/core/utils/render";
import { useReactiveModel } from "@web/model/model";
import { hasCoordinates } from "@web_map/map_view/map_model";

const apiTilesRouteWithToken =
    "https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token={accessToken}";
const apiTilesRouteWithoutToken = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png";

const colors = [
    "#F06050",
    "#6CC1ED",
    "#F7CD1F",
    "#814968",
    "#30C381",
    "#D6145F",
    "#475577",
    "#F4A460",
    "#EB7E7F",
    "#2C8397",
];

const GOOGLE_MAPS_MAX_WAYPOINTS = 9;
const GOOGLE_MAPS_MAX_WAYPOINTS_MOBILE = 3;

const mapTileAttribution = `
    © <a href="https://www.mapbox.com/about/maps/">Mapbox</a>
    © <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>
    <strong>
        <a href="https://www.mapbox.com/map-feedback/" target="_blank">
            Improve this map
        </a>
    </strong>`;

const log = makeLogger("map.renderer");

export class MapRenderer extends Component {
    static template = "web_map.MapRenderer";
    static markerPopupTemplate = "web_map.markerPopup";
    static props = { model: t.object(), onMarkerClick: t.function() };
    static subTemplates = {
        PinListContainer: "web_map.MapRenderer.PinListContainer",
        PinList: "web_map.MapRenderer.PinList",
        PinListItems: "web_map.MapRenderer.PinListItems",
        RoutingUnavailable: "web_map.MapRenderer.RoutingUnavailable",
        FetchingCoordinates: "web_map.MapRenderer.FetchingCoordinates",
        NoMapToken: "web_map.MapRenderer.NoMapToken",
    };
    props = useProps(this.constructor.props);

    get subTemplates() {
        return this.constructor.subTemplates;
    }

    setup() {
        this.ui = useService("ui");
        useLifecycleLog(log);
        this.model = useReactiveModel(this.props.model);
        this.leafletMap = null;
        this.markers = [];
        this.polylines = [];
        this.mapContainerRef = elementRef();
        this.state = proxy({
            closedGroupIds: [],
            expandedPinList: false,
            dismissedAlerts: {},
        });
        this.nextId = 1;
        this.renderedMarkerSignature = null;
        this.fittedBoundsSignature = null;
        this.groupedByKey = this.model.data.groupByKey;

        useLayoutEffect(
            () => {
                this.leafletMap = L.map(this.mapContainerRef.el, {
                    maxBounds: [L.latLng(-90, -180), L.latLng(90, 180)],
                });
                this.leafletMap.attributionControl.setPrefix(
                    '<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">Leaflet</a>',
                );
                L.tileLayer(this.apiTilesRoute, {
                    attribution: mapTileAttribution,
                    tileSize: 512,
                    zoomOffset: -1,
                    minZoom: 2,
                    maxZoom: 19,
                    id: "mapbox/streets-v11",
                    accessToken: this.model.metaData.mapBoxToken,
                }).addTo(this.leafletMap);
            },
            () => [],
        );
        useLayoutEffect(
            () => this.updateMap(),
            () => [
                this.getMarkersInfo(),
                this.model.data.routes,
                this.model.data.shouldUpdatePosition,
                this.model.data.groupByKey,
            ],
        );

        this.pinListRef = elementRef();
        useSortable({
            enable: () => this.model.canResequence,
            ref: this.pinListRef,
            elements: ".o-map-renderer--pin-located",
            handle: ".o_row_handle",
            onDrop: async (params) => {
                const rowId = parseInt(params.element.dataset.id);
                const previousRowId = parseInt(params.previous?.dataset?.id) || null;
                await this.model.resequence(rowId, previousRowId);
            },
        });

        onWillUnmount(this.onWillUnmount);
    }
    onWillUnmount() {
        this.removeMarkers();
        this.removeRoutes();
        if (this.leafletMap) {
            this.leafletMap.remove();
        }
    }

    /** @returns {string} */
    get apiTilesRoute() {
        return this.model.data.useMapBoxAPI
            ? apiTilesRouteWithToken
            : apiTilesRouteWithoutToken;
    }

    /** @returns {Object[]} */
    getMarkersInfo() {
        const markersInfo = new Map();
        const pinInSamePlace = {};
        for (const record of this.getVisibleRecords()) {
            const partner = record.partner;
            if (!hasCoordinates(partner)) {
                continue;
            }
            const position = `${partner.partner_latitude}-${partner.partner_longitude}`;
            const key = this.model.data.isGrouped
                ? `${position}-${record.groupId}`
                : position;
            const markerInfo = markersInfo.get(key);
            if (markerInfo) {
                markerInfo.records.push(record);
                markerInfo.ids.push(record.id);
            } else {
                pinInSamePlace[position] = ++pinInSamePlace[position] || 0;
                markersInfo.set(key, {
                    records: [record],
                    ids: [record.id],
                    pinInSamePlace: pinInSamePlace[position],
                });
            }
        }
        return [...markersInfo.values()];
    }

    /**
     * @param {Object} record
     * @returns {boolean}
     */
    isRecordLocated(record) {
        return hasCoordinates(record.partner);
    }

    /**
     * @param {Object} record
     * @returns {string}
     */
    getPinListItemClass(record) {
        return this.isRecordLocated(record)
            ? "cursor-pointer o-map-renderer--pin-located"
            : "text-muted";
    }

    /**
     * @param {Object} record
     * @param {Object[]} records
     * @returns {number}
     */
    getPinNumber(record, records) {
        return (
            records
                .filter((candidate) => this.isRecordLocated(candidate))
                .findIndex((candidate) => candidate.id === record.id) + 1
        );
    }

    /**
     * @param {Object} markerInfo
     * @returns {Object}
     */
    getMarkerRecord(markerInfo) {
        return markerInfo.records[0];
    }

    /**
     * @param {Object} markerInfo
     * @returns {number}
     */
    getMarkerNumber(markerInfo) {
        const record = this.getMarkerRecord(markerInfo);
        const records = this.model.data.isGrouped
            ? this.model.data.recordGroups[record.groupId].records
            : this.model.data.records;
        return this.getPinNumber(record, records);
    }

    /**
     * @param {Object[]} markersInfos
     * @returns {string}
     */
    getMarkerSignature(markersInfos) {
        return JSON.stringify([
            this.model.data.revision,
            this.model.metaData.numbering,
            this.model.data.isGrouped,
            markersInfos.map((markerInfo) => {
                const record = this.getMarkerRecord(markerInfo);
                return [
                    markerInfo.ids,
                    markerInfo.pinInSamePlace,
                    record.partner.partner_latitude,
                    record.partner.partner_longitude,
                    record.groupId ?? null,
                    this.getMarkerNumber(markerInfo),
                ];
            }),
        ]);
    }

    addMarkers() {
        const endMarkers = log.perf("addMarkers");
        this.removeMarkers();

        for (const markerInfo of this.getMarkersInfo()) {
            const record = this.getMarkerRecord(markerInfo);
            const params = {
                count: markerInfo.ids.length,
                isMulti: markerInfo.ids.length > 1,
                number: this.getMarkerNumber(markerInfo),
                numbering: this.model.metaData.numbering,
            };

            if (this.model.data.isGrouped) {
                params.color = this.getGroupColor(record.groupId);
            }

            const iconInfo = {
                className: "o-map-renderer--marker",
                html: renderToString("web_map.marker", params),
            };

            const offset = markerInfo.pinInSamePlace * 0.000025;
            const marker = L.marker(
                [
                    record.partner.partner_latitude + offset,
                    record.partner.partner_longitude - offset,
                ],
                { icon: L.divIcon(iconInfo) },
            );
            marker.addTo(this.leafletMap);
            marker.on("click", () => {
                this.createMarkerPopup(markerInfo, offset);
            });
            this.markers.push(marker);
        }
        endMarkers({ markers: this.markers.length });
    }
    addRoutes() {
        this.removeRoutes();
        log.logic("addRoutes", () => ({
            mapbox: this.model.data.useMapBoxAPI,
            routes: this.model.data.routes?.length,
        }));
        if (!this.model.data.useMapBoxAPI || !this.model.data.routes.length) {
            return;
        }

        for (const leg of this.model.data.routes[0].legs) {
            const latLngs = [];
            for (const step of leg.steps) {
                for (const coordinate of step.geometry.coordinates) {
                    latLngs.push(L.latLng(coordinate[1], coordinate[0]));
                }
            }

            const polyline = L.polyline(latLngs, {
                color: "blue",
                weight: 5,
                opacity: 0.3,
            }).addTo(this.leafletMap);

            const polylines = this.polylines;
            polyline.on("click", function () {
                for (const polyline of polylines) {
                    polyline.setStyle({ color: "blue", opacity: 0.3 });
                }
                this.setStyle({ color: "darkblue", opacity: 1.0 });
            });
            this.polylines.push(polyline);
        }
    }
    /**
     * @param {Object} markerInfo
     * @param {Number} latLongOffset
     */
    createMarkerPopup(markerInfo, latLongOffset = 0) {
        const popupData = this.getMarkerPopupData(markerInfo);
        const partner = this.getMarkerRecord(markerInfo).partner;
        const popupHtml = renderToString(this.constructor.markerPopupTemplate, {
            data: popupData,
            hasFormView: this.model.metaData.hasFormView,
            url: this.buildGoogleMapUrl({
                destination: partner.contact_address_complete,
            }),
        });

        const popup = L.popup({ offset: [0, -30] })
            .setLatLng([
                partner.partner_latitude + latLongOffset,
                partner.partner_longitude - latLongOffset,
            ])
            .setContent(popupHtml)
            .openOn(this.leafletMap);

        const openBtn = popup
            .getElement()
            .querySelector("button.o-map-renderer--popup-buttons-open");
        if (openBtn) {
            const openRecords = (ev) => {
                if (ev.button !== 0 && ev.button !== 1) {
                    return;
                }
                const ctrlKey = isCtrlOrCmdKey(ev);
                const inNewWindow = (ctrlKey && ev.button === 0) || ev.button === 1;
                this.props.onMarkerClick(markerInfo.ids, inNewWindow);
            };
            openBtn.onclick = openRecords;
            openBtn.onauxclick = openRecords;
        }
        return popup;
    }
    /**
     * @param {Number} groupId
     */
    getGroupColor(groupId) {
        const index = Object.keys(this.model.data.recordGroups).indexOf(groupId);
        return colors[index % colors.length];
    }
    /** @returns {Object[]} */
    getVisibleRecords() {
        if (!this.model.data.isGrouped) {
            return this.model.data.records;
        }
        return Object.entries(this.model.data.recordGroups)
            .filter(([key]) => !this.state.closedGroupIds.includes(key))
            .flatMap(([groupId, value]) =>
                value.records.map((elem) => ({ ...elem, groupId })),
            );
    }
    /** @returns {latLngBounds|false} */
    getVisibleBounds() {
        const tabLatLng = [];
        for (const record of this.getVisibleRecords()) {
            if (hasCoordinates(record.partner)) {
                tabLatLng.push(
                    L.latLng(
                        record.partner.partner_latitude,
                        record.partner.partner_longitude,
                    ),
                );
            }
        }
        if (!tabLatLng.length) {
            return false;
        }
        return L.latLngBounds(tabLatLng);
    }
    getMarkerPopupRecordData(record) {
        const fieldsView = [];
        if (!this.model.metaData.hideName) {
            fieldsView.push({
                id: this.nextId++,
                value: record.display_name,
                string: _t("Name"),
            });
        }
        if (!this.model.metaData.hideAddress) {
            fieldsView.push({
                id: this.nextId++,
                value: record.partner.contact_address_complete,
                string: _t("Address"),
            });
        }
        const fields = this.model.metaData.fields;
        for (const field of this.model.metaData.fieldNamesMarkerPopup) {
            if (record[field.fieldName]) {
                let value = record[field.fieldName];
                if (fields[field.fieldName].type === "many2one") {
                    value = record[field.fieldName].display_name;
                } else if (
                    ["one2many", "many2many"].includes(fields[field.fieldName].type)
                ) {
                    value = record[field.fieldName]
                        ? record[field.fieldName].map((r) => r.display_name).join(", ")
                        : "";
                }
                fieldsView.push({
                    id: this.nextId++,
                    value,
                    string: field.string || fields[field.fieldName].string,
                });
            }
        }
        return fieldsView;
    }
    /**
     * @param {Object} markerInfo
     * @returns {Object[]}
     */
    getMarkerPopupData(markerInfo) {
        const record = this.getMarkerRecord(markerInfo);
        if (markerInfo.ids.length > 1) {
            const fieldsView = [];
            if (!this.model.metaData.hideAddress) {
                fieldsView.push({
                    id: this.nextId++,
                    value: record.partner.contact_address_complete,
                    string: _t("Address"),
                });
            }
            return fieldsView;
        }
        return this.getMarkerPopupRecordData(record);
    }
    /** @returns {string[]} */
    getRouteAddresses() {
        const addresses = new Set();
        for (const { partner } of this.model.data.records) {
            if (partner?.contact_address_complete) {
                addresses.add(partner.contact_address_complete);
            }
        }
        return [...addresses];
    }
    /** @returns {Object} */
    get googleMapParams() {
        const addresses = this.getRouteAddresses();
        if (!addresses.length) {
            return {};
        }
        const params = { destination: addresses.pop() };
        if (addresses.length) {
            params.waypoints = this.joinWaypoints(addresses);
        }
        return params;
    }
    /**
     * @param {string[]} addresses
     * @returns {string}
     */
    joinWaypoints(addresses) {
        const limit = this.ui.isSmall
            ? GOOGLE_MAPS_MAX_WAYPOINTS_MOBILE
            : GOOGLE_MAPS_MAX_WAYPOINTS;
        return addresses.slice(0, limit).join("|");
    }
    /**
     * @returns {string}
     */
    get googleMapUrl() {
        return this.buildGoogleMapUrl(this.googleMapParams);
    }
    /**
     * @param {Object} params
     * @returns {string}
     */
    buildGoogleMapUrl(params) {
        const query = new URLSearchParams({ api: "1", ...params });
        return `https://www.google.com/maps/dir/?${query}`;
    }
    removeMarkers() {
        for (const marker of this.markers) {
            marker.off("click");
            this.leafletMap.removeLayer(marker);
        }
        this.markers = [];
    }
    removeRoutes() {
        for (const polyline of this.polylines) {
            polyline.off("click");
            this.leafletMap.removeLayer(polyline);
        }
        this.polylines = [];
    }
    updateMap() {
        if (this.groupedByKey !== this.model.data.groupByKey) {
            this.groupedByKey = this.model.data.groupByKey;
            this.state.closedGroupIds = [];
        }

        const bounds = this.getVisibleBounds();
        const boundsSignature = `${this.model.data.revision}|${bounds ? bounds.toBBoxString() : ""}`;
        if (
            this.model.data.shouldUpdatePosition &&
            this.fittedBoundsSignature !== boundsSignature
        ) {
            this.fittedBoundsSignature = boundsSignature;
            if (bounds) {
                this.leafletMap.flyToBounds(bounds, { animate: false });
            } else {
                this.leafletMap.fitWorld();
            }
            this.leafletMap.closePopup();
        }

        const markersInfos = this.getMarkersInfo();
        const markerSignature = this.getMarkerSignature(markersInfos);
        log.pipeline("updateMap", () => ({
            markers: markersInfos.length,
            markersChanged: this.renderedMarkerSignature !== markerSignature,
            boundsChanged: this.fittedBoundsSignature === boundsSignature,
        }));
        if (this.renderedMarkerSignature !== markerSignature) {
            this.renderedMarkerSignature = markerSignature;
            this.addMarkers();
        }
        this.addRoutes();
    }

    /** @param {Object} record */
    async centerAndOpenPin(record) {
        if (!this.isRecordLocated(record)) {
            return;
        }
        this.state.expandedPinList = false;
        await delay(0);
        const popup = this.createMarkerPopup({
            records: [record],
            ids: [record.id],
        });
        const px = this.leafletMap.project([
            record.partner.partner_latitude,
            record.partner.partner_longitude,
        ]);
        const popupHeight = popup.getElement().offsetHeight;
        px.y -= popupHeight / 2;
        const latlng = this.leafletMap.unproject(px);
        this.leafletMap.panTo(latlng, { animate: true });
    }
    /**
     * @param {Number} id
     */
    toggleGroup(id) {
        if (this.state.closedGroupIds.includes(id)) {
            const index = this.state.closedGroupIds.indexOf(id);
            this.state.closedGroupIds.splice(index, 1);
        } else {
            this.state.closedGroupIds.push(id);
        }
    }

    togglePinList() {
        this.state.expandedPinList = !this.state.expandedPinList;
    }

    get expandedPinList() {
        return this.ui.isSmall ? this.state.expandedPinList : false;
    }

    /** @returns {boolean} */
    /** @returns {boolean} */
    get displayNoContentHelper() {
        return Boolean(this.model.useSampleModel || !this.model.hasData());
    }

    get displayNoMapTokenAlert() {
        return this.model.metaData.routing && !this.model.data.useMapBoxAPI;
    }

    get canDisplayPinList() {
        return !this.ui.isSmall || this.expandedPinList;
    }
}
