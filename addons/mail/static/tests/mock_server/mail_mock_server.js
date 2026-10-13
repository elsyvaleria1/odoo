// @ts-check
import { markup } from "@odoo/owl";
import {
    authenticate,
    getKwArgs,
    logout,
    makeKwArgs,
    MockServer,
    MockServerError,
    models,
    onRpc,
    serverState,
    unmakeKwArgs,
} from "@web/../tests/web_test_helpers";
import { now, parseISO, serializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { groupBy } from "@web/core/utils/collections/arrays";
import { createDocumentFragmentFromContent } from "@web/core/utils/dom/html";

import { messagingMenuHelpers } from "./messaging_menu_mock_server.js";

const mockRpcRegistry = registry.category("mail.mock_rpc");
export const DISCUSS_ACTION_ID = 104;

/**
 * @typedef {import("@web/../tests/web_test_helpers").RouteCallback} WebRouteCallback
 */
/** @typedef {(this: ThisParameterType<WebRouteCallback>, ...args: Parameters<WebRouteCallback>) => Promise<Awaited<ReturnType<WebRouteCallback>>>} RouteCallback */

/** @param {{id: number}} guest */
export const authenticateGuest = (guest) => {
    const { env } = MockServer;
    /** @type {import("mock_models").ResUsers} */
    const ResUsers = env["res.users"];
    if (!guest?.id) {
        throw new MockServerError("Unauthorized");
    }
    const [publicUser] = ResUsers.read(serverState.publicUserId);
    env.cookie.set("dgid", guest.id);
    authenticate(publicUser.login, publicUser.password);
    env.uid = serverState.publicUserId;
};

/**
 * @param {number} guestId
 * @param {() => any} fn
 */
export async function withGuest(guestId, fn) {
    const { env } = MockServer;
    /** @type {import("mock_models").MailGuest} */
    const MailGuest = env["mail.guest"];
    const currentUser = env.user;
    const [targetGuest] = MailGuest.browse(guestId);
    authenticateGuest(targetGuest);
    let result;
    try {
        result = await fn();
    } finally {
        if (currentUser) {
            authenticate(currentUser.login, currentUser.password);
        } else {
            logout();
            env.cookie.delete("dgid");
        }
    }
    return result;
}

/** @param {Request} request */
export const parseRequestParams = async (request) => {
    const response = await request.json();
    return response.params;
};

const onRpcBeforeGlobal = { cb: (route, args) => {} };
const onRpcAfterGlobal = { cb: (route, args) => {} };
registry.category("mail.on_rpc_before_global").add("global", onRpcBeforeGlobal);
registry.category("mail.on_rpc_after_global").add("global", onRpcAfterGlobal);

export const registeredRoutes = [];

export function registerMailMockRoutes() {
    for (const [route, handler] of registeredRoutes) {
        onRpc(route, handler);
    }
}

export function registerRoute(route, handler) {
    /** @type {RouteCallback & {before?: (args: any) => any, after?: (response: any) => any}} */
    const beforeCallableHandler = async function (request) {
        let args;
        try {
            args = await parseRequestParams(request);
        } catch {
            args = await request.text();
        }
        let res = await onRpcBeforeGlobal.cb?.(route, args);
        if (res !== undefined) {
            return res;
        }
        res = await beforeCallableHandler.before?.(args);
        if (res !== undefined) {
            return res;
        }
        const response = handler.call(this, request);
        res = await beforeCallableHandler?.after?.(response);
        if (res !== undefined) {
            return res;
        }
        return response;
    };
    mockRpcRegistry.add(route, beforeCallableHandler);
    registeredRoutes.push([route, beforeCallableHandler]);
    onRpc(route, beforeCallableHandler);
}

registerRoute("/mail/attachment/upload", mail_attachment_upload);
/** @type {RouteCallback} */
async function mail_attachment_upload(request) {
    /** @type {import("mock_models").DiscussVoiceMetadata} */
    const DiscussVoiceMetadata = this.env["discuss.voice.metadata"];
    /** @type {import("mock_models").IrAttachment} */
    const IrAttachment = this.env["ir.attachment"];

    const body = await request.formData();
    const ufile = /** @type {File} */ (body.get("ufile"));
    const is_pending = body.get("is_pending") === "true";
    const model = is_pending ? "wizard.mail.message.send" : body.get("thread_model");
    const id = is_pending ? 0 : parseInt(/** @type {string} */ (body.get("thread_id")));
    const attachmentId = /** @type {number} */ (
        IrAttachment.create({
            mimetype: ufile.type,
            name: ufile.name,
            res_id: id,
            res_model: model,
        })
    );
    if (body.get("voice")) {
        /** @type {number} */ (
            DiscussVoiceMetadata.create({ attachment_id: attachmentId })
        );
    }
    return {
        data: {
            attachment_id: attachmentId,
            store_data: new mailDataHelpers.Store(
                IrAttachment.browse(attachmentId),
            ).get_result(),
        },
    };
}

registerRoute("/mail/attachment/delete", mail_attachment_delete);
/** @type {RouteCallback} */
async function mail_attachment_delete(request) {
    /** @type {import("mock_models").BusBus} */
    const BusBus = this.env["bus.bus"];
    /** @type {import("mock_models").IrAttachment} */
    const IrAttachment = this.env["ir.attachment"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const { attachment_id } = await parseRequestParams(request);
    const [partner] = ResPartner.read(this.env.user.partner_id);
    BusBus._sendone(partner, "ir.attachment/delete", {
        id: attachment_id,
    });
    return IrAttachment.unlink([attachment_id]);
}

registerRoute("/discuss/channel/attachments", load_attachments);
/** @type {RouteCallback} */
async function load_attachments(request) {
    /** @type {import("mock_models").IrAttachment} */
    const IrAttachment = this.env["ir.attachment"];

    const { channel_id, limit = 30, before = null } = await parseRequestParams(request);
    const matching = IrAttachment.filter(
        ({ id, res_id, res_model }) =>
            res_id === channel_id &&
            res_model === "discuss.channel" &&
            (!before || id < before),
    ).sort((a1, a2) => Number(a2.id) - Number(a1.id));
    const attachmentIds = matching.slice(0, limit).map(({ id }) => id);
    return {
        count: attachmentIds.length,
        has_more: matching.length > limit,
        store_data: new mailDataHelpers.Store(
            IrAttachment.browse(attachmentIds),
        ).get_result(),
    };
}

registerRoute("/mail/rtc/channel/join_call", channel_call_join);
/** @type {RouteCallback} */
async function channel_call_join(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").DiscussChannelRtcSession} */
    const DiscussChannelRtcSession = this.env["discuss.channel.rtc.session"];

    const { channel_id } = await parseRequestParams(request);
    const memberOfCurrentUser =
        DiscussChannel._get_or_create_member_for_self(channel_id);
    const sessionId = /** @type {number} */ (
        DiscussChannelRtcSession.create({
            channel_member_id: memberOfCurrentUser.id,
            channel_id,
            guest_id: memberOfCurrentUser.guest_id,
            partner_id: memberOfCurrentUser.partner_id,
        })
    );
    const channelMembers = DiscussChannelMember._filter([
        ["channel_id", "=", channel_id],
    ]);
    const rtcSessions = DiscussChannelRtcSession._filter([
        [
            "channel_member_id",
            "in",
            channelMembers.map((channelMember) => channelMember.id),
        ],
    ]);
    return new mailDataHelpers.Store(DiscussChannel.browse(channel_id), {
        rtc_session_ids: mailDataHelpers.Store.many(
            rtcSessions,
            makeKwArgs({ mode: "ADD" }),
        ),
    })
        .add("Rtc", {
            iceServers: false,
            localSession: mailDataHelpers.Store.one(
                DiscussChannelRtcSession.browse(sessionId),
            ),
        })
        .get_result();
}

registerRoute("/mail/rtc/channel/leave_call", channel_call_leave);
/** @type {RouteCallback} */
async function channel_call_leave(request) {
    /** @type {import("mock_models").BusBus} */
    const BusBus = this.env["bus.bus"];
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").DiscussChannelRtcSession} */
    const DiscussChannelRtcSession = this.env["discuss.channel.rtc.session"];
    /** @type {import("mock_models").MailGuest} */
    const MailGuest = this.env["mail.guest"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const { channel_id } = await parseRequestParams(request);
    const channelMembers = DiscussChannelMember._filter([
        ["channel_id", "=", channel_id],
        ["is_self", "=", true],
    ]);
    const rtcSessions = DiscussChannelRtcSession._filter([
        [
            "channel_member_id",
            "in",
            channelMembers.map((channelMember) => channelMember.id),
        ],
    ]);
    /** @type {[any, string, any][]} */
    const notifications = [];
    const sessionsByChannelId = {};
    for (const session of rtcSessions) {
        const [member] = DiscussChannelMember.browse(session.channel_member_id);
        if (!sessionsByChannelId[member.channel_id]) {
            sessionsByChannelId[member.channel_id] = [];
        }
        sessionsByChannelId[member.channel_id].push(session);
    }
    for (const [channelId, sessions] of Object.entries(sessionsByChannelId)) {
        const channel = DiscussChannel.search_read([
            ["id", "=", parseInt(channelId)],
        ])[0];
        notifications.push([
            channel,
            "mail.record/insert",
            new mailDataHelpers.Store(DiscussChannel.browse(Number(channelId)), {
                rtc_session_ids: mailDataHelpers.Store.many(
                    DiscussChannelRtcSession.browse(
                        sessions.map((session) => session.id),
                    ),
                    makeKwArgs({ only_id: true, mode: "DELETE" }),
                ),
            }).get_result(),
        ]);
    }
    for (const rtcSession of rtcSessions) {
        const target = rtcSession.guest_id
            ? MailGuest.search_read([["id", "=", rtcSession.guest_id]])[0]
            : ResPartner.search_read([["id", "=", rtcSession.partner_id]])[0];
        notifications.push([
            target,
            "discuss.channel.rtc.session/ended",
            { sessionId: rtcSession.id },
        ]);
    }
    this.env["discuss.channel.rtc.session"].unlink(
        Array.from(rtcSessions).map(({ id }) => id),
    );
    BusBus._sendmany(notifications);
}

registerRoute("/mail/rtc/channel/upgrade_connection", channel_upgrade_connection);
/** @type {RouteCallback} */
async function channel_upgrade_connection() {}

registerRoute("/discuss/channel/join", discuss_channel_join);
/** @type {RouteCallback} */
async function discuss_channel_join(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const { channel_id } = await parseRequestParams(request);
    if (!DiscussChannel._get_or_create_member_for_self(channel_id)) {
        const [partner, guest] = ResPartner._get_current_persona();
        DiscussChannelMember.create({
            channel_id,
            ...(guest ? { guest_id: guest.id } : { partner_id: partner.id }),
        });
    }
    return new mailDataHelpers.Store(DiscussChannel.browse(channel_id)).get_result();
}

registerRoute("/discuss/channel/members", discuss_channel_members);
/** @type {RouteCallback} */
async function discuss_channel_members(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];

    const { channel_id, known_member_ids } = await parseRequestParams(request);
    return DiscussChannel._load_more_members([channel_id], known_member_ids);
}

registerRoute("/discuss/channel/messages", discuss_channel_messages);
/** @type {RouteCallback} */
async function discuss_channel_messages(request) {
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];

    const { channel_id, fetch_params = {} } = await parseRequestParams(request);
    const channel = this.env["discuss.channel"].browse(channel_id);
    const res = MailMessage._message_fetch([], channel, makeKwArgs(fetch_params));
    const { messages } = res;
    delete res.messages;
    if (!this.env["res.users"]._is_public(this.env.uid)) {
        MailMessage.set_message_done(messages.map((message) => message.id));
    }
    return {
        ...res,
        data: new mailDataHelpers.Store(
            MailMessage.browse(messages.map((message) => message.id)),
            makeKwArgs({ for_current_user: true }),
        ).get_result(),
        messages: messages.map((message) => message.id),
    };
}

registerRoute(
    "/discuss/channel/sub_channel/create",
    discuss_channel_sub_channel_create,
);
async function discuss_channel_sub_channel_create(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    const { from_message_id, parent_channel_id, name } =
        await parseRequestParams(request);
    return DiscussChannel._create_sub_channel(
        [parent_channel_id],
        makeKwArgs({ from_message_id, name }),
    );
}

registerRoute(
    "/discuss/channel/sub_channel/delete",
    discuss_channel_sub_channel_delete,
);
async function discuss_channel_sub_channel_delete(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];
    const { sub_channel_id } = await parseRequestParams(request);
    const [partner] = ResPartner.read(this.env.user.partner_id);
    const [subChannel] = DiscussChannel.read(sub_channel_id);
    if (subChannel.author_id[0] !== partner.id) {
        return;
    }
    const [sub_channel] = DiscussChannel.browse(sub_channel_id);
    DiscussChannel.message_post(
        sub_channel.parent_channel_id,
        makeKwArgs({
            body: `<div data-oe-type="thread_deletion" class="o_mail_notification">${sub_channel.name}</div>`,
            message_type: "notification",
            subtype_xmlid: "mail.mt_comment",
        }),
    );
    DiscussChannel.unlink([sub_channel_id]);
}

