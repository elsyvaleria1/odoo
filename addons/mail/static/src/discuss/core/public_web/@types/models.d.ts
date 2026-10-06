declare module "models" {
    export interface Message {
        linkedSubChannel: DiscussChannel;
    }
    export interface MessagingMenu {
        channelTab: MessagingMenuTab;
        chatTab: MessagingMenuTab;
        meetingTab: MessagingMenuTab;
    }
    export interface MessagingMenuTab {
        channels: DiscussChannel[];
        channelTypes: string[];
        compareChannels?: (c1: DiscussChannel, c2: DiscussChannel) => number;
        hasChannelKind: (channel: DiscussChannel) => boolean;
        holdsChannel: (channel: DiscussChannel) => boolean;
        channelsWithCounter: DiscussChannel[];
        counterChannelsToResolve: DiscussChannel[];
        _resolveCounterChannel: (channel: DiscussChannel) => Promise<void>;
        getSortedChannels: (filters?: MessagingMenuTabFilter[]) => DiscussChannel[];
        includesChannel: (channel: DiscussChannel) => boolean;
    }
    export interface MessagingMenuTabFilter {
        compareChannels?: (c1: DiscussChannel, c2: DiscussChannel) => number;
        includesChannel?: (channel: DiscussChannel) => boolean;
    }
    export interface Store {
        most_popular_channels: DiscussChannel[];
        mostPopularChannelsFetcher: ReturnType<Store["makeCachedFetchData"]>;
        fetchSearchConversationsSequential: ReturnType<
            typeof import("@mail/utils/common/misc").makeSequential
        >;
        searchConversations: (searchValue: string) => Promise<
            | {
                  channel_ids: number[];
                  mentioned_channel_ids?: number[];
                  recent_channel_ids?: number[];
              }
            | undefined
        >;
    }
    export interface DiscussChannel {
        _computeMessagingMenuTabsWithCounter: () => MessagingMenuTab[];
        joinAndPin: () => Promise<void>;
        last_message_fetched: boolean;
        messagingMenuTabs: MessagingMenuTab[];
        messagingMenuTabsWithCounter: MessagingMenuTab[];
        primaryMessagingMenuTab: MessagingMenuTab | undefined;
        typeMessagingMenuTab: MessagingMenuTab | undefined;
        createSubChannel: (param0?: {
            initialMessage?: Message;
            name?: string;
        }) => Promise<void>;
        from_message_id: Message;
        hasSubChannelFeature: Readonly<boolean>;
        lastSearchSubChannelLoaded: Thread | null;
        lastSubChannelLoaded: Thread | null;
        loadMoreSubChannels: (param0?: {
            searchTerm?: string;
        }) => Promise<Thread[] | undefined>;
        loadSubChannelsDone: boolean;
        searchSubChannelsDone: boolean;
        subChannelSearchTerm: string;
        parent_channel_id: DiscussChannel;
        sub_channel_ids: DiscussChannel[];
    }
}
