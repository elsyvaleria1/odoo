declare module "services" {
    import { voiceService } from "@voice_command/voice_service";

    export interface Services {
        voice: typeof voiceService;
    }
}