registerRoute("/discuss/channel/sub_channel/fetch", discuss_channel_sub_channel_fetch);
async function discuss_channel_sub_channel_fetch(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];
    const { parent_channel_id, before, limit } = await parseRequestParams(request);
    /** @type {import("@web/core/domain").DomainListRepr} */
    const domain = [["parent_channel_id", "=", parent_channel_id]];
    if (before) {
        domain.push(["id", "<", before]);
    }
    const subChannels = DiscussChannel.search(
        domain,
        makeKwArgs({ limit, order: "id DESC" }),
    );
    const store = new mailDataHelpers.Store(DiscussChannel.browse(subChannels));
    const lastMessageIds = [];
    for (const channel of DiscussChannel.browse(subChannels)) {
        if (channel.message_ids.length) {
            lastMessageIds.push(Math.max(...channel.message_ids));
        }
    }
    store.add(MailMessage.browse(lastMessageIds));
    return {
        store_data: store.get_result(),
        sub_channel_ids: subChannels,
    };
}

registerRoute("/discuss/channel/favorite", discuss_channel_favorite);
/** @type {RouteCallback} */
async function discuss_channel_favorite(request) {
    const { channel_id, is_favorite } = await parseRequestParams(request);
    const DiscussChannelMember = this.env["discuss.channel.member"];
    const member = messagingMenuHelpers._selfMember(
        this.env,
        this.env["discuss.channel"].browse(channel_id)[0],
    );
    DiscussChannelMember.write([member.id], { is_favorite });
    const [partner] = this.env["res.partner"].read(this.env.user.partner_id);
    this.env["bus.bus"]._sendone(
        partner,
        "mail.record/insert",
        new mailDataHelpers.Store(DiscussChannelMember.browse([member.id]), {
            is_favorite,
        }).get_result(),
    );
}

registerRoute("/discuss/settings/mute", discuss_settings_mute);
/** @type {RouteCallback} */
async function discuss_settings_mute(request) {
    /** @type {import("mock_models").BusBus} */
    const BusBus = this.env["bus.bus"];
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const { channel_id, minutes } = await parseRequestParams(request);
    let mute_until_dt;
    if (minutes === -1) {
        mute_until_dt = serializeDateTime(parseISO("9999-12-31T23:59:59"));
    } else if (minutes) {
        mute_until_dt = serializeDateTime(now().add({ minutes }));
    } else {
        mute_until_dt = false;
    }
    const member = DiscussChannel._get_or_create_member_for_self(channel_id);
    DiscussChannelMember.write([member.id], { mute_until_dt });
    const [partner] = ResPartner.read(this.env.user.partner_id);
    BusBus._sendone(
        partner,
        "mail.record/insert",
        new mailDataHelpers.Store(DiscussChannelMember.browse([member.id]), {
            mute_until_dt,
        }).get_result(),
    );
    return "dummy";
}

