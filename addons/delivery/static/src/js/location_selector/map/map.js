/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { L } from "@web/core/lib/leaflet";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { renderToString } from "@web/core/utils/render";

export class Map extends Component {
    static template = "delivery.locationSelector.map";
    static props = {
        locations: t.array(t.record(t.any())),
        selectedLocationId: t.or([t.string(), t.literal(false)]),
        setSelectedLocation: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.leafletMap = null;
        this.markers = [];
        this.mapRef = elementRef();

        useLayoutEffect(
            () => {
                this.leafletMap = L.map(this.mapRef.el, {
                    zoom: 13,
                });
                this.leafletMap.attributionControl.setPrefix(
                    '<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">Leaflet</a>',
                );
                L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 19,
                    attribution:
                        "&copy; <a href='http://www.openstreetmap.org/copyright'>OpenStreetMap</a>",
                }).addTo(this.leafletMap);
                return () => {
                    this.leafletMap.remove();
                };
            },
            () => [],
        );

        useLayoutEffect(
            () => {
                this.leafletMap.invalidateSize();
            },
            () => [this.props.locations],
        );

        useLayoutEffect(
            (locations, selectedLocationId) => {
                this.addMarkers(locations);
                const selectedLocation = locations.find(
                    (l) => String(l.id) === selectedLocationId,
                );
                if (selectedLocation) {
                    this.leafletMap.panTo(
                        [selectedLocation.latitude, selectedLocation.longitude],
                        { animate: true },
                    );
                }
                return () => {
                    this.removeMarkers();
                };
            },
            () => [this.props.locations, this.props.selectedLocationId],
        );
    }

    /**
     * @param {Array} locations
     * @return {void}
     */
    addMarkers(locations) {
        for (const loc of locations) {
            const isSelected = String(loc.id) === this.props.selectedLocationId;
            const iconInfo = {
                className: isSelected
                    ? "o_location_selector_marker_icon_selected"
                    : "o_location_selector_marker_icon",
                html: renderToString("delivery.locationSelector.map.marker", {
                    number: locations.indexOf(loc) + 1,
                }),
                iconSize: [30, 40],
                iconAnchor: [15, 40],
            };

            const marker = L.marker([loc.latitude, loc.longitude], {
                icon: L.divIcon(iconInfo),
                title: locations.indexOf(loc) + 1,
            });

            if (isSelected) {
                marker.setZIndexOffset(100);
            }

            marker.addTo(this.leafletMap);
            marker.addEventListener("click", () => {
                this.props.setSelectedLocation(loc.id);
            });

            this.markers.push(marker);
        }
    }

    /** @return {void} */
    removeMarkers() {
        for (const marker of this.markers) {
            marker.removeEventListener();
            this.leafletMap.removeLayer(marker);
        }
        this.markers = [];
    }

    /** @return {Object} */
    get selectedLocation() {
        return this.props.locations.find(
            (l) => String(l.id) === this.props.selectedLocationId,
        );
    }
}
