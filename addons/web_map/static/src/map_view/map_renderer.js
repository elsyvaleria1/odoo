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

// "The number of waypoints allowed varies by the platform where the link opens,
// with up to three waypoints supported on mobile browsers, and a maximum of
// nine waypoints supported otherwise."
// -- developers.google.com/maps/documentation/urls/get-started
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
        // Subscribe to the model instead of reading it off the raw prop, so a
        // `notify()` re-renders this component on its own. Previously only the
        // controller's blanket deep render refreshed the map.
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
        // What the map is currently showing, so an unrelated re-render neither
        // rebuilds every marker nor throws the user's pan/zoom away.
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
        // Leaflet draws outside the template: the effect reads what it draws,
        // so a geocoded partner or a new route redraws the map
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
    /**
     * Remove map and the listeners on its markers and routes.
     */
    onWillUnmount() {
        this.removeMarkers();
        this.removeRoutes();
        if (this.leafletMap) {
            this.leafletMap.remove();
        }
    }

    /**
     * Return the route to the tiles api with or without access token.
     *
     * @returns {string}
     */
    get apiTilesRoute() {
        return this.model.data.useMapBoxAPI
            ? apiTilesRouteWithToken
            : apiTilesRouteWithoutToken;
    }

    /**
     * Groups the visible records by the point they sit on.
     *
     * `records` keeps the load order, so `records[0]` is the record whose
     * number and popup stand for the whole cluster and the pin list agrees
     * with the marker.
     *
     * @returns {Object[]}
     */
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
     * Whether `record`'s partner is placed on the map. Read by the pin list,
     * which must show exactly the records the markers do.
     *
     * @param {Object} record
     * @returns {boolean}
     */
    isRecordLocated(record) {
        return hasCoordinates(record.partner);
    }

    /**
     * The classes a pin-list entry carries.
     *
     * A method rather than a `t-att-class` expression: an inheriting view that
     * marks some records out -- an unplanned task, say -- composes with this
     * instead of xpath-ing a second class binding onto the same element, which
     * would collide with this one.
     *
     * @param {Object} record
     * @returns {string}
     */
    getPinListItemClass(record) {
        return this.isRecordLocated(record)
            ? "cursor-pointer o-map-renderer--pin-located"
            : "text-muted";
    }

    /**
     * The position `record` holds in the numbered route drawn over `records`.
     *
     * Counted over the *located* records only, because those are the ones the
     * map draws and the ones `_fetchRoute` sends: numbering over every record
     * instead made the pin list start at 2 whenever the first record had no
     * position, and made a marker's number name a route leg that was not its
     * own.
     *
     * @param {Object} record
     * @param {Object[]} records the list the numbering runs over -- every
     *      record when ungrouped, the group's records when grouped
     * @returns {number} 1-based, or 0 when `record` is not located
     */
    getPinNumber(record, records) {
        return (
            records
                .filter((candidate) => this.isRecordLocated(candidate))
                .findIndex((candidate) => candidate.id === record.id) + 1
        );
    }

    /**
     * The record standing for a cluster: its popup, its number, its position.
     *
     * @param {Object} markerInfo
     * @returns {Object}
     */
    getMarkerRecord(markerInfo) {
        return markerInfo.records[0];
    }

    /**
     * The number the marker standing for `markerInfo` shows.
     *
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
     * A cheap description of everything addMarkers() reads, so the Leaflet
     * layers are only torn down and rebuilt when one of them moved.
     *
     * @param {Object[]} markersInfos
     * @returns {string}
     */
    getMarkerSignature(markersInfos) {
        return JSON.stringify([
            // A load that returns the same ids at the same coordinates still
            // replaces every record object, and the markers' click handlers
            // close over the ones they were built from.
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

    /**
     * If there's located records, adds the corresponding marker on the map.
     * Binds events to the created markers.
     */
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

            // Icon creation
            const iconInfo = {
                className: "o-map-renderer--marker",
                html: renderToString("web_map.marker", params),
            };

            const offset = markerInfo.pinInSamePlace * 0.000025;
            // Attach marker with icon and popup
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
    /**
     * If there are computed routes, create polylines and add them to the map.
     * each element of this.model.data.routes[0].legs array represent the route between
     * two waypoints thus each of these must be a polyline.
     */
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
     * Create a popup for the specified marker.
     *
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
    /**
     * Returns the records that are actually shown on the map: every record
     * when the view isn't grouped, or only the records of the currently
     * expanded groups otherwise. Shared by addMarkers() and getVisibleBounds()
     * so the fitted viewport can never diverge from what is actually rendered.
     *
     * @returns {Object[]}
     */
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
    /**
     * The bounds holding every visible marker.
     *
     * @returns {latLngBounds|false} false when no visible record is located.
     */
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
                    // `string` is optional on a map field, and an inheriting
                    // view adding one rarely spells it: fall back to the
                    // field's own label rather than an empty popup row.
                    string: field.string || fields[field.fieldName].string,
                });
            }
        }
        return fieldsView;
    }
    /**
     * Get the fields' name and value to display in the popup.
     *
     * @param {Object} markerInfo
     * @returns {Object[]} value contains the value of the field and string
     *                   contains the value of the xml's string attribute
     */
    getMarkerPopupData(markerInfo) {
        const record = this.getMarkerRecord(markerInfo);
        // Only display address in multi coordinates marker popup
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
    /**
     * The addresses to route through, deduplicated and in load order.
     *
     * @returns {string[]}
     */
    getRouteAddresses() {
        const addresses = new Set();
        for (const { partner } of this.model.data.records) {
            if (partner?.contact_address_complete) {
                addresses.add(partner.contact_address_complete);
            }
        }
        return [...addresses];
    }
    /**
     * The Google Maps directions parameters, as an overridable object rather
     * than a half-built string: a subclass routing from a fixed origin sets
     * `origin` instead of appending a second `destination` to the query.
     *
     * @returns {Object}
     */
    get googleMapParams() {
        const addresses = this.getRouteAddresses();
        if (!addresses.length) {
            return {};
        }
        // Without a destination the link opens a blank destination form
        // rather than a route, so the last address is always the destination,
        // routing enabled or not.
        const params = { destination: addresses.pop() };
        if (addresses.length) {
            params.waypoints = this.joinWaypoints(addresses);
        }
        return params;
    }
    /**
     * Join `addresses` into a `waypoints` value, capped at what the platform
     * the link opens on will accept.
     *
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
    /**
     * Remove the markers from the map and empty the markers array.
     */
    removeMarkers() {
        for (const marker of this.markers) {
            marker.off("click");
            this.leafletMap.removeLayer(marker);
        }
        this.markers = [];
    }
    /**
     * Remove the routes from the map and empty the the polyline array.
     */
    removeRoutes() {
        for (const polyline of this.polylines) {
            polyline.off("click");
            this.leafletMap.removeLayer(polyline);
        }
        this.polylines = [];
    }
    /**
     * Update position in the map, markers and routes.
     *
     * Runs after every render, so each step first asks whether what it draws
     * has actually moved: refitting unconditionally threw away the user's
     * pan/zoom and closed the popup they had just opened, and rebuilding the
     * markers unconditionally re-rendered every icon.
     */
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

    /**
     * Center the map on a certain pin and open the popup linked to it.
     *
     * @param {Object} record
     */
    async centerAndOpenPin(record) {
        if (!this.isRecordLocated(record)) {
            return;
        }
        this.state.expandedPinList = false;
        // wait the next owl render to avoid marker popup create => destroy
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

    /**
     * Whether to invite the user to set a MapBox token.
     *
     * A getter rather than an inline template condition: an inheriting view
     * that shows the invitation to some users only narrows this instead of
     * xpath-ing on the condition's source text.
     *
     * @returns {boolean}
     */
    /**
     * Whether the pin list gives way to the no-content help the chassis draws.
     *
     * The map itself stays: it is still a map, and under sample data it is
     * showing sampled pins the helper is explaining.
     *
     * @returns {boolean}
     */
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