registerRoute("/discuss/settings/custom_notifications", discuss_custom_notifications);
/** @type {RouteCallback} */
async function discuss_custom_notifications(request) {
    /** @type {import("mock_models").ResUsersSettings} */
    const ResUsersSettings = this.env["res.users.settings"];
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];

    const { custom_notifications, channel_id } = await parseRequestParams(request);
    let record;
    let model;
    if (!channel_id) {
        record = ResUsersSettings._get_or_create_for_user(this.env.uid);
        model = ResUsersSettings;
    } else {
        record = DiscussChannel._get_or_create_member_for_self(channel_id);
        model = DiscussChannelMember;
    }
    if (!record) {
        return;
    }
    model.set_custom_notifications(record.id, custom_notifications);
}

registerRoute("/discuss/channel/notify_typing", discuss_channel_notify_typing);
/** @type {RouteCallback} */
async function discuss_channel_notify_typing(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];

    const { channel_id, is_typing } = await parseRequestParams(request);
    const memberOfCurrentUser =
        DiscussChannel._get_or_create_member_for_self(channel_id);
    if (!memberOfCurrentUser) {
        return;
    }
    DiscussChannelMember.notify_typing([Number(memberOfCurrentUser.id)], is_typing);
}

registerRoute("/discuss/channel/ping", channel_ping);
/** @type {RouteCallback} */
async function channel_ping(request) {}

registerRoute("/discuss/channel/pinned_messages", discuss_channel_pins);
/** @type {RouteCallback} */
async function discuss_channel_pins(request) {
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];

    const { channel_id } = await parseRequestParams(request);
    const messageIds = MailMessage.search([
        ["model", "=", "discuss.channel"],
        ["res_id", "=", channel_id],
        ["pinned_at", "!=", false],
    ]);
    return new mailDataHelpers.Store(
        MailMessage.browse(messageIds),
        makeKwArgs({ for_current_user: true }),
    ).get_result();
}

registerRoute("/discuss/channel/mark_as_read", discuss_channel_mark_as_read);
/** @type {RouteCallback} */
async function discuss_channel_mark_as_read(request) {
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    const { channel_id, last_message_id } = await parseRequestParams(request);
    const [partner, guest] = this.env["res.partner"]._get_current_persona();
    const [memberId] = this.env["discuss.channel.member"].search([
        ["channel_id", "=", channel_id],
        partner ? ["partner_id", "=", partner.id] : ["guest_id", "=", guest.id],
    ]);
    if (!memberId) {
        return;
    }
    return DiscussChannelMember._mark_as_read([memberId], last_message_id);
}

registerRoute(
    "/discuss/channel/set_new_message_separator",
    discuss_channel_set_new_message_separator,
);
/** @type {RouteCallback} */
async function discuss_channel_set_new_message_separator(request) {
    const { channel_id, message_id } = await parseRequestParams(request);
    const [partner, guest] = this.env["res.partner"]._get_current_persona();
    const [memberId] = this.env["discuss.channel.member"].search([
        ["channel_id", "=", channel_id],
        partner ? ["partner_id", "=", partner.id] : ["guest_id", "=", guest.id],
    ]);
    return this.env["discuss.channel.member"]._update_new_message_separator(
        [memberId],
        message_id,
        true,
    );
}

registerRoute("/discuss/gif/favorites", get_favorites);
/** @type {RouteCallback} */
async function get_favorites(request) {
    return [[], false];
}
registerRoute("/discuss/gif/add_favorite", add_favorite);
/** @type {RouteCallback} */
async function add_favorite(request) {
    /** @type {import("mock_models").DiscussGifFavorite} */
    const DiscussGifFavorite = this.env["discuss.gif.favorite"];
    const { tenor_gif_id } = await parseRequestParams(request);
    if (
        !DiscussGifFavorite.search([["tenor_gif_id", "=", String(tenor_gif_id)]]).length
    ) {
        /** @type {number} */ (
            DiscussGifFavorite.create({ tenor_gif_id: String(tenor_gif_id) })
        );
    }
}

registerRoute("/discuss/gif/remove_favorite", remove_favorite);
/** @type {RouteCallback} */
async function remove_favorite(request) {
    /** @type {import("mock_models").DiscussGifFavorite} */
    const DiscussGifFavorite = this.env["discuss.gif.favorite"];
    const { tenor_gif_id } = await parseRequestParams(request);
    DiscussGifFavorite.unlink(
        DiscussGifFavorite.search([["tenor_gif_id", "=", String(tenor_gif_id)]]),
    );
}

registerRoute("/mail/link_preview", mail_link_preview);
/** @type {RouteCallback} */
async function mail_link_preview(request) {
    /** @type {import("mock_models").BusBus} */
    const BusBus = this.env["bus.bus"];
    /** @type {import("mock_models").MailLinkPreview} */
    const MailLinkPreview = this.env["mail.link.preview"];
    /** @type {import("mock_models").MailMessageLinkPreview} */
    const MailMessageLinkPreview = this.env["mail.message.link.preview"];
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];

    const { message_id } = await parseRequestParams(request);
    const [message] = MailMessage.search_read([["id", "=", message_id]]);
    const link = createDocumentFragmentFromContent(markup(message.body)).querySelector(
        "a[href^='https://tenor.com'], a[href^='https://make-link-preview.com'], a[href^='https://media.tenor.com']",
    );
    if (link) {
        const isGifPreview =
            /** @type {HTMLAnchorElement} */ (link).href.startsWith(
                "https://tenor.com",
            ) ||
            /** @type {HTMLAnchorElement} */ (link).href.startsWith(
                "https://media.tenor.com",
            );
        const sourceUrl = isGifPreview
            ? /** @type {HTMLAnchorElement} */ (link).href
            : "https://make-link-preview.com";
        const [existingLinkPreviewId] = MailLinkPreview.search([
            ["source_url", "=", sourceUrl],
        ]);
        const linkPreviewId =
            existingLinkPreviewId ??
            /** @type {number} */ (
                MailLinkPreview.create({
                    og_description: isGifPreview
                        ? "Click to view the GIF"
                        : "test description",
                    og_image: isGifPreview
                        ? /** @type {HTMLAnchorElement} */ (link).href
                        : undefined,
                    og_mimetype: isGifPreview ? "image/gif" : undefined,
                    og_title: isGifPreview ? "Gif title" : "Article title",
                    og_type: isGifPreview ? "video.other" : "article",
                    source_url: sourceUrl,
                })
            );
        const alreadyOnMessage = MailMessageLinkPreview.search([
            ["message_id", "=", message.id],
            ["link_preview_id", "=", linkPreviewId],
        ]);
        if (alreadyOnMessage.length === 0) {
            /** @type {number} */ (
                MailMessageLinkPreview.create({
                    message_id: message.id,
                    link_preview_id: linkPreviewId,
                })
            );
        }
        BusBus._sendone(
            MailMessage._bus_notification_target(message_id),
            "mail.record/insert",
            new mailDataHelpers.Store(MailMessage.browse(message_id)).get_result(),
        );
    }
}

registerRoute("/mail/link_preview/hide", mail_link_preview_hide);
/** @type {RouteCallback} */
async function mail_link_preview_hide(request) {
    /** @type {import("mock_models").BusBus} */
    const BusBus = this.env["bus.bus"];
    /** @type {import("mock_models").MailMessageLinkPreview} */
    const MailMessageLinkPreview = this.env["mail.message.link.preview"];
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];

    const { message_link_preview_ids } = await parseRequestParams(request);
    const messageLinkPreviews = MailMessageLinkPreview.browse(
        MailMessageLinkPreview.search([["id", "in", message_link_preview_ids]]),
    );
    for (const messageLinkPreview of messageLinkPreviews) {
        messageLinkPreview.is_hidden = true;
        BusBus._sendone(
            MailMessage._bus_notification_target(messageLinkPreview.message_id),
            "mail.record/insert",
            new mailDataHelpers.Store(
                MailMessage.browse(messageLinkPreview.message_id),
            ).get_result(),
        );
    }
}

