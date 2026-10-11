// @ts-check
/** @odoo-module native */
import { IM_STATUS_DEBOUNCE_DELAY } from "@mail/core/common/constants";
import { baseImStatus } from "@mail/core/common/presence_status";
import { fields } from "@mail/core/common/record";
import { toRaw } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { now } from "@web/core/l10n/dates";
import { debounce } from "@web/core/utils/timing";

const log = makeLogger("mail.presence");
/** @type {WeakMap<object, ReturnType<typeof debounce<(newStatus: ImStatus) => void>>>} */
const debouncedSetImStatusByRecord = new WeakMap();

/**
 * @typedef {'offline' | 'bot' | 'online' | 'away' | 'im_partner' | undefined} ImStatus
 */

/**
 * @template {new (...args: any[]) => import("@mail/core/common/record").Record} T
 * @param {T} Base
 */
export const PresenceMixin = (Base) =>
    class extends Base {
        /** @type {string} */
        avatar_128_access_token;
        /** @returns {ReturnType<typeof debounce<(newStatus: ImStatus) => void>>} */
        get debouncedSetImStatus() {
            const record = toRaw(this)._raw;
            let debounced = debouncedSetImStatusByRecord.get(record);
            if (!debounced) {
                debounced = debounce(
                    /** @param {ImStatus} newStatus */
                    (newStatus) => record._proxy.updateImStatus(newStatus),
                    IM_STATUS_DEBOUNCE_DELAY,
                );
                debouncedSetImStatusByRecord.set(record, debounced);
            }
            return debounced;
        }
        /** @type {number} */
        id;
        /** @type {ImStatus} */
        im_status = fields.Attr(null, {
            /** @this {import("models").Persona} */
            onUpdate() {
                if (baseImStatus(this.im_status) === "offline" && this.isSelfPresence) {
                    this.store.env.services.im_status.updateBusPresence();
                }
            },
        });
        /** @type {string|undefined} */
        im_status_access_token;
        monitorPresence = fields.Attr(false, {
            /** @this {import("models").Persona} */
            compute() {
                return this.computeMonitorPresence();
            },
        });
        /** @type {Temporal.ZonedDateTime} */
        offline_since = fields.Datetime();
        presenceChannel = fields.Attr(null, {
            /** @this {import("models").Persona} */
            compute() {
                const channel = `odoo-presence-${this.Model.getName()}_${this.id}`;
                return this.im_status_access_token
                    ? `${channel}-${this.im_status_access_token}`
                    : channel;
            },
        });
        /** @type {(() => void)|undefined} */
        releasePresenceChannel;
        _triggerPresenceSubscription = fields.Attr(null, {
            /** @this {import("models").Persona} */
            compute() {
                return this.monitorPresence && this.presenceChannel;
            },
            /** @this {import("models").Persona} */
            onUpdate() {
                this.releasePresenceChannel?.();
                this.releasePresenceChannel = this._triggerPresenceSubscription
                    ? this.store.env.services.bus_service.addChannel(
                          this.presenceChannel,
                      )
                    : undefined;
            },
        });
        write_date = fields.Datetime();

        /** @returns {boolean} */
        computeMonitorPresence() {
            return this.store.env.services.bus_service.isActive && this.id > 0;
        }

        /** @returns {boolean} */
        get isSelfPresence() {
            return false;
        }

        /** @returns {{access_token?: string}} */
        get avatarAccessTokenParam() {
            if (this.store.selfIsInternalUser) {
                return {};
            }
            return { access_token: this.avatar_128_access_token };
        }

        delete() {
            debouncedSetImStatusByRecord.get(toRaw(this)._raw)?.cancel();
            super.delete();
        }

        /** @param {ImStatus} newStatus */
        updateImStatus(newStatus) {
            log.pipeline("updateImStatus", () => ({
                model: this.Model.getName(),
                id: this.id,
                from: this.im_status,
                to: newStatus,
            }));
            if (baseImStatus(newStatus) === "offline") {
                this.offline_since = now();
            }
            this.im_status = newStatus;
        }
    };
