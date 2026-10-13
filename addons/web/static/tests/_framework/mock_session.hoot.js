// @ts-check

const moduleScope = new URLSearchParams(location.search).get("module_scope");

/** @type {Map<string, boolean>} */
const sessionGroups = new Map([["base.group_allow_export", true]]);

/** @param {Record<string, boolean>} groups */
export function registerSessionGroups(groups) {
    for (const [group, value] of Object.entries(groups)) {
        sessionGroups.set(group, value);
    }
}

/** @type {Record<string, unknown>} */
const sessionExtensions = {};

/** @param {Record<string, unknown>} extension */
export function registerSessionInfo(extension) {
    Object.assign(sessionExtensions, extension);
}

/** @param {import("./mock_server_state.hoot.js").ServerState} serverState */
export const makeSession = ({
    companies,
    db,
    disallowedAncestorCompanies,
    lang,
    partnerId,
    partnerName,
    serverVersion,
    timezone,
    userContext,
    userId,
    view_info,
}) => ({
    active_ids_limit: 20000,
    bundle_params: {
        debug: new URLSearchParams(location.search).get("debug"),
        lang,
        ...(moduleScope ? { module_scope: moduleScope } : {}),
    },
    can_insert_in_spreadsheet: false,
    db,
    registry_hash: "05500d71e084497829aa807e3caa2e7e9782ff702c15b2f57f87f2d64d049bd0",
    menus_cache_version: `05500d71e084497829aa807e3caa2e7e9782ff702c15b2f57f87f2d64d049bd0:${userId}`,
    groups: Object.fromEntries(sessionGroups),
    home_action_id: false,
    home_tints: [
        { name: "blue", label: "Blue" },
        { name: "teal", label: "Teal" },
        { name: "green", label: "Green" },
        { name: "amber", label: "Amber" },
        { name: "rose", label: "Rose" },
        { name: "violet", label: "Violet" },
        { name: "graphite", label: "Graphite" },
    ],
    is_admin: true,
    is_internal_user: true,
    is_system: true,
    max_file_upload_size: 134217728,
    name: partnerName,
    partner_display_name: partnerName,
    partner_id: partnerId,
    profile_collectors: null,
    profile_params: null,
    profile_session: null,
    server_version: serverVersion.slice(0, 2).join("."),
    server_version_info: serverVersion,
    show_effect: true,
    uid: userId,
    user_companies: {
        allowed_companies: Object.fromEntries(
            companies.map((company) => [company.id, company]),
        ),
        current_company: companies[0]?.id,
        disallowed_ancestor_companies: Object.fromEntries(
            (disallowedAncestorCompanies || []).map((company) => [company.id, company]),
        ),
    },
    user_context: {
        ...userContext,
        lang,
        tz: timezone,
        uid: userId,
    },
    user_id: [userId],
    username: "admin",
    ["web.base.url"]: "http://localhost:8069",
    view_info,
    ...sessionExtensions,
});
