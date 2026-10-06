declare module "models" {
    import { DiscussApp as DiscussAppClass } from "@mail/core/public_web/discuss_app_model";

    export interface DiscussApp extends DiscussAppClass {}

    export interface Store {
        action_discuss_id: number | undefined;
        discuss: DiscussApp;
        DiscussApp: StaticMailRecord<DiscussApp, typeof DiscussAppClass>;
    }
    export interface Thread {
        askLeaveConfirmation: (body: string) => Promise<boolean>;
        autoOpenChatWindowOnNewMessage: Readonly<boolean>;
        inChathubOnNewMessage: Readonly<boolean>;
        notifyMessageToUser: (message: Message) => Promise<void>;
        notifyWhenOutOfFocus: Readonly<boolean>;
        revealInMessagingMenu: (state: MessagingMenuUIState) => void;
        setActiveURL: () => void;
        setAsDiscussThread: (pushState?: boolean) => void;
        unpin: () => Promise<void>;
    }

    export interface Models {
        DiscussApp: DiscussApp;
    }
}
