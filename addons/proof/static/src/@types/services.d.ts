declare module "services" {
    import { proofService } from "@proof/proof_service";

    export interface Services {
        proof: typeof proofService;
    }
}
