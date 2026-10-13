/** @odoo-module native */

import { toRaw } from "@odoo/owl";
import { SessionRecorder } from "@voip/core/session_recorder";
import { _t } from "@web/core/translation";

export class Session {
    /** @type {WeakSet<Session>} */
    static allSessions = new WeakSet();
    static get mediaConstraints() {
        const constraints = { audio: true, video: false };
        if (Session.preferredInputDevice) {
            constraints.audio = { deviceId: { exact: Session.preferredInputDevice } };
        }
        return constraints;
    }
    /** @type {string} */
    static preferredInputDevice = "";

    /** @type {string} */
    controlHandle = "";
    /** @type {import("@voip/core/call_service").CallService} */
    callService;
    /**
     * @type {"trying"|"ringing"|"ok"|undefined}
     */
    inviteState;
    /** @type {SessionRecorder} */
    recorder;
    /**
     * @type {HTMLAudioElement|null}
     */
    remoteAudio = null;
    /**
     * @type {boolean}
     */
    ringleader = false;
    /** @type {string|undefined} */
    transferTarget;
    /** @type {import("@voip/core/call_model").Call} */
    _call;
    /** @type {boolean} */
    _isOnHold = false;
    /** @type {boolean} */
    _isMuted = false;
    /**
     * @type {SIP.Session|null}
     */
    _sipSession = null;

    constructor(call, sipSession = null) {
        if (!call) {
            throw new Error("Required argument 'call' is missing.");
        }
        Session.allSessions.add(this);
        this._call = call;
        if (call.direction === "outgoing") {
            this.inviteState = "trying";
        }
        const services = call.store.env.services;
        this.callService = services["voip.call"];
        this.ringtones = services["voip.ringtone"];
        this.userAgent = services["voip.user_agent"];
        this.voip = services.voip;
        if (!sipSession) {
            return this;
        }
        sipSession.delegate = { onBye: () => this.callService.end(this.call) };
        sipSession.stateChange.addListener((state) =>
            this._onSessionStateChange(state),
        );
        this._sipSession = sipSession;
    }

    /** @type {import("@voip/core/call_model").Call} */
    get call() {
        return this._call;
    }

    get inviteRequestDelegate() {
        return {
            onAccept: (response) => this._onOutgoingInviteAccepted(response),
            onProgress: (response) => this._onOutgoingInviteProgress(response),
            onReject: (response) => this._onOutgoingInviteRejected(response),
        };
    }

    /**
     * @returns {boolean}
     */
    get isActiveSession() {
        return toRaw(this.userAgent.activeSession) === toRaw(this);
    }

    /** @returns {boolean} */
    get isOnHold() {
        return this._isOnHold;
    }

    /** @param {boolean} state */
    set isOnHold(state) {
        this._isOnHold = state;
        if (this.sipSession) {
            this._requestHold(state);
            this.updateTracks();
        }
    }

    /** @returns {boolean} */
    get isMuted() {
        return this._isMuted;
    }

    /** @param {boolean} state */
    set isMuted(state) {
        this._isMuted = state;
        this.updateTracks();
    }

    /** @returns {SIP.Session|null} */
    get sipSession() {
        return this._sipSession;
    }

    /** @returns {ReturnType<_t>|""} */
    get statusText() {
        if (this.isOnHold) {
            return _t("On hold");
        }
        if (this.voip.mode === "demo") {
            return _t("Demo call");
        }
        return _t("Calling…");
    }

    /**
     * @param {string} deviceId
     */
    static async switchInputDevice(deviceId) {
        Session.preferredInputDevice = deviceId;
        const stream = await navigator.mediaDevices.getUserMedia(
            Session.mediaConstraints,
        );
        for (const session of Session.allSessions) {
            const peerConnection =
                session.sipSession?.sessionDescriptionHandler.peerConnection;
            if (!peerConnection) {
                continue;
            }
            for (const sender of peerConnection.getSenders()) {
                if (sender.track) {
                    await sender.replaceTrack(stream.getAudioTracks()[0]);
                }
            }
            session.updateTracks();
        }
    }

    /**
     * @param {string} transferTarget
     */
    blindTransfer(transferTarget) {
        this.voip.softphone.addressBook.searchInputValue = "";
        if (!this.sipSession) {
            this.userAgent.hangup({ session: this });
            return;
        }
        this.sipSession.refer(this.userAgent.makeUri(transferTarget), {
            requestDelegate: {
                onAccept: (response) => {
                    this.userAgent.hangup({ session: this });
                },
            },
        });
    }

    record() {
        if (this.recorder) {
            console.warn(
                "Session.record() called on a session that already had a recorder.",
            );
            return;
        }
        if (!this.sipSession) {
            return;
        }
        const recorder = new SessionRecorder(this.sipSession);
        this.recorder = recorder;
        recorder.start();
        recorder.file.then((recording) =>
            SessionRecorder.upload(
                `/voip/upload_recording/${this.call.id}`,
                recording,
                {
                    fields: { start_ms: 0, end_ms: recorder.durationMs },
                },
            ),
        );
    }

