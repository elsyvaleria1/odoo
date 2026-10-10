declare module "models" {
    import { ChannelMember as ChannelMemberClass } from "@mail/discuss/core/common/channel_member_model";
    import { DiscussChannel as DiscussChannelClass } from "@mail/discuss/core/common/discuss_channel_model";

    export interface ChannelMember extends ChannelMemberClass {}
    export interface ChannelTypePolicy {
        allows_seen_infos: boolean;
        allows_unfollow: boolean;
        describes_as_channel: boolean;
        email_invite: "never" | "always" | "public_only";
        has_description: boolean;
        lazy_loads_members: boolean;
        member_based_naming: boolean;
        mentionable_by_hashtag: boolean;
        notify_opted_in_only: boolean;
        supports_sub_channels: boolean;
    }
    export interface DiscussChannel extends DiscussChannelClass, Thread {}

    export interface MailGuest {
        channelMembers: ChannelMember[];
    }
    export interface Message {
        channelMemberHaveSeen: Readonly<ChannelMember[]>;
        readonly hasEveryoneSeen: boolean;
        hasNewMessageSeparator: boolean;
        readonly hasSomeoneFetched: boolean;
        readonly hasSomeoneSeen: boolean;
        readonly isMessagePreviousToLastSelfMessageSeenByEveryone: boolean;
        threadAsFirstUnread: DiscussChannel;
    }
    export interface ResPartner {
        channelMembers: ChannelMember[];
    }
    export interface Store {
        channel_type_policies: Record<string, ChannelTypePolicy>;
        channelIdsFetchingDeferred: Map<number, Deferred>;
        createGroupChat: (param0: {
            default_display_mode?: string;
            partners_to: number[];
            name?: string;
        }) => Promise<DiscussChannel>;
        "discuss.channel.member": StaticMailRecord<
            ChannelMember,
            typeof ChannelMemberClass
        >;
        fetchChannel: (
            channelId: number,
            options?: { withLastMessage?: boolean },
        ) => Promise<void>;
        getRecentChatPartnerIds: () => number[];
        onlineMemberStatuses: Readonly<string[]>;
        sortMembers: (m1: ChannelMember, m2: ChannelMember) => number;
        startChat: (partnerIds: number[]) => Promise<void>;
        updateBusSubscription: (() => unknown) & { cancel: () => void };
    }
    export interface DiscussChannel {
        canRestoreInChatHub: Readonly<boolean>;
        notifyAvatarToServer(data: string): Promise<void>;
        notifyDescriptionToServer(description: string): Promise<void>;
        _setupMembershipFields(): void;
        _setupSeenStateFields(): void;
        _setupChannelStateFields(): void;
        _computeFirstUnreadMessage(): Message | null;
        _computeLastMessageSeenByAllId(): number | string | undefined;
        _maxMessageIdByOthers(
            fieldName: "seen_message_id" | "fetched_message_id",
        ): number;
        _computeMaxSeenMessageIdByOthers(): number;
        _computeMaxFetchedMessageIdByOthers(): number;
        _computeLastSelfMessageSeenByEveryone(): Message | false | undefined;
        _computeOfflineMembers(): ChannelMember[];
        allow_invite_by_email: Readonly<boolean>;
        allowedToUnpinChannelTypes: Readonly<string[]>;
        areAllMembersLoaded: Readonly<boolean>;
        avatar_cache_key: string;
        channel_member_ids: ChannelMember[];
        channel_name_member_ids: ChannelMember[];
        channel_type: string;
        computeCorrespondent: () => ChannelMember;
        correspondent: ChannelMember;
        correspondentCountry: Country;
        correspondents: Readonly<ChannelMember[]>;
        default_display_mode: "video_full_screen" | undefined;
        executeCommand: (
            command: import("@mail/discuss/core/common/channel_commands").ChannelCommand,
            body?: string,
        ) => Promise<any>;
        fetchChannelInfoState: "not_fetched" | "fetching" | "fetched";
        fetchChannelMembers: () => Promise<void>;
        fetchMoreAttachments: (limit?: number) => Promise<void>;
        firstUnreadMessage: Message;
        group_ids: ResGroups[];
        has_mail_thread: boolean | undefined;
        has_meeting_today: boolean;
        hasMemberList: Readonly<boolean>;
        isMeetingOrMeetingChild: Readonly<boolean>;
        isMultiMemberChannel: Readonly<boolean>;
        isMuted: Readonly<boolean>;
        isVideoCall: Readonly<boolean>;
        hasOtherMembersTyping: boolean;
        hasSeenFeature: boolean;
        hasSelfAsMember: Readonly<boolean>;
        invited_member_ids: ChannelMember[];
        last_interest_dt: Temporal.ZonedDateTime;
        lastInterestDt: Temporal.ZonedDateTime;
        lastMessageSeenByAllId: undefined | number;
        lastSelfMessageSeenByEveryone: Message;
        meeting_start_dt: Temporal.ZonedDateTime;
        meeting_stop_dt: Temporal.ZonedDateTime;
        leaveChannel: (options?: { force?: boolean }) => Promise<boolean>;
        markAsFetched: () => Promise<void>;
        markedAsUnread: boolean;
        markingAsRead: boolean;
        markReadSequential: ReturnType<
            typeof import("@mail/utils/common/misc").makeSequential
        >;
        maxFetchedMessageIdByOthers: number;
        maxSeenMessageIdByOthers: number;
        member_count: number | undefined;
        membersThatCanSeen: Readonly<ChannelMember[]>;
        name: string;
        offlineMembers: ChannelMember[];
        onlineMembers: ChannelMember[];
        openChannel: () => boolean;
        otherTypingMembers: ChannelMember[];
        scrollUnread: boolean;
        self_member_id: ChannelMember;
        shouldSubscribeToBusChannel: Readonly<boolean>;
        showCorrespondentCountry: Readonly<boolean>;
        showUnreadBanner: Readonly<boolean>;
        lastMemberBusSubscription:
            "not_member" | "member_before_start" | "member_after_start";
        memberBusSubscription:
            "not_member" | "member_before_start" | "member_after_start";
        typesAllowingCalls: Readonly<string[]>;
        typingMembers: ChannelMember[];
        unknownMembersCount: Readonly<number>;
    }

    export interface Models {
        "discuss.channel": DiscussChannel;
        "discuss.channel.member": ChannelMember;
    }
}
