// @ts-check
/** @odoo-module native */

import { registry } from "@web/core/registry";

import { ProofDialog } from "./proof_dialog/proof_dialog.js";

/**
 * @typedef {{ token: string, method: string, payload: Object }} Proof
 */

export const proofService = {
    dependencies: ["dialog"],
    /**
     * @param {any} env
     * @param {{ dialog: any }} services
     */
    start(env, { dialog }) {
        return {
            /**
             * Ask the user for a proof of identity answering the challenge in
             * ``params``, then hand it to ``submit``. A refusal the server raises
             * as a UserError is shown in the dialog and the user tries again;
             * resolves with what ``submit`` returned, or null when the user
             * cancels.
             *
             * @param {{ params: Object, submit: (proof: Proof) => Promise<any> }} request
             * @returns {Promise<any>}
             */
            request({ params, submit }) {
                return new Promise((resolve, reject) => {
                    let settled = false;
                    dialog.add(
                        ProofDialog,
                        {
                            params,
                            submit,
                            onProved: (/** @type {any} */ result) => {
                                settled = true;
                                resolve(result);
                            },
                            onFailed: (/** @type {any} */ error) => {
                                settled = true;
                                reject(error);
                            },
                        },
                        {
                            onClose: () => {
                                if (!settled) {
                                    resolve(null);
                                }
                            },
                        },
                    );
                });
            },
        };
    },
};

registry.category("services").add("proof", proofService);