    updateTracks() {
        const sessionDescriptionHandler = this.sipSession?.sessionDescriptionHandler;
        if (!sessionDescriptionHandler?.peerConnection) {
            return;
        }
        sessionDescriptionHandler.enableReceiverTracks(!this.isOnHold);
        sessionDescriptionHandler.enableSenderTracks(!this.isOnHold && !this.isMuted);
    }

    _cleanUpRemoteAudio() {
        if (!this.remoteAudio) {
            return;
        }
        this.remoteAudio.pause();
        this.remoteAudio.srcObject.getTracks().forEach((track) => track.stop());
        this.remoteAudio.srcObject = null;
        this.remoteAudio.load();
        this.remoteAudio = null;
    }

    /** @param {SIP.IncomingRequestMessage} message */
    _onIncomingInviteCanceled() {
        if (this.isActiveSession) {
            this.ringtones.stopPlaying();
            this.voip.softphone.activeTab = "recent";
        }
        this.sipSession.reject({ statusCode: 487 });
        this.callService.miss(this.call);
    }

    /** @param {SIP.IncomingResponse} response */
    _onOutgoingInviteAccepted(response) {
        this.inviteState = "ok";
        if (this.isActiveSession) {
            this.ringtones.stopPlaying();
        }
        if (this.voip.willCallFromAnotherDevice) {
            this.blindTransfer(this.transferTarget);
            return;
        }
        this.callService.start(this.call, { sipCallId: response?.message?.callId });
    }

    /**
     * @param {SIP.IncomingResponse} response
     */
    _onOutgoingInviteProgress(response) {
        const { statusCode } = response.message;
        if (statusCode === 183 || statusCode === 180) {
            if (this.isActiveSession) {
                this.ringtones.ringback.play();
            }
            this.inviteState = "ringing";
        }
    }

    /**
     * @param {SIP.IncomingResponse} response
     */
    _onOutgoingInviteRejected(response) {
        if (this.isActiveSession) {
            this.ringtones.stopPlaying();
        }
        if (response.message.statusCode === 487) {
            return;
        }
        const errorMessage = (() => {
            switch (response.message.statusCode) {
                case 404:
                case 488:
                case 603:
                    return _t(
                        "The number is incorrect, the user credentials could be wrong or the connection cannot be made. Please check your configuration.\n(Reason received: %(reasonPhrase)s)",
                        { reasonPhrase: response.message.reasonPhrase },
                    );
                case 486:
                case 600:
                    return _t(
                        "The person you try to contact is currently unavailable.",
                    );
                default:
                    return _t("Call rejected (reason: “%(reasonPhrase)s”)", {
                        reasonPhrase: response.message.reasonPhrase,
                    });
            }
        })();
        this.voip.triggerError(errorMessage, { isNonBlocking: true });
        this.callService.reject(this.call);
    }

    _onSessionEstablished() {
        this._setUpRemoteAudio();
        this.sipSession.sessionDescriptionHandler.remoteMediaStream.onaddtrack = (
            mediaStreamTrackEvent,
        ) => this._setUpRemoteAudio();
        if (this.voip.recordingPolicy === "always") {
            this.record();
        }
    }

    /** @param {SIP.SessionState} newState */
    _onSessionStateChange(newState) {
        switch (newState) {
            case SIP.SessionState.Initial:
                break;
            case SIP.SessionState.Establishing:
                break;
            case SIP.SessionState.Established:
                this._onSessionEstablished();
                break;
            case SIP.SessionState.Terminating:
                break;
            case SIP.SessionState.Terminated: {
                this._onSessionTerminated();
                break;
            }
            default:
                throw new Error(`Unknown session state: "${newState}".`);
        }
    }

    _onSessionTerminated() {
        this._cleanUpRemoteAudio();
    }

    /** @param {boolean} state */
    async _requestHold(state) {
        try {
            await this.sipSession.invite({
                requestDelegate: {
                    onAccept: () => {
                        this._isOnHold = state;
                    },
                },
                sessionDescriptionHandlerOptions: { hold: state },
            });
        } catch (error) {
            console.error(error);
            let errorMessage;
            if (state === true) {
                errorMessage = _t("Error putting the call on hold:");
            } else {
                errorMessage = _t("Error resuming the call:");
            }
            errorMessage += "\n\n" + error.message;
            this.voip.triggerError(errorMessage, { isNonBlocking: true });
        }
    }

    _setUpRemoteAudio() {
        const remoteAudio = new Audio();
        const remoteStream = new MediaStream();
        const receivers =
            this.sipSession.sessionDescriptionHandler.peerConnection.getReceivers();
        for (const { track } of receivers) {
            if (track) {
                remoteStream.addTrack(track);
            }
        }
        this.updateTracks();
        remoteAudio.srcObject = remoteStream;
        this._cleanUpRemoteAudio();
        this.remoteAudio = remoteAudio;
        remoteAudio.play();
    }
}