registerRoute("/mail/message/post", mail_message_post);
/** @type {RouteCallback} */
export async function mail_message_post(request) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];
    /** @type {import("mock_models").MailThread} */
    const MailThread = this.env["mixin.mail.thread"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const { context, post_data, thread_id, thread_model, canned_response_ids } =
        await parseRequestParams(request);
    if (canned_response_ids) {
        for (const cannedResponseId of canned_response_ids) {
            this.env["mail.canned.response"].write([cannedResponseId], {
                last_used: serializeDateTime(now()),
            });
        }
    }
    if (post_data.partner_emails) {
        post_data.partner_ids = post_data.partner_ids || [];
        for (const email of post_data.partner_emails) {
            const partner = ResPartner._filter([["email", "=", email]]);
            if (partner.length !== 0) {
                post_data.partner_ids.push(partner[0].id);
            } else {
                const partner_id = /** @type {number} */ (
                    ResPartner.create({
                        email,
                        name: email,
                    })
                );
                post_data.partner_ids.push(partner_id);
            }
        }
    }
    const finalData = {};
    const allowedParams = [
        "attachment_ids",
        "body",
        "message_type",
        "partner_ids",
        "subtype_xmlid",
    ];
    if (thread_model === "discuss.channel") {
        allowedParams.push("parent_id", "special_mentions");
    }
    if (post_data.role_ids?.length) {
        const userIds = this.env["res.users"].search([
            ["role_ids", "in", post_data.role_ids],
        ]);
        const partnerIds = this.env["res.partner"].search([
            ["user_ids", "in", userIds],
        ]);
        post_data.partner_ids = [
            ...new Set([...(post_data.partner_ids || []), ...partnerIds]),
        ];
    }
    for (const allowedParam of allowedParams) {
        if (post_data[allowedParam] !== undefined) {
            finalData[allowedParam] = post_data[allowedParam];
        }
    }
    const kwargs = makeKwArgs({ ...finalData, context });
    let messageIds;
    if (thread_model === "discuss.channel") {
        messageIds = DiscussChannel.message_post(thread_id, kwargs);
    } else {
        const model = this.env[thread_model];
        messageIds = MailThread.message_post.call(model, [thread_id], {
            ...kwargs,
            model: thread_model,
        });
    }
    return {
        message_id: messageIds[0],
        store_data: new mailDataHelpers.Store(
            MailMessage.browse(messageIds[0]),
            makeKwArgs({ for_current_user: true }),
        ).get_result(),
    };
}

registerRoute("/mail/message/reaction", mail_message_reaction);
/** @type {RouteCallback} */
async function mail_message_reaction(request) {
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];
    const { action, content, message_id } = await parseRequestParams(request);
    const partner_id = this.env.user?.partner_id ?? false;
    const guest_id = this.env.cookie.get("dgid") ?? false;
    const store = new mailDataHelpers.Store();
    MailMessage._message_reaction(
        message_id,
        content,
        partner_id,
        guest_id,
        action,
        store,
    );
    return store.get_result();
}

registerRoute("/mail/message/translate", translate);
/** @type {RouteCallback} */
async function translate(request) {}

registerRoute("/mail/message/update_content", mail_message_update_content);
/** @type {RouteCallback} */
async function mail_message_update_content(request) {
    /** @type {import("mock_models").BusBus} */
    const BusBus = this.env["bus.bus"];
    /** @type {import("mock_models").IrAttachment} */
    const IrAttachment = this.env["ir.attachment"];
    /** @type {import("mock_models").MailMessageLinkPreview} */
    const MailMessageLinkPreview = this.env["mail.message.link.preview"];
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];

    const { message_id, update_data } = await parseRequestParams(request);
    const [message] = MailMessage.browse(message_id);
    const msg_values = {};
    if (update_data.body !== null) {
        const edit_label = "<span class='o-mail-Message-edited'/>";
        msg_values.body =
            update_data.body === "" && update_data.attachment_ids.length === 0
                ? ""
                : update_data.body + edit_label;
    }
    if (update_data.attachment_ids.length === 0) {
        IrAttachment.unlink(message.attachment_ids);
    } else {
        const attachments = IrAttachment.browse(update_data.attachment_ids).filter(
            (attachment) =>
                attachment.res_model === "wizard.mail.message.send" &&
                attachment.create_uid === this.env.user?.id,
        );
        IrAttachment.write(
            attachments.map((attachment) => attachment.id),
            {
                res_model: message.model,
                res_id: message.res_id,
            },
        );
        msg_values.attachment_ids = update_data.attachment_ids;
    }
    if (update_data.body === "") {
        MailMessageLinkPreview.unlink(message.message_link_preview_ids);
    }
    if (!update_data.body && update_data.attachment_ids.length === 0) {
        msg_values.partner_ids = false;
        msg_values.parent_id = false;
    }
    if ("subject" in update_data) {
        msg_values.subject = update_data.subject;
    }
    MailMessage.write([message_id], msg_values);
    const res = {
        attachment_ids: mailDataHelpers.Store.many(
            IrAttachment.browse(message.attachment_ids),
        ),
        body: ["markup", message.body],
        parent_id: mailDataHelpers.Store.one(MailMessage.browse(message.parent_id)),
        partner_ids: mailDataHelpers.Store.many(
            this.env["res.partner"].browse(message.partner_ids),
            makeKwArgs({ fields: ["avatar_128", "name"] }),
        ),
        pinned_at: message.pinned_at,
        message_link_preview_ids: message.message_link_preview_ids,
    };
    if ("subject" in update_data) {
        res.subject = message.subject;
    }
    BusBus._sendone(
        MailMessage._bus_notification_target(message.id),
        "mail.record/insert",
        new mailDataHelpers.Store(MailMessage.browse(message.id), res).get_result(),
    );
    return new mailDataHelpers.Store(
        MailMessage.browse(message_id),
        makeKwArgs({ for_current_user: true }),
    ).get_result();
}

registerRoute(
    "/discuss/channel/<int:cid>/partner/<int:pid>/avatar_128",
    partnerAvatar128,
);
/** @type {RouteCallback} */
async function partnerAvatar128(request, { cid, pid }) {
    return [cid, pid];
}

registerRoute("/mail/partner/from_email", mail_thread_partner_from_email);
/** @type {RouteCallback} */
async function mail_thread_partner_from_email(request) {
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const { thread_model, thread_id, emails } = await parseRequestParams(request);
    this.env[thread_model].browse(thread_id);
    const partners = emails.map(
        (email) => ResPartner.search([["email", "=", email]])[0],
    );
    for (const index in partners) {
        if (!partners[index]) {
            const email = emails[index];
            partners[index] = /** @type {number} */ (
                ResPartner.create({
                    email,
                    name: email,
                })
            );
        }
    }
    return partners.map((partner_id) => {
        const [partner] = ResPartner.browse(partner_id);
        return { id: partner_id, name: partner.name, email: partner.email };
    });
}

registerRoute("/mail/read_subscription_data", read_subscription_data);
/** @type {RouteCallback} */
async function read_subscription_data(request) {
    /** @type {import("mock_models").MailFollowers} */
    const MailFollowers = this.env["mail.followers"];
    /** @type {import("mock_models").MailMessageSubtype} */
    const MailMessageSubtype = this.env["mail.message.subtype"];

    const { follower_id } = await parseRequestParams(request);
    const [follower] = MailFollowers.browse(follower_id);
    const subtypes = MailMessageSubtype.search([
        "&",
        ["hidden", "=", false],
        "|",
        ["res_model", "=", follower.res_model],
        ["res_model", "=", false],
    ]);
    return {
        store_data: new mailDataHelpers.Store(
            MailMessageSubtype.browse(subtypes),
            makeKwArgs({ fields: ["name"] }),
        )
            .add(
                MailFollowers.browse(follower_id),
                makeKwArgs({ fields: ["subtype_ids"] }),
            )
            .get_result(),
        subtype_ids: subtypes,
    };
}

registerRoute("/mail/rtc/session/update_and_broadcast", session_update_and_broadcast);
/** @type {RouteCallback} */
async function session_update_and_broadcast(request) {
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").DiscussChannelRtcSession} */
    const DiscussChannelRtcSession = this.env["discuss.channel.rtc.session"];

    const { session_id, values } = await parseRequestParams(request);
    const [session] = DiscussChannelRtcSession.search_read([["id", "=", session_id]]);
    const [currentChannelMember] = DiscussChannelMember.search_read([
        ["id", "=", session.channel_member_id[0]],
    ]);
    if (session && currentChannelMember.partner_id[0] === serverState.partnerId) {
        DiscussChannelRtcSession._update_and_broadcast(Number(session.id), values);
    }
}

