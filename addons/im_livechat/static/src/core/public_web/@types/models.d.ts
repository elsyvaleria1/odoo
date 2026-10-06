declare module "models" {
    export interface DiscussApp {
        lastThread: Thread;
    }
    export interface LivechatChannel {
        threads: Thread[];
    }
    export interface MessagingMenu {
        isLivechatTabDisplayed: boolean;
        livechatChannelFilters: Readonly<MessagingMenuTabFilter[]>;
        livechatTab: MessagingMenuTab;
    }
    export interface DiscussChannel {
        country_id: Country;
        livechat_channel_id: LivechatChannel;
        livechat_expertise_ids: LivechatExpertise[];
        livechat_status: "in_progress" | "waiting" | "need_help" | undefined;
        matchesSelfExpertise: Readonly<boolean>;
        shadowedBySelf: number;
    }
}
