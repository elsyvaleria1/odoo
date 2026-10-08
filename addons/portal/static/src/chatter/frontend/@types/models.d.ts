declare module "models" {
    export interface Composer {
        portalComment: boolean;
    }
    export interface Thread {
        can_post: boolean | undefined;
        hasReadAccess: boolean | undefined;
    }
}
