declare module "models" {
    export interface Message {
        pin: () => Deferred<boolean>;
        pinned_at: Temporal.ZonedDateTime;
        unpin: () => Deferred<boolean>;
    }
    export interface DiscussChannel {
        fetchPinnedMessages: () => Promise<void>;
        pinnedMessages: Message[];
        pinnedMessagesState: "loaded" | "loading" | "error" | undefined;
    }
}
