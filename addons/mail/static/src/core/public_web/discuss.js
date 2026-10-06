// @ts-check
/** @odoo-module native */
import { SIDEBAR_MIN_WIDTH } from "@mail/core/public_web/discuss_app_model";
import { DiscussContent } from "@mail/core/public_web/discuss_content";
import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { useMessageScrolling } from "@mail/utils/common/hooks";
import { provideMailContext } from "@mail/utils/common/mail_context";
import {
    Component,
    onMounted,
    onWillUnmount,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { ResizablePanel } from "@web/components/resizable_panel";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
const log = makeLogger("mail.discuss");

export class Discuss extends Component {
    static components = {
        DiscussContent,
        MessagingMenu,
        ResizablePanel,
    };
    static props = {
        hasSidebar: t.boolean().optional(true),
        thread: t.any().optional(),
    };
    static template = "mail.Discuss";
    props = useProps(this.constructor.props);

    sidebarMinWidth = SIDEBAR_MIN_WIDTH;
    toggleSidebar = () => {
        this.store.discuss.isSidebarCollapsed = !this.store.discuss.isSidebarCollapsed;
    };

    setup() {
        useLifecycleLog(log);
        super.setup();
        this.config = useViewConfig();
        this.store = useService("mail.store");
        this.messageHighlight = useMessageScrolling();
        this.root = elementRef();
        this.orm = useService("orm");
        this.effect = useService("effect");
        this.ui = useService("ui");
        provideMailContext({
            inDiscussApp: true,
            messageHighlight: this.messageHighlight,
        });
        useListener(
            window,
            "keydown",
            /** @param {KeyboardEvent} ev */
            (ev) => {
                if (
                    getActiveHotkey(ev) === "escape" &&
                    !this.thread?.composer?.isFocused
                ) {
                    if (this.thread?.composer) {
                        this.thread.composer.autofocus++;
                    }
                }
                if (getActiveHotkey(ev) === "control+k") {
                    this.store.env.services.command.openMainPalette({
                        searchValue: "@",
                    });
                    ev.preventDefault();
                    ev.stopPropagation();
                }
            },
            { capture: true },
        );
        if (this.store.inPublicPage) {
            useLayoutEffect(
                /**
                 * @param {import("models").Thread|undefined} thread
                 * @param {boolean} isSmall
                 */
                (thread, isSmall) => {
                    if (!thread) {
                        return;
                    }
                    log.logic("public page thread display", () => ({
                        thread: thread.localId,
                        isSmall,
                    }));
                    if (isSmall) {
                        const promise = (this._openChatWindowPromise = this.thread
                            .openChatWindow({ focus: true })
                            .then((chatWindow) => {
                                if (this._openChatWindowPromise === promise) {
                                    this.chatWindow = chatWindow;
                                } else {
                                    chatWindow?.close();
                                }
                            }));
                    } else {
                        this.chatWindow?.close();
                    }
                },
                () => [this.thread, this.ui.isSmall],
            );
        }
        onMounted(() => {
            document.body.classList.add("o_mail_discuss");
        });

        onWillUnmount(() => {
            document.body.classList.remove("o_mail_discuss");
        });
    }

    get thread() {
        return this.props.thread || this.store.discuss.thread;
    }
}
