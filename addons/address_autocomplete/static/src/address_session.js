/** @odoo-module native */
import { rpc } from "@web/core/network";

function makeAddressSession() {
    let current;

    /**
     * A lookup is one session: it begins with the first suggestions and ends
     * with the details of the address chosen, after which its token is spent
     * and the next lookup needs a fresh one. A provider bills the session as
     * one lookup (Google Places:
     * https://developers.google.com/maps/documentation/places/web-service/details#session_tokens).
     */
    function generateUUID() {
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            const r = (Math.random() * 16) | 0,
                v = c === "x" ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    function getAddressPropositions(params = {}) {
        if (!params.session_id) {
            current = current || generateUUID();
            params.session_id = current;
        }
        return rpc("/autocomplete/address", params);
    }

    async function getAddressDetails(params = {}) {
        if (!params.session_id) {
            current = current || generateUUID();
            params.session_id = current;
        }
        current = null;
        return rpc("/autocomplete/address_full", params);
    }

    return {
        get sessionToken() {
            return current;
        },
        getAddressPropositions,
        getAddressDetails,
    };
}

export const addressSession = makeAddressSession();
