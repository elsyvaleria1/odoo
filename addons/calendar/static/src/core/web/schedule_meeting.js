/** @odoo-module native */

/** @param {import("@web/env").OdooEnv} env */
export async function openScheduleMeeting(env) {
    const videocallLocation = await env.services.orm.call(
        "calendar.event",
        "get_discuss_videocall_location",
    );
    await env.services.action.doAction("calendar.action_calendar_event", {
        additionalContext: {
            default_access_token: videocallLocation.split("/").pop(),
            default_videocall_location: videocallLocation,
            return_to_parent_breadcrumb: true,
        },
    });
}