registerRoute("/mail/thread/messages", mail_thread_messages);
/** @type {RouteCallback} */
async function mail_thread_messages(request) {
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];

    const {
        fetch_params = {},
        thread_id,
        thread_model,
    } = await parseRequestParams(request);
    const thread = this.env[thread_model].browse(thread_id);
    const res = MailMessage._message_fetch([], thread, makeKwArgs(fetch_params));
    const { messages } = res;
    delete res.messages;
    if (!this.env["res.users"]._is_public(this.env.uid)) {
        MailMessage.set_message_done(messages.map((message) => message.id));
    }
    return {
        ...res,
        data: new mailDataHelpers.Store(
            MailMessage.browse(messages.map((message) => message.id)),
            makeKwArgs({ for_current_user: true }),
        ).get_result(),
        messages: messages.map((message) => message.id),
    };
}

registerRoute("/mail/action", mail_action);
/** @type {RouteCallback} */
async function mail_action(request) {
    const args = await parseRequestParams(request);
    return processRequest.call(this, args.fetch_params, args.context).get_result();
}

registerRoute("/mail/data", mail_data);
/** @type {RouteCallback} */
export async function mail_data(request) {
    const args = await parseRequestParams(request);
    return processRequest.call(this, args.fetch_params, args.context).get_result();
}

registerRoute("/discuss/search", search);
/** @type {RouteCallback} */
async function search(request) {
    const { term, limit = 10 } = await parseRequestParams(request);

    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];

    const store = new mailDataHelpers.Store();
    const lowerTerm = (term ?? "").toLowerCase();
    /** @param {any} channel */
    const isSelfMember = (channel) =>
        Boolean(messagingMenuHelpers._selfMember(this.env, channel));
    /** @param {any} channel */
    const matches = (channel) => {
        if (channel.channel_type === "chat") {
            return false;
        }
        if (channel.name) {
            return channel.name.toLowerCase().includes(lowerTerm);
        }
        return (
            channel.channel_type === "group" &&
            isSelfMember(channel) &&
            DiscussChannelMember._filter([["channel_id", "=", channel.id]]).some(
                (member) => {
                    const persona = member.partner_id
                        ? ResPartner.browse(member.partner_id)[0]
                        : this.env["mail.guest"].browse(member.guest_id)[0];
                    return persona?.name?.toLowerCase().includes(lowerTerm);
                },
            )
        );
    };
    const candidates = DiscussChannel._filter([]).filter(matches);
    /** @param {any} channel */
    const isFavorite = (channel) =>
        Boolean(messagingMenuHelpers._selfMember(this.env, channel)?.is_favorite);
    const channelIds = [
        ...candidates.filter(isFavorite),
        ...candidates.filter(
            (channel) => isSelfMember(channel) && !isFavorite(channel),
        ),
        ...candidates.filter((channel) => !isSelfMember(channel)),
    ]
        .slice(0, limit)
        .map((channel) => channel.id);
    /** @type {{channel_ids: number[], mentioned_channel_ids?: number[], recent_channel_ids?: number[]}} */
    const result = { channel_ids: channelIds };
    const listed = new Set(channelIds);
    if (!this.env["res.users"]._is_public(this.env.uid)) {
        if (!term) {
            const byRecency = DiscussChannel._filter([])
                .filter(isSelfMember)
                .sort(
                    (c1, c2) =>
                        (c2.last_interest_dt || "").localeCompare(
                            c1.last_interest_dt || "",
                        ) || c2.id - c1.id,
                );
            result.mentioned_channel_ids = byRecency
                .filter((channel) =>
                    messagingMenuHelpers.isImportantChannel(this.env, channel),
                )
                .slice(0, 3)
                .map((channel) => channel.id);
            result.recent_channel_ids = byRecency
                .slice(0, 6)
                .map((channel) => channel.id);
            for (const id of [
                ...result.mentioned_channel_ids,
                ...result.recent_channel_ids,
            ]) {
                listed.add(id);
            }
        }
        const { partner_ids } = ResPartner._search_for_channel_invite(
            store,
            term,
            undefined,
            limit,
        );
        for (const id of ResPartner._get_self_chats(partner_ids)) {
            listed.add(id);
        }
    }
    store.add(DiscussChannel.browse([...listed]));
    return { ...result, store_data: store.get_result() };
}

registerRoute(
    "/mail/thread/recipients/get_suggested_recipients",
    get_suggested_recipients,
);
/** @type {RouteCallback} */
async function get_suggested_recipients(request) {
    const { thread_model, thread_id, partner_ids, main_email } =
        await parseRequestParams(request);
    const MailThread = this.env[thread_model];
    return MailThread._message_get_suggested_recipients(
        [thread_id],
        partner_ids,
        main_email,
    );
}

registerRoute("/mail/thread/unsubscribe", mail_thread_unsubscribe);
/** @type {RouteCallback} */
async function mail_thread_unsubscribe(request) {
    const { res_model, res_id, partner_ids } = await parseRequestParams(request);
    const thread = this.env[res_model].browse(res_id);
    this.env["mixin.mail.thread"].message_unsubscribe.call(
        thread,
        [res_id],
        partner_ids,
    );
    return new mailDataHelpers.Store(
        thread,
        makeKwArgs({
            as_thread: true,
            request_list: ["followers", "suggestedRecipients"],
        }),
    ).get_result();
}

registerRoute("/mail/thread/subscribe", mail_thread_subscribe);
/** @type {RouteCallback} */
async function mail_thread_subscribe(request) {
    const { res_model, res_id, partner_ids } = await parseRequestParams(request);
    const thread = this.env[res_model].browse(res_id);
    this.env["mixin.mail.thread"].message_subscribe.call(thread, [res_id], partner_ids);
    return new mailDataHelpers.Store(
        thread,
        makeKwArgs({
            as_thread: true,
            request_list: ["followers", "suggestedRecipients"],
        }),
    ).get_result();
}

function processRequest(fetchParams, context) {
    const store = new mailDataHelpers.Store();
    for (const fetchParam of fetchParams) {
        const [name, params, data_id] =
            typeof fetchParam === "string" || fetchParam instanceof String
                ? [fetchParam, undefined, undefined]
                : fetchParam;
        store.data_id = data_id;
        mailDataHelpers._process_request_for_all.call(
            this,
            store,
            name,
            params,
            context,
        );
        mailDataHelpers._process_request_for_internal_user.call(
            this,
            store,
            name,
            params,
        );
    }
    store.data_id = null;
    return store;
}

