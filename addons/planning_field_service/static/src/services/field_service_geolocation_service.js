/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

/**
 * Where the phone is, read once when a visit is started or completed.
 *
 * Upstream master also watches the position continuously for a live map; this
 * port keeps the one-off reading only, as the vehicle's GPS already tracks the
 * route and a browser tab cannot be relied on to stay open.
 */
export class FieldServiceGeolocationService {
    async isFeatureEnabled() {
        const [isGeolocationEnabled, isPlanningUser] = await Promise.all([
            user.hasGroup("planning.group_field_service_allow_geolocation"),
            user.hasGroup("planning.group_planning_user"),
        ]);
        return isGeolocationEnabled && isPlanningUser;
    }

    _getPosition() {
        return new Promise((resolve, reject) => {
            // Without a timeout a phone with no fix never answers, and Start or
            // Complete would wait forever without a word.
            navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 60000,
            });
        });
    }

    /**
     * @returns {Promise<false|{success: boolean, latitude?: number, longitude?: number, message?: string}>}
     */
    async getGeolocation() {
        if (!(await this.isFeatureEnabled())) {
            return false;
        }
        if (!navigator.geolocation) {
            return {
                success: false,
                message: _t("This device cannot give its location."),
            };
        }
        try {
            const position = await this._getPosition();
            return {
                success: true,
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
            };
        } catch (error) {
            return { success: false, message: _t("Location error: %s", error.message) };
        }
    }
}

export const fieldServiceGeolocationService = {
    start() {
        return new FieldServiceGeolocationService();
    },
};

registry
    .category("services")
    .add("field_service_geolocation", fieldServiceGeolocationService);
