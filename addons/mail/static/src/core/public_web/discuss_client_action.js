// @ts-check
/** @odoo-module native */
import { Discuss } from "@mail/core/public_web/discuss";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    status,
    useProps,
} from "@odoo/owl";
import { router } from "@web/core/browser/router";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("mail.discuss");
/**
 * @typedef {Object} Props
 * @property {Object} action
 * @property {Object} action.context
 * @property {number} [action.context.active_id]
 * @property {string} [action.context.call]
 * @property {Object} [action.params]
 * @property {string | number} [action.params.active_id]
 * @property {string} [action.params.call]
 * @property {number} [action.params.highlight_message_id]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class DiscussClientAction extends Component {
    static components = { Discuss };
    static props = null;
    static template = "mail.DiscussClientAction";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.ui = useService("ui");
        this.store = useService("mail.store");
        onWillStart(() => {
            this.restoreDiscussThread(this.props);
        });
        onWillUpdateProps(
            /** @param {{action: Object}} nextProps */ (nextProps) => {
                this.restoreDiscussThread(nextProps);
            },
        );
        onMounted(() => {
            log.lifecycle("discuss active");
            this.store.discuss.isActive = true;
            if (this.pendingHighlight) {
                const { thread, message } = this.pendingHighlight;
                this.pendingHighlight = null;
                thread.highlightMessage = message;
            }
        });
        onWillUnmount(() => {
            log.lifecycle("discuss inactive");
            this.store.discuss.isActive = false;
        });
    }

    /**
     * @param {{action: Object}} props
     * @returns {string|number|undefined}
     */
    getActiveId(props) {
        return (
            props.action.context.active_id ??
            props.action.params?.active_id ??
            this.store.Thread.localIdToActiveId(this.store.discuss.thread?.localId) ??
            (this.ui.isSmall ? undefined : this.store.discuss.lastActiveId)
        );
    }

    /**
     * @param {string | number} [rawActiveId]
     * @returns {[string, string | number, {showAll?: boolean}?] | undefined}
     */
    parseActiveId(rawActiveId) {
        if (!rawActiveId) {
            return undefined;
        }
        if (typeof rawActiveId === "number") {
            return ["discuss.channel", rawActiveId];
        }
        const [model, id] = rawActiveId.split("_");
        if (model === "mail.box") {
            return id === "starred"
                ? ["discuss.tab", "bookmark"]
                : ["discuss.tab", "notification", { showAll: id === "history" }];
        }
        if (model === "discuss.tab") {
            return [model, id];
        }
        return [model, parseInt(id)];
    }

    /** @param {Props} props */
    async restoreDiscussThread(props) {
        const token = (this._restoreToken = (this._restoreToken ?? 0) + 1);
        const rawActiveId = this.getActiveId(props);
        const parsedActiveId = this.parseActiveId(rawActiveId);
        log.pipeline("restoreDiscussThread", () => ({
            token,
            rawActiveId,
            parsedActiveId,
        }));
        if (!parsedActiveId) {
            this.store.discuss.thread = undefined;
            this.store.discuss.hasRestoredThread = true;
            const sidebarState = this.store.discuss.sidebarState;
            const shownTab = sidebarState.selectedTab;
            await this.store.fetchStoreData("odoobot_chat");
            if (
                token !== this._restoreToken ||
                this.store.discuss.thread ||
                sidebarState.selectedTab?.notEq(shownTab)
            ) {
                return;
            }
            const odoobotChat = this.store.odoobot?.searchChat();
            const selfMember = odoobotChat?.self_member_id;
            if (odoobotChat && selfMember?.is_pinned && !selfMember.seen_message_id) {
                odoobotChat.setAsDiscussThread(false);
            }
            return;
        }
        const [model, id, options] = parsedActiveId;
        if (model === "discuss.tab") {
            const tab = this.store.MessagingMenuTab.get(String(id));
            this.store.discuss.thread = undefined;
            if (tab) {
                this.store.discuss.sidebarState.showTab(
                    tab,
                    options?.showAll ? { filter: undefined } : undefined,
                );
            }
            this.store.discuss.hasRestoredThread = true;
            return;
        }
        const shownThread = this.store.discuss.thread;
        const activeThread = await this.store.Thread.getOrFetch({ model, id });
        if (token !== this._restoreToken) {
            log.logic("restoreDiscussThread superseded", () => ({
                token,
                current: this._restoreToken,
            }));
            return;
        }
        if (this.store.discuss.thread && this.store.discuss.thread.notEq(shownThread)) {
            log.logic("restoreDiscussThread overtaken", () => ({
                token,
                thread: this.store.discuss.thread?.localId,
            }));
            this.store.discuss.hasRestoredThread = true;
            return;
        }
        log.pipeline("restoreDiscussThread resolved", () => ({
            token,
            thread: activeThread?.localId,
            found: Boolean(activeThread),
        }));
        if (activeThread) {
            const highlight_message_id =
                props.action?.params?.highlight_message_id ||
                router.current.highlight_message_id;
            if (highlight_message_id) {
                const message = this.store["mail.message"].insert({
                    id: highlight_message_id,
                });
                if (status(this) === "mounted") {
                    activeThread.highlightMessage = message;
                } else {
                    this.pendingHighlight = { thread: activeThread, message };
                }
                delete props.action?.params?.highlight_message_id;
                delete router.current?.highlight_message_id;
            }
            if (activeThread.notEq(this.store.discuss.thread)) {
                activeThread.setAsDiscussThread(false);
            }
        }
        this.store.discuss.hasRestoredThread = true;
    }
}

registry.category("actions").add("mail.action_discuss", DiscussClientAction);
