/** @odoo-module native */
import { LocationSchedule } from "@delivery/js/location_selector/location_schedule/location_schedule";
import { Map } from "@delivery/js/location_selector/map/map";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { AssetsLoadingError } from "@web/core/assets";
import { loadLeaflet } from "@web/core/lib/leaflet";
import { _t } from "@web/core/translation";

export class MapContainer extends Component {
    static components = { LocationSchedule, Map };
    static template = "delivery.locationSelector.mapContainer";
    static props = {
        locations: t.array(t.record(t.any())),
        selectedLocationId: t.or([t.string(), t.literal(false)]),
        setSelectedLocation: t.function(),
        validateSelection: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ mapStatus: "loading" });
        loadLeaflet().then(
            () => {
                this.state.mapStatus = "loaded";
            },
            (error) => {
                if (
                    !(error instanceof AssetsLoadingError || error instanceof TypeError)
                ) {
                    throw error;
                }
                this.state.mapStatus = "failed";
            },
        );
    }

    /**
     * Get the city and the zip code.
     *
     * @param {Number} selectedLocation - The location form which the city and the zip code
     *                                    should be taken.
     * @return {Object} The city and the zip code.
     */
    getCityAndZipCode(selectedLocation) {
        return `${selectedLocation.zip_code} ${selectedLocation.city}`;
    }

    /**
     * Find the selected location based on its id.
     *
     * @return {Object} The selected location.
     */
    get selectedLocation() {
        return this.props.locations.find(
            (l) => String(l.id) === this.props.selectedLocationId,
        );
    }

    get errorMessage() {
        return _t("There was an error loading the map");
    }

    get chooseLocationButtonLabel() {
        return _t("Choose this location");
    }

    get openingHoursLabel() {
        return _t("Opening hours");
    }
}
