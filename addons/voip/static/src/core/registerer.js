/** @odoo-module native */

import { _t } from "@web/core/translation";

export class Registerer {
    static EXPIRATION_INTERVAL = 600;
    state;
    __sipJsRegisterer;

    constructor(voip, sipJsUserAgent) {
        this.voip = voip;
        this.__sipJsRegisterer = new SIP.Registerer(sipJsUserAgent, {
            expires: Registerer.EXPIRATION_INTERVAL,
        });
        this.__sipJsRegisterer.stateChange.addListener((state) =>
            this._onStateChanged(state),
        );
        window.addEventListener("beforeunload", () => {
            voip.isUnloading = true;
            this.__sipJsRegisterer.unregister();
            setTimeout(() => {
                voip.isUnloading = false;
                voip.env.services["voip.user_agent"].attemptReconnection();
            }, 7_500);
        });
    }

    register() {
        this.__sipJsRegisterer.register({
            requestDelegate: {
                onReject: (response) => this._onRegistrationRejected(response),
            },
        });
    }

    /**
     * Triggered when receiving a response with status code 4xx, 5xx, or 6xx to
     * the REGISTER request.
     *
     * @param {SIP.IncomingResponse} response The server final response to the
     * REGISTER request.
     */
    _onRegistrationRejected(response) {
        const errorMessage = _t(
            "Registration rejected: %(statusCode)s %(reasonPhrase)s.",
            {
                statusCode: response.message.statusCode,
                reasonPhrase: response.message.reasonPhrase,
            },
        );
        const help = (() => {
            switch (response.message.statusCode) {
                case 401:
                    return _t(
                        "The server failed to authenticate you. Please have an administrator verify that you are reaching the right server (PBX server IP in the VoIP Provider Settings) and that the credentials in your user preferences are correct.",
                    );
                case 503:
                    return _t(
                        "The error may come from the transport layer. Please have an administrator verify the websocket server URL in the VoIP Provider Settings. If the problem persists, this is probably an issue with the server.",
                    );
                default:
                    return _t(
                        "Please try again later. If the problem persists, you may want to ask an administrator to check the configuration.",
                    );
            }
        })();
        this.voip.triggerError(`${errorMessage}\n\n${help}`);
    }

    _onStateChanged(newState) {
        this.state = newState;
        if (newState === SIP.RegistererState.Registered) {
            this.voip.resolveError();
        }
    }
}
