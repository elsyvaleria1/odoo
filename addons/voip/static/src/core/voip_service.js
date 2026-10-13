/** @odoo-module native */
import { EventBus, proxy } from "@odoo/owl";
import { CallMethodSelectionDialog } from "@voip/mobile/call_method_selection_dialog";
import { SoftphoneContainer } from "@voip/softphone/softphone_container";
import { Softphone } from "@voip/softphone/softphone_model";
import { cleanPhoneNumber } from "@voip/utils/utils";
import { VoipSystrayItem } from "@voip/web/voip_systray_item";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Deferred } from "@web/core/utils/concurrency";

export class Voip {
    bus = new EventBus();
    callActivityTypeId;
    error;
    isUnloading = false;
    /** @type {"demo"|"prod"} */
    mode;
    /** @type {string} */
    pbxAddress;
    /** @type {"always"|"user"|"disabled"} */
    recordingPolicy;
    /** @type {Softphone} */
    softphone;
    /** @type {string} */
    webSocketUrl;

    constructor(env, services) {
        this.env = env;
        /** @type {import("@mail/core/common/store_service").Store} */
        this.store = services["mail.store"];
        this.callService = services["voip.call"];
        this.dialog = services.dialog;
        this.orm = services.orm;
        this.busService = services.bus_service;
        this.softphone = new Softphone(this.store, this);
        this.callService.missedCalls = this.store.voipConfig?.missedCalls ?? 0;
        delete this.store.voipConfig?.missedCalls;
        Object.assign(this, this.store.voipConfig);
        delete this.store.voipConfig;
        this.busService.subscribe("remove_call_activity", (payload) => {
            const activity = this.store["mail.activity"].insert(payload);
            activity.remove();
        });
        this.busService.subscribe("refresh_call_activities", () => {
            this.fetchTodayCallActivities();
        });
        this.busService.subscribe("phone.call/delete", (payload) => {
            for (const id of payload.ids) {
                this.store["phone.call"].get(id)?.delete();
            }
        });
        window.addEventListener("beforeunload", this._onBeforeUnload.bind(this));
        return proxy(this);
    }

    /** @returns {boolean} */
    get areCredentialsSet() {
        return Boolean(
            this.store.settings.voip_username && this.store.settings.voip_secret,
        );
    }

    /** @returns {string} */
    get authorizationUsername() {
        return this.store.settings.voip_username || "";
    }

    get calls() {
        return this.store["phone.call"].records;
    }

    /** @returns {boolean} */
    get canCall() {
        return (
            this.mode === "demo" ||
            (this.hasRtcSupport && this.isServerConfigured && this.areCredentialsSet)
        );
    }

    /** @returns {boolean} */
    get hasPendingRequest() {
        return Boolean(this._activityRpc || this._contactRpc || this._recentCallsRpc);
    }

    /** @returns {boolean} */
    get hasRtcSupport() {
        return Boolean(
            window.RTCPeerConnection && window.MediaStream && navigator.mediaDevices,
        );
    }

    /** @returns {boolean} */
    get hasValidExternalDeviceNumber() {
        if (!this.store.settings.external_device_number) {
            return false;
        }
        return cleanPhoneNumber(this.store.settings.external_device_number) !== "";
    }

    /** @returns {boolean} */
    get isServerConfigured() {
        return Boolean(this.pbxAddress && this.webSocketUrl);
    }

    /** @returns {number} */
    get missedCalls() {
        return this.callService.missedCalls;
    }

    /** @returns {boolean} */
    get willCallFromAnotherDevice() {
        return (
            this.store.settings.should_call_from_another_device &&
            this.hasValidExternalDeviceNumber
        );
    }