function _process_request_for_all(store, name, params, context = {}) {
    /** @type {import("mock_models").DiscussChannel} */
    const DiscussChannel = this.env["discuss.channel"];
    /** @type {import("mock_models").DiscussChannelMember} */
    const DiscussChannelMember = this.env["discuss.channel.member"];
    /** @type {import("mock_models").MailGuest} */
    const MailGuest = this.env["mail.guest"];
    /** @type {import("mock_models").MailMessage} */
    const MailMessage = this.env["mail.message"];
    /** @type {import("mock_models").MailNotification} */
    const MailNotification = this.env["mail.notification"];
    /** @type {import("mock_models").ResPartner} */
    const ResPartner = this.env["res.partner"];
    /** @type {import("mock_models").ResUsers} */
    const ResUsers = this.env["res.users"];
    if (name === "init_messaging") {
        if (
            !MailGuest._get_guest_from_context() ||
            !ResUsers._is_public(this.env.uid)
        ) {
            ResUsers._init_messaging([this.env.uid], store);
        }
        const guest =
            ResUsers._is_public(this.env.uid) && MailGuest._get_guest_from_context();
        const members = DiscussChannelMember._filter([
            guest
                ? ["guest_id", "=", guest.id]
                : ["partner_id", "=", this.env.user.partner_id],
            ["rtc_inviting_session_id", "!=", false],
        ]);
        /** @type {import("@web/core/domain").DomainListRepr} */
        const channelsDomain = [["id", "in", members.map((m) => m.channel_id)]];
        store.add(DiscussChannel.browse(DiscussChannel.search(channelsDomain)));
    }
    if (name === "failures" && this.env.user?.partner_id) {
        const [partner] = ResPartner.browse(this.env.user.partner_id);
        const messages = MailMessage._filter([
            ["author_id", "=", partner.id],
            ["res_id", "!=", 0],
            ["model", "!=", false],
            ["message_type", "!=", "user_notification"],
        ]).filter((message) => {
            const notifications = MailNotification._filter([
                ["mail_message_id", "=", message.id],
                ["notification_status", "in", ["bounce", "exception"]],
            ]);
            return notifications.length > 0;
        });
        messages.length = Math.min(messages.length, 100);
        MailMessage._message_notifications_to_store(
            messages.map((message) => message.id),
            store,
        );
    }
    /** @param {number[]} channelIds */
    const addLastMessages = (channelIds) => {
        for (const id of channelIds) {
            store.add("discuss.channel", { id, last_message_fetched: true });
        }
        store.add(
            MailMessage.browse(
                channelIds
                    .map(
                        (channelId) =>
                            MailMessage._filter([
                                ["model", "=", "discuss.channel"],
                                ["res_id", "=", channelId],
                            ]).sort((a, b) => b.id - a.id)[0],
                    )
                    .filter((lastMessage) => lastMessage)
                    .map((message) => message.id),
            ),
            makeKwArgs({ for_current_user: true }),
        );
        const lastNeedactionIds = channelIds
            .map((channelId) =>
                Math.max(
                    0,
                    ...MailMessage._filter([
                        ["model", "=", "discuss.channel"],
                        ["res_id", "=", channelId],
                    ])
                        .filter(
                            (message) =>
                                MailNotification._filter([
                                    ["mail_message_id", "=", message.id],
                                    ["res_partner_id", "=", this.env.user?.partner_id],
                                    ["is_read", "=", false],
                                ]).length > 0,
                        )
                        .map((message) => message.id),
                ),
            )
            .filter(Boolean);
        store.add(
            MailMessage.browse(lastNeedactionIds),
            makeKwArgs({ for_current_user: true }),
        );
    };
    if (name === "odoobot_chat" && messagingMenuHelpers._isInternal(this.env)) {
        const odoobotId = serverState.odoobotId;
        const [chat] = DiscussChannel._filter([["channel_type", "=", "chat"]]).filter(
            (channel) =>
                messagingMenuHelpers._selfMember(this.env, channel) &&
                DiscussChannelMember._filter([
                    ["channel_id", "=", channel.id],
                    ["partner_id", "=", odoobotId],
                ]).length > 0,
        );
        if (chat) {
            store.add(DiscussChannel.browse(chat.id));
        }
    }
    if (name === "/mail/messaging_menu/initialize_counters") {
        const filterIdByTabId =
            params.filter_id_by_tab_id_by_record_type?.["discuss.channel"] ?? {};
        const important = DiscussChannel._filter([]).filter((channel) =>
            messagingMenuHelpers.isImportantChannel(this.env, channel),
        );
        for (const [tabId, filterId] of Object.entries(filterIdByTabId)) {
            const predicate = messagingMenuHelpers.getFullPredicate(
                this.env,
                tabId,
                filterId ? [filterId] : [],
            );
            store.add("MessagingMenuTab", {
                id: tabId,
                init_counter_ids: important.filter(predicate).map((c) => c.id),
            });
            if (params.presence_tab_ids?.includes(tabId)) {
                const tabPredicate = messagingMenuHelpers.getFullPredicate(
                    this.env,
                    tabId,
                );
                store.add("MessagingMenuTab", {
                    id: tabId,
                    has_records: DiscussChannel._filter([]).some(tabPredicate),
                });
            }
        }
    }
    if (name === "/mail/messaging_menu/discuss.channel/load_more") {
        const predicate = messagingMenuHelpers.getFullPredicate(
            this.env,
            params.tab_id,
            params.filter_ids,
        );
        const excludeIds = new Set(params.exclude_ids ?? []);
        const searchTerm = params.search_term?.toLowerCase();
        /** @param {any} channel */
        const isFavorite = (channel) =>
            Boolean(messagingMenuHelpers._selfMember(this.env, channel)?.is_favorite);
        /** @param {any} channel */
        const isMeetingNotOver = (channel) =>
            messagingMenuHelpers._isMeetingNotOver(this.env, channel);
        const channels = DiscussChannel._filter([])
            .filter(
                (channel) =>
                    !excludeIds.has(channel.id) &&
                    (!searchTerm || channel.name?.toLowerCase().includes(searchTerm)) &&
                    predicate(channel),
            )
            .sort(
                (c1, c2) =>
                    Number(isFavorite(c2)) - Number(isFavorite(c1)) ||
                    (params.tab_id === "meeting"
                        ? Number(isMeetingNotOver(c2)) - Number(isMeetingNotOver(c1))
                        : 0) ||
                    (c2.last_interest_dt || "").localeCompare(
                        c1.last_interest_dt || "",
                    ) ||
                    c2.id - c1.id,
            )
            .slice(0, params.limit);
        const ids = channels.map((channel) => channel.id);
        store.add(DiscussChannel.browse(ids));
        addLastMessages(ids);
        store.resolve_data_request({ is_fully_loaded: channels.length < params.limit });
    }
    if (name === "/mail/messaging_menu/mail.message/load_more") {
        const predicate = messagingMenuHelpers.getFullPredicate(
            this.env,
            params.tab_id,
            params.filter_ids,
        );
        const excludeIds = new Set(params.exclude_ids ?? []);
        const searchTerm = params.search_term?.toLowerCase();
        const messages = MailMessage._filter([])
            .filter(
                (message) =>
                    !excludeIds.has(message.id) &&
                    (!searchTerm || message.body?.toLowerCase().includes(searchTerm)) &&
                    predicate(message),
            )
            .sort((m1, m2) => m2.id - m1.id)
            .slice(0, params.limit);
        store.add(
            MailMessage.browse(messages.map((message) => message.id)),
            makeKwArgs({ for_current_user: true, add_followers: true }),
        );
        store.resolve_data_request({ is_fully_loaded: messages.length < params.limit });
    }
    if (name === "/mail/messaging_menu/get_most_popular_channels") {
        const memberCount = (/** @type {any} */ channel) =>
            DiscussChannelMember._filter([["channel_id", "=", channel.id]]).length;
        const channels = DiscussChannel._filter([["channel_type", "=", "channel"]])
            .sort((c1, c2) => memberCount(c2) - memberCount(c1) || c2.id - c1.id)
            .slice(0, 3);
        const ids = channels.map((channel) => channel.id);
        store.add(DiscussChannel.browse(ids));
        store.add({
            most_popular_channels: mailDataHelpers.Store.many(
                DiscussChannel.browse(ids),
                makeKwArgs({ only_id: true }),
            ),
        });
    }
    if (name === "mixin.mail.thread") {
        store.add(
            this.env[params.thread_model].browse(params.thread_id),
            makeKwArgs({ as_thread: true, request_list: params.request_list }),
        );
    }
    if (name === "discuss.channel") {
        const channels = DiscussChannel.search([["id", "=", params.ids]]);
        store.add(DiscussChannel.browse(channels));
        if (params.with_last_message) {
            addLastMessages(channels);
        }
        for (const channelId of params.ids.filter((id) => !channels.includes(id))) {
            const channel = DiscussChannel.browse([]);
            channel.push({ id: channelId });
            store.add(channel, makeKwArgs({ delete: true }));
        }
    }
    if (name === "/discuss/get_or_create_chat") {
        const channelId = DiscussChannel._get_or_create_chat(params.partners_to);
        store.add(channelId).resolve_data_request({
            channel: mailDataHelpers.Store.one(
                channelId,
                makeKwArgs({ only_id: true }),
            ),
        });
    }
    if (name === "/discuss/create_channel") {
        const channelId = DiscussChannel._create_channel(params.name, params.group_id);
        store.add(channelId).resolve_data_request({
            channel: mailDataHelpers.Store.one(
                channelId,
                makeKwArgs({ only_id: true }),
            ),
        });
    }
    if (name === "/discuss/create_group") {
        const channelId = DiscussChannel._create_group(
            params.partners_to,
            params.default_display_mode,
            params.name,
        );
        store.add(channelId).resolve_data_request({
            channel: mailDataHelpers.Store.one(
                channelId,
                makeKwArgs({ only_id: true }),
            ),
        });
    }
}

