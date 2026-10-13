/** @odoo-module native */
import { loader } from "@web/components/emoji_picker";
import { patch } from "@web/core/utils/patch";
import { url } from "@web/core/utils/urls";
import { session } from "@web/session";

patch(loader, {
    loadEmoji: () =>
        import(

            url("/im_livechat/emoji_bundle", undefined, {
                origin: session.livechatData.serverUrl,
            })
        ),
});
