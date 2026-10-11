/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

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