    async fetchContacts(searchTerms = "", offset = 0, limit = 13, t9Search = false) {
        if (this._contactRpc) {
            this._contactRpc.abort();
        }
        this._contactRpc = this.orm.call("res.partner", "get_contacts", [], {
            offset,
            limit,
            search_terms: searchTerms.trim(),
            t9_search: t9Search,
        });
        try {
            const data = await this._contactRpc;
            this.store.insert(data);
            this._contactRpc = null;
        } catch (error) {
            if (error.event?.type === "abort") {
                error.event.preventDefault();
                return;
            }
            if (error.message?.toLowerCase().includes("abort")) {
                return;
            }
            this._contactRpc = null;
            console.error(error);
        }
    }

    async fetchRecentCalls(searchTerms = "", offset = 0, limit = 13) {
        if (this._recentCallsRpc) {
            this._recentCallsRpc.abort();
        }
        this._recentCallsRpc = this.orm.call(
            "phone.call",
            "get_recent_phone_calls",
            [],
            {
                offset,
                limit,
                search_terms: searchTerms.trim(),
            },
        );
        try {
            const data = await this._recentCallsRpc;
            this.store.insert(data);
            this._recentCallsRpc = null;
        } catch (error) {
            if (error.event?.type === "abort") {
                error.event.preventDefault();
                return;
            }
            if (error.message?.toLowerCase().includes("abort")) {
                return;
            }
            this._recentCallsRpc = null;
            console.error(error);
        }
    }

    async fetchTodayCallActivities() {
        if (this._activityRpc) {
            return;
        }
        this._activityRpc = this.orm.call("mail.activity", "get_today_call_activities");
        try {
            const data = await this._activityRpc;
            this.store.insert(data);
        } finally {
            this._activityRpc = null;
        }
    }

    resetMissedCalls() {
        if (this.missedCalls !== 0) {
            this.orm.call("res.users", "reset_last_seen_phone_call");
        }
        this.callService.missedCalls = 0;
    }

    resolveError() {
        this.error = null;
    }

    /**
     * @param {string} message
     * @param {Object} [options={}]
     * @param {boolean} [options.isNonBlocking=false]
     */
    triggerError(message, { isNonBlocking = false, title, button } = {}) {
        this.error = { title, text: message, isNonBlocking, button };
    }

    /** @returns {Deferred<boolean>} */
    async willCallUsingVoip() {
        if (!isMobileOS()) {
            return true;
        }
        const callMethod = this.store.settings.how_to_call_on_mobile;
        if (callMethod !== "ask") {
            return callMethod === "voip";
        }
        const useVoip = new Deferred();
        this.dialog.add(
            CallMethodSelectionDialog,
            { useVoip },
            { onClose: () => useVoip.resolve(true) },
        );
        return useVoip;
    }

    /**
     * @param {BeforeUnloadEvent} ev
     * @returns {string|undefined}
     */
    _onBeforeUnload(ev) {
        if (!this.env.services["voip.user_agent"]?.activeSession?.call.isInProgress) {
            return;
        }
        ev.preventDefault();
        return (ev.returnValue = _t(
            "There is still a call in progress, are you sure you want to leave the page?",
        ));
    }

    fakeIncoming() {
        const fakeInvitation = {
            remoteIdentity: {
                uri: {
                    user: "+1 555-555-5555",
                },
            },
            incomingInviteRequest: {},
            stateChange: {
                addListener() {},
            },
        };
        this.env.services["voip.user_agent"]._onIncomingInvitation(fakeInvitation);
    }
}

export const voipService = {
    dependencies: ["bus_service", "dialog", "mail.store", "orm", "voip.call"],
    async start() {
        const isEmployee = await user.hasGroup("base.group_user");
        if (!isEmployee) {
            return {
                bus: new EventBus(),
                get canCall() {
                    return false;
                },
            };
        }
        registry.category("main_components").add("voip.SoftphoneContainer", {
            Component: SoftphoneContainer,
        });
        registry.category("systray").add("voip", { Component: VoipSystrayItem });
        return new Voip(...arguments);
    },
};

registry.category("services").add("voip", voipService);
