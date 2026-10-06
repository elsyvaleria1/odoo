// @ts-check

import { after, before, beforeEach, createJobScopedGetter } from "@odoo/hoot";
import { assertType, t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { dateSettings } from "@web/core/l10n/date_settings";

const { view_info } = /** @type {any} */ (odoo).__session_info__ || {};

const log = makeLogger("web.tests.server_state");

/** @typedef {typeof SERVER_STATE_VALUES} ServerState */

const applyDefaults = () => {
    Object.assign(dateSettings, DEFAULT_DATE_SETTINGS);

    notifySubscribers({ reset: true });
};

/** @type {WeakMap<object, string[]>} */
const definedKeys = new WeakMap();

/** @type {WeakMap<object, PropertyDescriptorMap>} */
const pristineDescriptors = new WeakMap();

/** @param {PropertyDescriptor} descriptor */
function copyDescriptor(descriptor) {
    if (!("value" in descriptor)) {
        return descriptor;
    }
    try {
        return { ...descriptor, value: structuredClone(descriptor.value) };
    } catch {
        return descriptor;
    }
}

/**
 * @param {object} target
 * @param {PropertyDescriptorMap} descriptors
 * @param {PropertyDescriptorMap} pristine
 */
function restorePristine(target, descriptors, pristine) {
    const runtimeKeys = Object.keys(target).filter(
        (key) => !(key in descriptors) && !(key in pristine),
    );
    const restoredKeys = Object.keys(pristine).filter((key) => !(key in descriptors));
    log.logic("reset", () => ({
        runtimeKeys: runtimeKeys.join(","),
        restoredKeys: restoredKeys.join(","),
    }));
    for (const key of runtimeKeys) {
        delete (/** @type {any} */ (target)[key]);
    }
    for (const key of restoredKeys) {
        Object.defineProperty(target, key, copyDescriptor(pristine[key]));
    }
}

/** @param {{ reset?: boolean }} [options] */
const notifySubscribers = ({ reset = false } = {}) => {
    for (const [target, callback] of subscriptions) {
        const descriptors = Object.getOwnPropertyDescriptors(callback(serverState));
        const pristine = reset && pristineDescriptors.get(target);
        if (pristine) {
            restorePristine(target, descriptors, pristine);
        } else {
            const staleKeys = (definedKeys.get(target) || []).filter(
                (key) => !(key in descriptors),
            );
            log.logic("notify", () => ({
                keys: Object.keys(descriptors).length,
                staleKeys,
            }));
            for (const key of staleKeys) {
                delete target[key];
            }
        }
        Object.defineProperties(target, descriptors);
        definedKeys.set(target, Object.keys(descriptors));
    }
};

const DEFAULT_DATE_SETTINGS = { ...dateSettings };
const SERVER_STATE_VALUES = {
    /** @type {{ id: number; name: string; currency_id?: number; [key: string]: any }[]} */
    companies: [
        {
            id: 1,
            name: "Hermit",
            currency_id: 1,
        },
    ],
    /** @type {{ id: number; name: string; [key: string]: any }[]} */
    disallowedAncestorCompanies: [],
    /** @type {{ id: number; name: string; position: string; symbol: string; [key: string]: any }[]} */
    currencies: [
        {
            id: 1,
            name: "USD",
            position: "before",
            symbol: "$",
        },
        {
            id: 2,
            name: "EUR",
            position: "after",
            symbol: "€",
        },
    ],
    db: "test",
    debug: "",
    groupId: 11,
    lang: "en",
    multiLang: false,
    odoobotId: 418,
    odoobotUid: 518,
    partnerId: 17,
    partnerName: "Mitchell Admin",
    publicPartnerId: 18,
    publicPartnerName: "Public user",
    publicUserId: 8,
    serverVersion: [1, 0, 0, "final", 0, ""],
    timezone: "taht",
    userContext: {},
    userId: 7,
    view_info,
};

const SERVER_STATE_VALUES_SCHEMA = {
    companies: t.array(t.object()),
    currencies: t.array(t.object()),
    db: t.string(),
    disallowedAncestorCompanies: t.array(t.object()),
    debug: t.string(),
    groupId: t.or([t.number(), t.literal(false)]),
    lang: t.string(),
    multiLang: t.boolean(),
    odoobotId: t.or([t.number(), t.literal(false)]),
    partnerId: t.or([t.number(), t.literal(false)]),
    partnerName: t.string(),
    publicPartnerId: t.or([t.number(), t.literal(false)]),
    publicPartnerName: t.string(),
    publicUserId: t.number(),
    serverVersion: t.array(t.or([t.string(), t.number()])),
    timezone: t.string(),
    userContext: t.object(),
    userId: t.or([t.number(), t.literal(false)]),
    view_info: t.object(),
};

const getServerStateValues = createJobScopedGetter(
    (previousValues) =>
        JSON.parse(JSON.stringify({ ...SERVER_STATE_VALUES, ...previousValues })),
    applyDefaults,
);

/** @type {Map<any, (state: ServerState) => any>} */
const subscriptions = new Map([
    [
        odoo,
        ({ db, debug, serverVersion }) => ({
            ...odoo,
            debug,
            info: {
                db,
                server_version: serverVersion.slice(0, 2).join("."),
                server_version_info: serverVersion,
                isEnterprise: serverVersion.slice(-1)[0] === "e",
            },
            isReady: true,
        }),
    ],
]);

/**
 * With `pristine`, every test starts from the target as it was before any
 * test ran, plus the callback's keys: a key code assigned at runtime is gone.
 *
 * @template T
 * @param {T} target
 * @param {(state: ServerState) => T} callback
 * @param {{ pristine?: boolean }} [options]
 */
export function onServerStateChange(target, callback, { pristine = false } = {}) {
    if (pristine && !pristineDescriptors.has(/** @type {object} */ (target))) {
        const descriptors = Object.entries(Object.getOwnPropertyDescriptors(target));
        pristineDescriptors.set(
            /** @type {object} */ (target),
            Object.fromEntries(
                descriptors.map(([key, descriptor]) => [
                    key,
                    copyDescriptor(descriptor),
                ]),
            ),
        );
    }
    /** @type {(((state: ServerState) => any) | undefined)[]} */
    const shadowed = [];
    before((job) => {
        log.logic("subscribe", () => ({
            job: job?.fullName,
            shadows: subscriptions.has(target),
        }));
        shadowed.push(subscriptions.get(target));
        subscriptions.set(target, callback);
    });
    after((job) => {
        const previous = shadowed.pop();
        log.logic("unsubscribe", () => ({
            job: job?.fullName,
            restores: Boolean(previous),
        }));
        if (previous) {
            subscriptions.set(target, previous);
        } else {
            subscriptions.delete(target);
        }
    });
}

export const serverState = new Proxy(SERVER_STATE_VALUES, {
    deleteProperty(_target, p) {
        // @ts-ignore — createJobScopedGetter return type inference
        return Reflect.deleteProperty(getServerStateValues(), p);
    },
    get(_target, p) {
        // @ts-ignore — createJobScopedGetter return type inference
        return Reflect.get(getServerStateValues(), p);
    },
    has(_target, p) {
        // @ts-ignore — createJobScopedGetter return type inference
        return Reflect.has(getServerStateValues(), p);
    },
    set(_target, p, newValue) {
        if (
            /** @type {any} */ (p) in SERVER_STATE_VALUES_SCHEMA &&
            newValue !== null &&
            newValue !== undefined
        ) {
            assertType(
                newValue,
                /** @type {any} */ (SERVER_STATE_VALUES_SCHEMA)[p],
                `invalid server state "${String(p)}"`,
            );
        }
        // @ts-ignore — createJobScopedGetter return type inference
        const result = Reflect.set(getServerStateValues(), p, newValue);
        if (result) {
            notifySubscribers();
        }
        return result;
    },
});

beforeEach(applyDefaults, /** @type {any} */ ({ global: true }));
