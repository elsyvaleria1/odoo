/** @odoo-module native */
import { Location } from "@delivery/js/location_selector/location/location";
import { Component, onMounted, t, useProps } from "@odoo/owl";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class LocationList extends Component {
    static components = { Location };
    static template = "delivery.locationSelector.locationList";
    static props = {
        locations: t.array(t.record(t.any())),
        selectedLocationId: t.or([t.string(), t.literal(false)]),
        setSelectedLocation: t.function(),
        validateSelection: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        onMounted(() => {
            document
                .getElementById(`location-${this.props.selectedLocationId}`)
                ?.focus();
        });

        // Focus on the location on the list when clicking on the map marker.
        useLayoutEffect(
            (locations, selectedLocationId) => {
                const selectedLocation = locations.find(
                    (l) => String(l.id) === selectedLocationId,
                );
                if (selectedLocation) {
                    document.getElementById(`location-${selectedLocation.id}`).focus();
                }
            },
            () => [this.props.locations, this.props.selectedLocationId],
        );
    }
}