function _process_request_for_internal_user(store, name, params) {
    /** @type {import("mock_models").ResUsers} */
    const ResUsers = this.env["res.users"];
    if (name === "systray_get_activities" && this.env.user?.partner_id) {
        const bus_last_id = this.env["bus.bus"].lastBusNotificationId;
        const groups = ResUsers._get_activity_groups();
        store.add({
            activityCounter: groups.reduce(
                (counter, group) => counter + (group.due_count || 0),
                0,
            ),
            activityCounter_bus_id: bus_last_id,
            activityGroups: groups,
        });
    }
    if (name === "mail.canned.response") {
        const domain = [
            "|",
            ["create_uid", "=", this.env.user.id],
            ["group_ids", "in", this.env.user.group_ids],
        ];
        const CannedResponse = this.env["mail.canned.response"];
        const cannedResponses = CannedResponse.search(domain);
        store.add(CannedResponse.browse(cannedResponses));
    }
    if (name === "avatar_card") {
        const { id, model } = params;
        if (!id || !["res.users", "res.partner"].includes(model)) {
            return;
        }
        const Model = this.env[model];
        const [record] = Model.search([["id", "=", id]]);
        if (record) {
            const fields = Model._get_fields_store_avatar_card();
            store.add(Model.browse(record), makeKwArgs({ fields }));
        }
    }
}

const ids_by_model = {
    "mixin.mail.thread": ["model", "id"],
    MessageReactions: ["message", "content"],
    Rtc: [],
    Store: [],
};

function extractAndDeleteKwArgs(args, ...keys) {
    const allKwargs = unmakeKwArgs(getKwArgs(args, ...keys));
    const kwargs = {};
    for (const key of keys) {
        if (Object.hasOwn(allKwargs, key)) {
            kwargs[key] = allKwargs[key];
            delete allKwargs[key];
        }
    }
    return [kwargs, allKwargs];
}

export class StoreAttr {
    constructor(name, value, predicate) {
        const [kwargs] = extractAndDeleteKwArgs(
            arguments,
            "name",
            "value",
            "predicate",
        );
        this.name = kwargs.name;
        this.value = kwargs.value;
        this.predicate = kwargs.predicate;
    }

    _get_value(record, model = null) {
        if (typeof this.value === "function") {
            return this.value(record);
        }
        const value = this.value ?? record[this.name];
        return value;
    }
}

export class StoreRelation extends StoreAttr {
    constructor(name_or_record, fields, value, predicate, as_thread, only_id) {
        [{ name_or_record, fields, value, predicate, as_thread, only_id }] =
            extractAndDeleteKwArgs(
                arguments,
                "name_or_record",
                "fields",
                "value",
                "predicate",
                "as_thread",
                "only_id",
            );
        const name = typeof name_or_record === "string" ? name_or_record : null;
        super(makeKwArgs({ name, value }));
        this.records = name_or_record instanceof models.Model ? name_or_record : null;
        this.predicate = predicate;
        this.as_thread = as_thread;
        this.fields = fields;
        this.only_id = only_id;
    }
    _get_value(record, model) {
        let target = super._get_value(record);
        if (!target) {
            const res_model_field = model._fields["res_model"] ? "res_model" : "model";
            if (this.name === "thread" && !record["thread"]) {
                const res_model = record[res_model_field];
                const res_id = record["res_id"];
                if (res_model && res_id) {
                    target = model.env[res_model].browse(res_id);
                }
            }
        } else {
            const field = model._fields[this.name];

            target = model.env[field.relation].browse(target);
        }
        return this._copy_with_records(target, record);
    }

    _copy_with_records(target, record) {
        if (this.records) {
            throw new Error(`StoreRelation ${this.name} cannot be used with records`);
        }

        return new /** @type {new (...args: any[]) => this} */ (this.constructor)(
            target,
            makeKwArgs({
                fields: this.fields,
                value: this.value,
                predicate: this.predicate,
                as_thread: this.as_thread,
                only_id: this.only_id,
            }),
        );
    }

    _add_to_store(store, target, key) {
        if (!this.only_id) {
            store.add(
                this.records,
                this.fields,
                makeKwArgs({ as_thread: this.as_thread }),
            );
        }
    }
}

export class StoreOne extends StoreRelation {
    _add_to_store(store, target, key) {
        super._add_to_store(store, target, key);
        target[key] = this._get_id();
    }
    _get_id() {
        if (!this.records || !this.records.length) {
            return false;
        }
        const id = this.records[0].id;
        if (this.as_thread) {
            return { id, model: this.records._name };
        }
        if (this.records._name === "discuss.channel") {
            return { id, model: "discuss.channel" };
        }
        return id;
    }
}

export class StoreMany extends StoreRelation {
    constructor(
        name_or_record,
        fields,
        value,
        predicate,
        as_thread,
        mode,
        only_id,
        sort,
    ) {
        const [kwargs] = extractAndDeleteKwArgs(
            arguments,
            "name_or_record",
            "fields",
            "value",
            "predicate",
            "as_thread",
            "mode",
            "only_id",
            "sort",
        );
        name_or_record = kwargs.name_or_record;
        fields = kwargs.fields;
        value = kwargs.value;
        predicate = kwargs.predicate;
        as_thread = kwargs.as_thread;
        mode = kwargs.mode || "REPLACE";
        only_id = kwargs.only_id || false;
        sort = kwargs.sort || false;
        super(
            name_or_record,
            makeKwArgs({
                fields,
                value,
                predicate,
                as_thread,
                only_id,
            }),
        );
        this.mode = mode;
        /** @type {false | ((a: import("@web/../tests/_framework/mock_server/mock_model").ModelRecord, b: import("@web/../tests/_framework/mock_server/mock_model").ModelRecord) => number)} */
        this.sort = sort;
    }
    _copy_with_records(target, record) {
        const res = super._copy_with_records(target, record);
        res.mode = this.mode;
        res.sort = this.sort;
        return res;
    }

    _sort_records() {
        if (this.sort) {
            this.records.sort(this.sort);
            this.sort = false;
        }
    }
    _add_to_store(store, target, key) {
        this._sort_records();
        super._add_to_store(store, target, key);
        const rel_val = this._get_id();
        const previous_value = this.mode !== "REPLACE" ? target[key] : undefined;
        target[key] = (previous_value || []).concat(rel_val);
    }
    _get_id() {
        const res = [];

        if (this.records._name === "mail.message.reaction") {
            const reactionGroups = groupBy(this.records, (r) =>
                [r.message_id, r.content].join(","),
            );
            for (const groupId in reactionGroups) {
                const { message_id, content } = reactionGroups[groupId][0];
                res.push({ message: message_id, content: content });
            }
        } else {
            for (const record of this.records) {
                res.push(
                    new StoreOne(
                        this.records.env[this.records._name].browse(record.id),
                        makeKwArgs({
                            as_thread: this.as_thread,
                        }),
                    )._get_id(),
                );
            }
        }
        if (["ADD", "DELETE"].includes(this.mode)) {
            return [[this.mode, res]];
        }
        return res;
    }
}

export class Store {
    constructor(data, fields, as_thread, _delete, kwargs) {
        this.data = new Map();
        this.data_id = null;
        if (data) {
            this.add(...arguments);
        }
    }

