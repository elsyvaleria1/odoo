declare module "models" {
    export interface Activity {
        isNoteEmpty: boolean;
        dateCreateFormatted: Readonly<string>;
        dateDeadlineFormatted: Readonly<string>;
        dateDoneFormatted: Readonly<string>;
        edit: () => Promise<void>;
        markAsDone: (attachmentIds: number[]) => Promise<void>;
        markAsDoneAndScheduleNext: () => Promise<ActionDescription>;
        markAsDoneWithFile: (file: {
            data: string;
            name: string;
            type: string;
        }) => Promise<boolean>;
        remove: (param0?: { broadcast?: boolean }) => void;
    }
    export interface Message {
        canForward: (thread: Thread) => boolean;
        canReplyAll: (thread: Thread) => boolean;
    }
    export interface MessagingMenu {
        bookmarkTab: MessagingMenuTab | undefined;
        notificationTab: MessagingMenuTab | undefined;
    }
    export interface Store {
        _onActivityBroadcastChannelMessage: (param0: {
            data:
                | {
                      type: "INSERT" | "DELETE";
                      payload: Partial<Activity>;
                  }
                | {
                      type: "RELOAD_CHATTER";
                      payload: { model: string; id: number };
                  };
        }) => void;
        activityBroadcastChannel: BroadcastChannel | null;
        activityCounter: number;
        activityCounter_bus_id: number;
        activityGroups: Object[];
        computeGlobalCounter: () => number;
        globalCounter: number;
        needaction_counter: number;
        needaction_counter_bus_id: number;
        onLinkFollowed: (fromThread: Thread) => void;
        onUpdateActivityGroups: () => void;
        addPendingNeedactionDone: (messageId: number) => void;
        pendingNeedactionDone: Map<number, number>;
        pendingStarToggles: Map<number, boolean[]>;
        takePendingNeedactionDone: (messageId: number) => boolean;
        scheduleActivity: (
            resModel: string | false,
            resIds: (number | string)[] | false,
            defaultActivityTypeId?: number,
        ) => Promise<void>;
        messagingMenuDropdown:
            | ReturnType<typeof import("@web/components/dropdown").useDropdownState>
            | undefined;
        messagingMenuSystrayState: MessagingMenuUIState;
        starred_counter: number;
        starred_counter_bus_id: number;
        unstarAll: () => Promise<void>;
        updateAppBadge: () => void;
    }
    export interface Thread {
        activities: Activity[];
        follow: () => Promise<void>;
        isDisplayedInDiscussAppDesktop: boolean;
        openRecordActionRequest: Readonly<ActionDescription>;
        loadMoreFollowers: () => Promise<void>;
        recipients: import("@mail/model/record_list").RecordList<Follower>;
    }
}