    add(data, fields, as_thread, _delete, extra_fields, kwargs) {
        if (!data) {
            return this;
        }
        [{ data, fields, as_thread, delete: _delete, extra_fields }, kwargs] =
            extractAndDeleteKwArgs(
                arguments,
                "data",
                "fields",
                "as_thread",
                "delete",
                "extra_fields",
            );
        _delete = _delete ?? false;
        let model_name;
        if (data instanceof models.Model) {
            if (fields) {
                if (Object.keys(kwargs).length) {
                    throw new Error(
                        `expected empty kwargs with recordset ${data} values: ${kwargs}`,
                    );
                }
                if (_delete) {
                    throw new Error(
                        `deleted not expected for ${data} with values: ${fields}`,
                    );
                }
            }
            if (_delete) {
                if (data.length !== 1) {
                    throw new Error(`expected single record ${data} with delete`);
                }
                if (fields) {
                    throw new Error(
                        `for ${data} expected empty values with delete: ${fields}`,
                    );
                }
            }
            const ids = data.map((idOrRecord) =>
                typeof idOrRecord === "number" ? idOrRecord : idOrRecord.id,
            );
            if (_delete) {
                if (as_thread) {
                    this._add_model_values(
                        "mixin.mail.thread",
                        { id: data[0].id, model: data._name },
                        makeKwArgs({ delete: _delete }),
                    );
                } else {
                    this._add_model_values(
                        data._name,
                        { id: ids[0] },
                        makeKwArgs({ delete: _delete }),
                    );
                }
            } else {
                if (!fields) {
                    if (as_thread) {
                        fields = [];
                    } else {
                        fields = data._to_store_defaults || [];
                    }
                }
                fields = this._format_fields(fields).concat(
                    this._format_fields(extra_fields),
                );
                if (as_thread) {
                    MockServer.env["mixin.mail.thread"]._thread_to_store.call(
                        data,
                        this,
                        fields,
                        makeKwArgs(kwargs),
                    );
                } else {
                    if (data._to_store) {
                        data._to_store(this, fields, makeKwArgs(kwargs));
                    } else {
                        this._add_record_fields(data, fields, as_thread);
                    }
                }
            }
            return this;
        } else if (typeof data === "object") {
            if (fields) {
                throw new Error(`expected empty values with dict ${data}: ${fields}`);
            }
            if (Object.keys(kwargs).length) {
                throw new Error(`expected empty kwargs with dict ${data}: ${kwargs}`);
            }
            if (as_thread) {
                throw new Error(`expected not as_thread with dict ${data}: ${fields}`);
            }
            model_name = "Store";
            fields = data;
        } else {
            if (Object.keys(kwargs).length) {
                throw new Error(
                    `expected empty kwargs with model name ${data}: ${kwargs}`,
                );
            }
            if (as_thread) {
                throw new Error(
                    `expected not as_thread with model name ${data}: ${fields}`,
                );
            }
            model_name = data;
        }
        return this._add_model_values(model_name, fields, _delete);
    }

    _get_records_data_list(records, fields) {
        const abstractedFields = fields.filter((field) => field instanceof StoreAttr);
        const records_data_list = records
            ._read_format(
                records.map((r) => r.id),
                fields.filter((f) => !abstractedFields.includes(f)),
                false,
            )
            .map((data) => [data]);
        for (const index in records_data_list) {
            const record = records[index];
            for (const field of abstractedFields) {
                if (field instanceof StoreAttr) {
                    if (!field.predicate || field.predicate(record)) {
                        const field_data = {};
                        field_data[field.name] = field._get_value(record, records);
                        records_data_list[index].push(field_data);
                    }
                } else {
                    records_data_list[index].push(field);
                }
            }
        }
        return records_data_list;
    }

    _add_record_fields(records, fields, as_thread) {
        if (!records || !records.length) {
            return this;
        }
        if (!(records instanceof models.Model)) {
            throw new Error(`expected recordset for _add_record_fields: ${records}`);
        }
        fields = this._format_fields(fields);
        const data_list = this._get_records_data_list(records, fields);
        const model_name = records._name;
        for (const index in data_list) {
            for (const data of data_list[index]) {
                if (as_thread) {
                    this._add_model_values("mixin.mail.thread", {
                        id: records[index].id,
                        model: model_name,
                        ...data,
                    });
                } else {
                    this._add_model_values(model_name, {
                        id: records[index].id,
                        ...data,
                    });
                }
            }
        }
        return this;
    }
    _add_model_values(model_name, values, _delete) {
        if (typeof model_name !== "string") {
            throw new Error(`expected string for model name: ${model_name}: ${values}`);
        }
        const ids = ids_by_model[model_name] || ["id"];
        if (!ids.length) {
            if (typeof values !== "object") {
                throw new Error(`expected dict for singleton ${model_name}: ${values}`);
            }
            if (_delete) {
                throw new Error(`Singleton ${model_name} cannot be deleted`);
            }
            if (!this.data.has(model_name)) {
                this.data.set(model_name, {});
            }
            this._add_values(values, model_name);
            return this;
        }
        if (!Array.isArray(values)) {
            if (!values) {
                return this;
            }
            values = [values];
        }
        if (!values.length) {
            return this;
        }
        let records = this.data.get(model_name);
        if (!records) {
            records = new Map();
            this.data.set(model_name, records);
        }
        for (const vals of values) {
            if (typeof vals !== "object") {
                throw new Error(`expected dict for ${model_name}: ${vals}`);
            }
            for (const i of ids) {
                if (!vals[i]) {
                    throw new Error(`missing id ${i} in ${model_name}: ${vals}`);
                }
            }
            const index = ids.map((i) => vals[i]).join(" AND ");
            if (!records.has(index)) {
                records.set(index, {});
            }
            this._add_values(vals, model_name, index);
            if (_delete) {
                records.get(index)._DELETE = true;
            } else {
                delete records.get(index)._DELETE;
            }
        }
        return this;
    }

    _format_fields(fields) {
        if (fields === null || fields === undefined) {
            return [];
        } else if (
            typeof fields === "object" &&
            !Array.isArray(fields) &&
            !(fields instanceof StoreAttr)
        ) {
            fields = Object.entries(fields).map(
                ([key, value]) => new StoreAttr(makeKwArgs({ name: key, value })),
            );
        }
        if (!Array.isArray(fields)) {
            fields = [fields];
        }
        return fields;
    }

    _add_values(values, model_name, index) {
        const target = index
            ? this.data.get(model_name).get(index)
            : this.data.get(model_name);
        for (const [key, val] of Object.entries(values)) {
            if (key === "_DELETE") {
                throw new Error(`invalid key ${key} in ${model_name}: ${values}`);
            }
            if (val instanceof StoreRelation) {
                val._add_to_store(this, target, key);
            } else {
                target[key] = val;
            }
        }
    }

    get_result() {
        const res = {};
        for (const [model_name, records] of this.data) {
            const ids = ids_by_model[model_name] || ["id"];
            if (!ids.length) {
                res[model_name] = { ...records };
            } else {
                res[model_name] = [...records.values()].map((record) => ({
                    ...record,
                }));
            }
        }
        return res;
    }

    resolve_data_request(values) {
        if (this.data_id) {
            this._add_model_values("DataResponse", {
                id: this.data_id,
                _resolve: true,
                ...values,
            });
        }
        return this;
    }

    toJSON() {
        throw Error(
            "Converting Store to JSON is not supported, you might want to call 'get_result()' instead.",
        );
    }

    static many(records, fields, mode = "REPLACE", as_thread, kwargs) {
        let otherKwArgs;
        [kwargs, otherKwArgs] = extractAndDeleteKwArgs(
            arguments,
            "records",
            "fields",
            "mode",
            "as_thread",
        );
        records = kwargs.records;
        fields = kwargs.fields;
        mode = kwargs.mode ?? "REPLACE";
        as_thread = kwargs.as_thread;
        return new StoreMany(
            records,
            makeKwArgs({
                fields: fields,
                mode,
                as_thread,
                ...otherKwArgs,
            }),
        );
    }

    static one(records, fields, as_thread, kwargs) {
        let otherKwArgs;
        [kwargs, otherKwArgs] = extractAndDeleteKwArgs(
            arguments,
            "records",
            "fields",
            "as_thread",
        );
        records = kwargs.records;
        fields = kwargs.fields;
        as_thread = kwargs.as_thread;
        return new StoreOne(
            records,
            makeKwArgs({
                fields: fields,
                as_thread,
                ...otherKwArgs,
            }),
        );
    }

    static attr(name, value, predicate) {
        [{ name, value, predicate }] = extractAndDeleteKwArgs(
            arguments,
            "name",
            "value",
            "predicate",
        );
        return new StoreAttr(makeKwArgs({ name, value, predicate }));
    }
}

export const mailDataHelpers = {
    _process_request_for_all,
    _process_request_for_internal_user,
    Store,
};
