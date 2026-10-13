/*!
 *
 *  SIP version 0.21.2
 *  Copyright (c) 2014-2022 Junction Networks, Inc <http://www.onsip.com>
 *  Homepage: https://sipjs.com
 *  License: https://sipjs.com/license/
 *
 *
 *  ~~~SIP.js contains substantial portions of JsSIP under the following license~~~
 *  Homepage: http://jssip.net
 *  Copyright (c) 2012-2013 José Luis Millán - Versatica <http://www.versatica.com>
 *
 *  Permission is hereby granted, free of charge, to any person obtaining
 *  a copy of this software and associated documentation files (the
 *  "Software"), to deal in the Software without restriction, including
 *  without limitation the rights to use, copy, modify, merge, publish,
 *  distribute, sublicense, and/or sell copies of the Software, and to
 *  permit persons to whom the Software is furnished to do so, subject to
 *  the following conditions:
 *
 *  The above copyright notice and this permission notice shall be
 *  included in all copies or substantial portions of the Software.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 *  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 *  MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 *  NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 *  LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 *  OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 *  WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 *
 *  ~~~ end JsSIP license ~~~
 *
 *
 *
 *
 */
(function webpackUniversalModuleDefinition(root, factory) {
	if(typeof exports === 'object' && typeof module === 'object')
		module.exports = factory();
	else if(typeof define === 'function' && define.amd)
		define([], factory);
	else if(typeof exports === 'object')
		exports["SIP"] = factory();
	else
		root["SIP"] = factory();
})(this, () => {
return  (() => {
	"use strict";
	var __webpack_modules__ = ([
,
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "LIBRARY_VERSION": () => ( LIBRARY_VERSION)
 });
const LIBRARY_VERSION = "0.21.2";


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Ack": () => ( _ack_js__WEBPACK_IMPORTED_MODULE_1__.Ack),
   "Bye": () => ( _bye_js__WEBPACK_IMPORTED_MODULE_2__.Bye),
   "Cancel": () => ( _cancel_js__WEBPACK_IMPORTED_MODULE_3__.Cancel),
   "ContentTypeUnsupportedError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_0__.ContentTypeUnsupportedError),
   "EmitterImpl": () => ( _emitter_js__WEBPACK_IMPORTED_MODULE_4__.EmitterImpl),
   "Info": () => ( _info_js__WEBPACK_IMPORTED_MODULE_5__.Info),
   "Invitation": () => ( _invitation_js__WEBPACK_IMPORTED_MODULE_6__.Invitation),
   "Inviter": () => ( _inviter_js__WEBPACK_IMPORTED_MODULE_7__.Inviter),
   "Message": () => ( _message_js__WEBPACK_IMPORTED_MODULE_8__.Message),
   "Messager": () => ( _messager_js__WEBPACK_IMPORTED_MODULE_9__.Messager),
   "Notification": () => ( _notification_js__WEBPACK_IMPORTED_MODULE_10__.Notification),
   "Publisher": () => ( _publisher_js__WEBPACK_IMPORTED_MODULE_12__.Publisher),
   "PublisherState": () => ( _publisher_state_js__WEBPACK_IMPORTED_MODULE_11__.PublisherState),
   "Referral": () => ( _referral_js__WEBPACK_IMPORTED_MODULE_13__.Referral),
   "Registerer": () => ( _registerer_js__WEBPACK_IMPORTED_MODULE_15__.Registerer),
   "RegistererState": () => ( _registerer_state_js__WEBPACK_IMPORTED_MODULE_14__.RegistererState),
   "RequestPendingError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_0__.RequestPendingError),
   "SIPExtension": () => ( _user_agent_options_js__WEBPACK_IMPORTED_MODULE_22__.SIPExtension),
   "Session": () => ( _session_js__WEBPACK_IMPORTED_MODULE_17__.Session),
   "SessionDescriptionHandlerError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_0__.SessionDescriptionHandlerError),
   "SessionState": () => ( _session_state_js__WEBPACK_IMPORTED_MODULE_16__.SessionState),
   "SessionTerminatedError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_0__.SessionTerminatedError),
   "StateTransitionError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_0__.StateTransitionError),
   "Subscriber": () => ( _subscriber_js__WEBPACK_IMPORTED_MODULE_18__.Subscriber),
   "Subscription": () => ( _subscription_js__WEBPACK_IMPORTED_MODULE_20__.Subscription),
   "SubscriptionState": () => ( _subscription_state_js__WEBPACK_IMPORTED_MODULE_19__.SubscriptionState),
   "TransportState": () => ( _transport_state_js__WEBPACK_IMPORTED_MODULE_21__.TransportState),
   "UserAgent": () => ( _user_agent_js__WEBPACK_IMPORTED_MODULE_24__.UserAgent),
   "UserAgentRegisteredOptionTags": () => ( _user_agent_options_js__WEBPACK_IMPORTED_MODULE_22__.UserAgentRegisteredOptionTags),
   "UserAgentState": () => ( _user_agent_state_js__WEBPACK_IMPORTED_MODULE_23__.UserAgentState)
 });
 var _exceptions_index_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(3);
 var _ack_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(10);
 var _bye_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(11);
 var _cancel_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(12);
 var _emitter_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(13);
 var _info_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(14);
 var _invitation_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(15);
 var _inviter_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(38);
 var _message_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(32);
 var _messager_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(39);
 var _notification_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(33);
 var _publisher_state_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(40);
 var _publisher_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(41);
 var _referral_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(34);
 var _registerer_state_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(42);
 var _registerer_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(43);
 var _session_state_js__WEBPACK_IMPORTED_MODULE_16__ = __webpack_require__(17);
 var _session_js__WEBPACK_IMPORTED_MODULE_17__ = __webpack_require__(16);
 var _subscriber_js__WEBPACK_IMPORTED_MODULE_18__ = __webpack_require__(44);
 var _subscription_state_js__WEBPACK_IMPORTED_MODULE_19__ = __webpack_require__(46);
 var _subscription_js__WEBPACK_IMPORTED_MODULE_20__ = __webpack_require__(45);
 var _transport_state_js__WEBPACK_IMPORTED_MODULE_21__ = __webpack_require__(48);
 var _user_agent_options_js__WEBPACK_IMPORTED_MODULE_22__ = __webpack_require__(35);
 var _user_agent_state_js__WEBPACK_IMPORTED_MODULE_23__ = __webpack_require__(49);
 var _user_agent_js__WEBPACK_IMPORTED_MODULE_24__ = __webpack_require__(50);


























































 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ContentTypeUnsupportedError": () => ( _content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_0__.ContentTypeUnsupportedError),
   "RequestPendingError": () => ( _request_pending_js__WEBPACK_IMPORTED_MODULE_1__.RequestPendingError),
   "SessionDescriptionHandlerError": () => ( _session_description_handler_js__WEBPACK_IMPORTED_MODULE_2__.SessionDescriptionHandlerError),
   "SessionTerminatedError": () => ( _session_terminated_js__WEBPACK_IMPORTED_MODULE_3__.SessionTerminatedError),
   "StateTransitionError": () => ( _state_transition_js__WEBPACK_IMPORTED_MODULE_4__.StateTransitionError)
 });
 var _content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(4);
 var _request_pending_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(6);
 var _session_description_handler_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(7);
 var _session_terminated_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(8);
 var _state_transition_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(9);







 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ContentTypeUnsupportedError": () => ( ContentTypeUnsupportedError)
 });
 var _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class ContentTypeUnsupportedError extends _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    constructor(message) {
        super(message ? message : "Unsupported content type.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Exception": () => ( Exception)
 });
/** @public */
class Exception extends Error {
    constructor(message) {
        super(message);
        Object.setPrototypeOf(this, new.target.prototype);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "RequestPendingError": () => ( RequestPendingError)
 });
 var _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class RequestPendingError extends _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    /** @internal */
    constructor(message) {
        super(message ? message : "Request pending.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionDescriptionHandlerError": () => ( SessionDescriptionHandlerError)
 });
 var _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class SessionDescriptionHandlerError extends _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    constructor(message) {
        super(message ? message : "Unspecified session description handler error.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionTerminatedError": () => ( SessionTerminatedError)
 });
 var _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class SessionTerminatedError extends _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    constructor() {
        super("The session has terminated.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "StateTransitionError": () => ( StateTransitionError)
 });
 var _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class StateTransitionError extends _core_exceptions_exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    constructor(message) {
        super(message ? message : "An error occurred during state transition.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Ack": () => ( Ack)
 });
/** @public */
class Ack {
    /** @internal */
    constructor(incomingAckRequest) {
        this.incomingAckRequest = incomingAckRequest;
    }
    get request() {
        return this.incomingAckRequest.message;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Bye": () => ( Bye)
 });
/** @public */
class Bye {
    /** @internal */
    constructor(incomingByeRequest) {
        this.incomingByeRequest = incomingByeRequest;
    }
    get request() {
        return this.incomingByeRequest.message;
    }
    accept(options) {
        this.incomingByeRequest.accept(options);
        return Promise.resolve();
    }
    reject(options) {
        this.incomingByeRequest.reject(options);
        return Promise.resolve();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Cancel": () => ( Cancel)
 });
/** @public */
class Cancel {
    /** @internal */
    constructor(incomingCancelRequest) {
        this.incomingCancelRequest = incomingCancelRequest;
    }
    get request() {
        return this.incomingCancelRequest;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "EmitterImpl": () => ( EmitterImpl)
 });
/** @internal */
class EmitterImpl {
    constructor() {
        this.listeners = new Array();
    }
    /**
     * @param listener
     * @param options
     */
    addListener(listener, options) {
        const onceWrapper = (data) => {
            this.removeListener(onceWrapper);
            listener(data);
        };
        (options === null || options === void 0 ? void 0 : options.once) === true ? this.listeners.push(onceWrapper) : this.listeners.push(listener);
    }
    /** @param data */
    emit(data) {
        this.listeners.slice().forEach((listener) => listener(data));
    }
    removeAllListeners() {
        this.listeners = [];
    }
    /** @param listener */
    removeListener(listener) {
        this.listeners = this.listeners.filter((l) => l !== listener);
    }
    /**
     * @param listener
     * @deprecated
     */
    on(listener) {
        return this.addListener(listener);
    }
    /**
     * @param listener
     * @deprecated
     */
    off(listener) {
        return this.removeListener(listener);
    }
    /**
     * @param listener
     * @deprecated
     */
    once(listener) {
        return this.addListener(listener, { once: true });
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Info": () => ( Info)
 });
/** @public */
class Info {
    /** @internal */
    constructor(incomingInfoRequest) {
        this.incomingInfoRequest = incomingInfoRequest;
    }
    get request() {
        return this.incomingInfoRequest.message;
    }
    accept(options) {
        this.incomingInfoRequest.accept(options);
        return Promise.resolve();
    }
    reject(options) {
        this.incomingInfoRequest.reject(options);
        return Promise.resolve();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Invitation": () => ( Invitation)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(22);
 var _core_messages_body_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(18);
 var _core_session_session_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(31);
 var _core_timers_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(37);
 var _core_exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(36);
 var _core_messages_utils_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(21);
 var _cancel_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(12);
 var _exceptions_content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(4);
 var _exceptions_session_description_handler_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(7);
 var _exceptions_session_terminated_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(8);
 var _session_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(16);
 var _session_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(17);
 var _user_agent_options_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(35);













/** @public */
class Invitation extends _session_js__WEBPACK_IMPORTED_MODULE_0__.Session {
    /** @internal */
    constructor(userAgent, incomingInviteRequest) {
        super(userAgent);
        this.incomingInviteRequest = incomingInviteRequest;
        this.disposed = false;
        this.expiresTimer = undefined;
        this.isCanceled = false;
        this.rel100 = "none";
        this.rseq = Math.floor(Math.random() * 10000);
        this.userNoAnswerTimer = undefined;
        this.waitingForPrack = false;
        this.logger = userAgent.getLogger("sip.Invitation");
        const incomingRequestMessage = this.incomingInviteRequest.message;
        const requireHeader = incomingRequestMessage.getHeader("require");
        if (requireHeader && requireHeader.toLowerCase().includes("100rel")) {
            this.rel100 = "required";
        }
        const supportedHeader = incomingRequestMessage.getHeader("supported");
        if (supportedHeader && supportedHeader.toLowerCase().includes("100rel")) {
            this.rel100 = "supported";
        }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        incomingRequestMessage.toTag = incomingInviteRequest.toTag;
        if (typeof incomingRequestMessage.toTag !== "string") {
            throw new TypeError("toTag should have been a string.");
        }
        this.userNoAnswerTimer = setTimeout(() => {
            incomingInviteRequest.reject({ statusCode: 480 });
            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated);
        }, this.userAgent.configuration.noAnswerTimeout ? this.userAgent.configuration.noAnswerTimeout * 1000 : 60000);
        if (incomingRequestMessage.hasHeader("expires")) {
            const expires = Number(incomingRequestMessage.getHeader("expires") || 0) * 1000;
            this.expiresTimer = setTimeout(() => {
                if (this.state === _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial) {
                    incomingInviteRequest.reject({ statusCode: 487 });
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated);
                }
            }, expires);
        }
        const assertedIdentity = this.request.getHeader("P-Asserted-Identity");
        if (assertedIdentity) {
            this._assertedIdentity = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.nameAddrHeaderParse(assertedIdentity);
        }
        this._contact = this.userAgent.contact.toString();
        const contentDisposition = incomingRequestMessage.parseHeader("Content-Disposition");
        if (contentDisposition && contentDisposition.type === "render") {
            this._renderbody = incomingRequestMessage.body;
            this._rendertype = incomingRequestMessage.getHeader("Content-Type");
        }
        this._id = incomingRequestMessage.callId + incomingRequestMessage.fromTag;
        this.userAgent._sessions[this._id] = this;
    }
    dispose() {
        if (this.disposed) {
            return Promise.resolve();
        }
        this.disposed = true;
        if (this.expiresTimer) {
            clearTimeout(this.expiresTimer);
            this.expiresTimer = undefined;
        }
        if (this.userNoAnswerTimer) {
            clearTimeout(this.userNoAnswerTimer);
            this.userNoAnswerTimer = undefined;
        }
        this.prackNeverArrived();
        switch (this.state) {
            case _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial:
                return this.reject().then(() => super.dispose());
            case _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Establishing:
                return this.reject().then(() => super.dispose());
            case _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Established:
                return super.dispose();
            case _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminating:
                return super.dispose();
            case _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated:
                return super.dispose();
            default:
                throw new Error("Unknown state.");
        }
    }
    get autoSendAnInitialProvisionalResponse() {
        return this.rel100 !== "required" && this.userAgent.configuration.sendInitialProvisionalResponse;
    }
    get body() {
        return this.incomingInviteRequest.message.body;
    }
    get localIdentity() {
        return this.request.to;
    }
    get remoteIdentity() {
        return this.request.from;
    }
    get request() {
        return this.incomingInviteRequest.message;
    }
    /**
     * @remarks
     * @param options
     */
    accept(options = {}) {
        this.logger.log("Invitation.accept");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial) {
            const error = new Error(`Invalid session state ${this.state}`);
            this.logger.error(error.message);
            return Promise.reject(error);
        }
        if (options.sessionDescriptionHandlerModifiers) {
            this.sessionDescriptionHandlerModifiers = options.sessionDescriptionHandlerModifiers;
        }
        if (options.sessionDescriptionHandlerOptions) {
            this.sessionDescriptionHandlerOptions = options.sessionDescriptionHandlerOptions;
        }
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Establishing);
        return (this.sendAccept(options)
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            .then(({ message, session }) => {
            session.delegate = {
                onAck: (ackRequest) => this.onAckRequest(ackRequest),
                onAckTimeout: () => this.onAckTimeout(),
                onBye: (byeRequest) => this.onByeRequest(byeRequest),
                onInfo: (infoRequest) => this.onInfoRequest(infoRequest),
                onInvite: (inviteRequest) => this.onInviteRequest(inviteRequest),
                onMessage: (messageRequest) => this.onMessageRequest(messageRequest),
                onNotify: (notifyRequest) => this.onNotifyRequest(notifyRequest),
                onPrack: (prackRequest) => this.onPrackRequest(prackRequest),
                onRefer: (referRequest) => this.onReferRequest(referRequest)
            };
            this._dialog = session;
            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Established);
            if (this._replacee) {
                this._replacee._bye();
            }
        })
            .catch((error) => this.handleResponseError(error)));
    }
    /**
     * @remarks
     * @param options
     */
    progress(options = {}) {
        this.logger.log("Invitation.progress");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial) {
            const error = new Error(`Invalid session state ${this.state}`);
            this.logger.error(error.message);
            return Promise.reject(error);
        }
        const statusCode = options.statusCode || 180;
        if (statusCode < 100 || statusCode > 199) {
            throw new TypeError("Invalid statusCode: " + statusCode);
        }
        if (options.sessionDescriptionHandlerModifiers) {
            this.sessionDescriptionHandlerModifiers = options.sessionDescriptionHandlerModifiers;
        }
        if (options.sessionDescriptionHandlerOptions) {
            this.sessionDescriptionHandlerOptions = options.sessionDescriptionHandlerOptions;
        }
        if (this.waitingForPrack) {
            this.logger.warn("Unexpected call for progress while waiting for prack, ignoring");
            return Promise.resolve();
        }
        if (options.statusCode === 100) {
            return this.sendProgressTrying()
                .then(() => {
                return;
            })
                .catch((error) => this.handleResponseError(error));
        }
        if (!(this.rel100 === "required") &&
            !(this.rel100 === "supported" && options.rel100) &&
            !(this.rel100 === "supported" && this.userAgent.configuration.sipExtension100rel === _user_agent_options_js__WEBPACK_IMPORTED_MODULE_3__.SIPExtension.Required)) {
            return this.sendProgress(options)
                .then(() => {
                return;
            })
                .catch((error) => this.handleResponseError(error));
        }
        return this.sendProgressReliableWaitForPrack(options)
            .then(() => {
            return;
        })
            .catch((error) => this.handleResponseError(error));
    }
    /**
     * @remarks
     * @param options
     */
    reject(options = {}) {
        this.logger.log("Invitation.reject");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial && this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Establishing) {
            const error = new Error(`Invalid session state ${this.state}`);
            this.logger.error(error.message);
            return Promise.reject(error);
        }
        const statusCode = options.statusCode || 480;
        const reasonPhrase = options.reasonPhrase ? options.reasonPhrase : (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_4__.getReasonPhrase)(statusCode);
        const extraHeaders = options.extraHeaders || [];
        if (statusCode < 300 || statusCode > 699) {
            throw new TypeError("Invalid statusCode: " + statusCode);
        }
        const body = options.body ? (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_5__.fromBodyLegacy)(options.body) : undefined;
        statusCode < 400
            ? this.incomingInviteRequest.redirect([], { statusCode, reasonPhrase, extraHeaders, body })
            : this.incomingInviteRequest.reject({ statusCode, reasonPhrase, extraHeaders, body });
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated);
        return Promise.resolve();
    }
    /**
     * @param message
     * @internal
     */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _onCancel(message) {
        this.logger.log("Invitation._onCancel");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial && this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Establishing) {
            this.logger.error(`CANCEL received while in state ${this.state}, dropping request`);
            return;
        }
        if (this.delegate && this.delegate.onCancel) {
            const cancel = new _cancel_js__WEBPACK_IMPORTED_MODULE_6__.Cancel(message);
            this.delegate.onCancel(cancel);
        }
        this.isCanceled = true;
        this.incomingInviteRequest.reject({ statusCode: 487 });
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated);
    }
    handlePrackOfferAnswer(request) {
        if (!this.dialog) {
            throw new Error("Dialog undefined.");
        }
        const body = (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_5__.getBody)(request.message);
        if (!body || body.contentDisposition !== "session") {
            return Promise.resolve(undefined);
        }
        const options = {
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions,
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers
        };
        switch (this.dialog.signalingState) {
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_7__.SignalingState.Initial:
                throw new Error(`Invalid signaling state ${this.dialog.signalingState}.`);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_7__.SignalingState.Stable:
                return this.setAnswer(body, options).then(() => undefined);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_7__.SignalingState.HaveLocalOffer:
                throw new Error(`Invalid signaling state ${this.dialog.signalingState}.`);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_7__.SignalingState.HaveRemoteOffer:
                return this.setOfferAndGetAnswer(body, options);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_7__.SignalingState.Closed:
                throw new Error(`Invalid signaling state ${this.dialog.signalingState}.`);
            default:
                throw new Error(`Invalid signaling state ${this.dialog.signalingState}.`);
        }
    }
    /** @param error */
    handleResponseError(error) {
        let statusCode = 480;
        if (error instanceof Error) {
            this.logger.error(error.message);
        }
        else {
            this.logger.error(error);
        }
        if (error instanceof _exceptions_content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_8__.ContentTypeUnsupportedError) {
            this.logger.error("A session description handler occurred while sending response (content type unsupported");
            statusCode = 415;
        }
        else if (error instanceof _exceptions_session_description_handler_js__WEBPACK_IMPORTED_MODULE_9__.SessionDescriptionHandlerError) {
            this.logger.error("A session description handler occurred while sending response");
        }
        else if (error instanceof _exceptions_session_terminated_js__WEBPACK_IMPORTED_MODULE_10__.SessionTerminatedError) {
            this.logger.error("Session ended before response could be formulated and sent (while waiting for PRACK)");
        }
        else if (error instanceof _core_exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_11__.TransactionStateError) {
            this.logger.error("Session changed state before response could be formulated and sent");
        }
        if (this.state === _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Initial || this.state === _session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Establishing) {
            try {
                this.incomingInviteRequest.reject({ statusCode });
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated);
            }
            catch (e) {
                this.logger.error("An error occurred attempting to reject the request while handling another error");
                throw e;
            }
        }
        if (this.isCanceled) {
            this.logger.warn("An error occurred while attempting to formulate and send a response to an incoming INVITE." +
                " However a CANCEL was received and processed while doing so which can (and often does) result" +
                " in errors occurring as the session terminates in the meantime. Said error is being ignored.");
            return;
        }
        throw error;
    }
    /** @param session */
    onAckTimeout() {
        this.logger.log("Invitation.onAckTimeout");
        if (!this.dialog) {
            throw new Error("Dialog undefined.");
        }
        this.logger.log("No ACK received for an extended period of time, terminating session");
        this.dialog.bye();
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated);
    }
    /** @param options */
    sendAccept(options = {}) {
        const responseOptions = {
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions,
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers
        };
        const extraHeaders = options.extraHeaders || [];
        if (this.waitingForPrack) {
            return this.waitForArrivalOfPrack()
                .then(() => clearTimeout(this.userNoAnswerTimer))
                .then(() => this.generateResponseOfferAnswer(this.incomingInviteRequest, responseOptions))
                .then((body) => this.incomingInviteRequest.accept({ statusCode: 200, body, extraHeaders }));
        }
        clearTimeout(this.userNoAnswerTimer);
        return this.generateResponseOfferAnswer(this.incomingInviteRequest, responseOptions).then((body) => this.incomingInviteRequest.accept({ statusCode: 200, body, extraHeaders }));
    }
    /** @param options */
    sendProgress(options = {}) {
        const statusCode = options.statusCode || 180;
        const reasonPhrase = options.reasonPhrase;
        const extraHeaders = (options.extraHeaders || []).slice();
        const body = options.body ? (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_5__.fromBodyLegacy)(options.body) : undefined;
        if (statusCode === 183 && !body) {
            return this.sendProgressWithSDP(options);
        }
        try {
            const progressResponse = this.incomingInviteRequest.progress({ statusCode, reasonPhrase, extraHeaders, body });
            this._dialog = progressResponse.session;
            return Promise.resolve(progressResponse);
        }
        catch (error) {
            return Promise.reject(error);
        }
    }
    /** @param options */
    sendProgressWithSDP(options = {}) {
        const responseOptions = {
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions,
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers
        };
        const statusCode = options.statusCode || 183;
        const reasonPhrase = options.reasonPhrase;
        const extraHeaders = (options.extraHeaders || []).slice();
        return this.generateResponseOfferAnswer(this.incomingInviteRequest, responseOptions)
            .then((body) => this.incomingInviteRequest.progress({ statusCode, reasonPhrase, extraHeaders, body }))
            .then((progressResponse) => {
            this._dialog = progressResponse.session;
            return progressResponse;
        });
    }
    /** @param options */
    sendProgressReliable(options = {}) {
        options.extraHeaders = (options.extraHeaders || []).slice();
        options.extraHeaders.push("Require: 100rel");
        options.extraHeaders.push("RSeq: " + Math.floor(Math.random() * 10000));
        return this.sendProgressWithSDP(options);
    }
    /** @param options */
    sendProgressReliableWaitForPrack(options = {}) {
        const responseOptions = {
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions,
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers
        };
        const statusCode = options.statusCode || 183;
        const reasonPhrase = options.reasonPhrase;
        const extraHeaders = (options.extraHeaders || []).slice();
        extraHeaders.push("Require: 100rel");
        extraHeaders.push("RSeq: " + this.rseq++);
        let body;
        return new Promise((resolve, reject) => {
            this.waitingForPrack = true;
            this.generateResponseOfferAnswer(this.incomingInviteRequest, responseOptions)
                .then((offerAnswer) => {
                body = offerAnswer;
                return this.incomingInviteRequest.progress({ statusCode, reasonPhrase, extraHeaders, body });
            })
                .then((progressResponse) => {
                this._dialog = progressResponse.session;
                let prackRequest;
                let prackResponse;
                progressResponse.session.delegate = {
                    onPrack: (request) => {
                        prackRequest = request;
                        // eslint-disable-next-line @typescript-eslint/no-use-before-define
                        clearTimeout(prackWaitTimeoutTimer);
                        // eslint-disable-next-line @typescript-eslint/no-use-before-define
                        clearTimeout(rel1xxRetransmissionTimer);
                        if (!this.waitingForPrack) {
                            return;
                        }
                        this.waitingForPrack = false;
                        this.handlePrackOfferAnswer(prackRequest)
                            .then((prackResponseBody) => {
                            try {
                                prackResponse = prackRequest.accept({ statusCode: 200, body: prackResponseBody });
                                this.prackArrived();
                                resolve({ prackRequest, prackResponse, progressResponse });
                            }
                            catch (error) {
                                reject(error);
                            }
                        })
                            .catch((error) => reject(error));
                    }
                };
                const prackWaitTimeout = () => {
                    if (!this.waitingForPrack) {
                        return;
                    }
                    this.waitingForPrack = false;
                    this.logger.warn("No PRACK received, rejecting INVITE.");
                    // eslint-disable-next-line @typescript-eslint/no-use-before-define
                    clearTimeout(rel1xxRetransmissionTimer);
                    this.reject({ statusCode: 504 })
                        .then(() => reject(new _exceptions_session_terminated_js__WEBPACK_IMPORTED_MODULE_10__.SessionTerminatedError()))
                        .catch((error) => reject(error));
                };
                const prackWaitTimeoutTimer = setTimeout(prackWaitTimeout, _core_timers_js__WEBPACK_IMPORTED_MODULE_12__.Timers.T1 * 64);
                const rel1xxRetransmission = () => {
                    try {
                        this.incomingInviteRequest.progress({ statusCode, reasonPhrase, extraHeaders, body });
                    }
                    catch (error) {
                        this.waitingForPrack = false;
                        reject(error);
                        return;
                    }
                    // eslint-disable-next-line @typescript-eslint/no-use-before-define
                    rel1xxRetransmissionTimer = setTimeout(rel1xxRetransmission, (timeout *= 2));
                };
                let timeout = _core_timers_js__WEBPACK_IMPORTED_MODULE_12__.Timers.T1;
                let rel1xxRetransmissionTimer = setTimeout(rel1xxRetransmission, timeout);
            })
                .catch((error) => {
                this.waitingForPrack = false;
                reject(error);
            });
        });
    }
    sendProgressTrying() {
        try {
            const progressResponse = this.incomingInviteRequest.trying();
            return Promise.resolve(progressResponse);
        }
        catch (error) {
            return Promise.reject(error);
        }
    }
    waitForArrivalOfPrack() {
        if (this.waitingForPrackPromise) {
            throw new Error("Already waiting for PRACK");
        }
        this.waitingForPrackPromise = new Promise((resolve, reject) => {
            this.waitingForPrackResolve = resolve;
            this.waitingForPrackReject = reject;
        });
        return this.waitingForPrackPromise;
    }
    prackArrived() {
        if (this.waitingForPrackResolve) {
            this.waitingForPrackResolve();
        }
        this.waitingForPrackPromise = undefined;
        this.waitingForPrackResolve = undefined;
        this.waitingForPrackReject = undefined;
    }
    prackNeverArrived() {
        if (this.waitingForPrackReject) {
            this.waitingForPrackReject(new _exceptions_session_terminated_js__WEBPACK_IMPORTED_MODULE_10__.SessionTerminatedError());
        }
        this.waitingForPrackPromise = undefined;
        this.waitingForPrackResolve = undefined;
        this.waitingForPrackReject = undefined;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Session": () => ( Session)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(22);
 var _grammar_uri_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(24);
 var _core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(18);
 var _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(31);
 var _core_messages_utils_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(21);
 var _core_user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(29);
 var _ack_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(10);
 var _bye_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(11);
 var _emitter_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(13);
 var _exceptions_content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(4);
 var _exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(6);
 var _info_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(14);
 var _message_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(32);
 var _notification_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(33);
 var _referral_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(34);
 var _session_state_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(17);
















/**
 * @remarks
 * @public
 */
class Session {
    /**
     * @param userAgent
     * @internal
     */
    constructor(userAgent, options = {}) {
        this.pendingReinvite = false;
        this.pendingReinviteAck = false;
        this._state = _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Initial;
        this.delegate = options.delegate;
        this._stateEventEmitter = new _emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this._userAgent = userAgent;
    }
    dispose() {
        this.logger.log(`Session ${this.id} in state ${this._state} is being disposed`);
        delete this.userAgent._sessions[this.id];
        if (this._sessionDescriptionHandler) {
            this._sessionDescriptionHandler.close();
        }
        switch (this.state) {
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Initial:
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Establishing:
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established:
                return new Promise((resolve) => {
                    this._bye({
                        onAccept: () => resolve(),
                        onRedirect: () => resolve(),
                        onReject: () => resolve()
                    });
                });
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating:
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated:
                break;
            default:
                throw new Error("Unknown state.");
        }
        return Promise.resolve();
    }
    get assertedIdentity() {
        return this._assertedIdentity;
    }
    get dialog() {
        return this._dialog;
    }
    get id() {
        return this._id;
    }
    get replacee() {
        return this._replacee;
    }
    get sessionDescriptionHandler() {
        return this._sessionDescriptionHandler;
    }
    get sessionDescriptionHandlerFactory() {
        return this.userAgent.configuration.sessionDescriptionHandlerFactory;
    }
    get sessionDescriptionHandlerModifiers() {
        return this._sessionDescriptionHandlerModifiers || [];
    }
    set sessionDescriptionHandlerModifiers(modifiers) {
        this._sessionDescriptionHandlerModifiers = modifiers.slice();
    }
    get sessionDescriptionHandlerOptions() {
        return this._sessionDescriptionHandlerOptions || {};
    }
    set sessionDescriptionHandlerOptions(options) {
        this._sessionDescriptionHandlerOptions = Object.assign({}, options);
    }
    get sessionDescriptionHandlerModifiersReInvite() {
        return this._sessionDescriptionHandlerModifiersReInvite || [];
    }
    set sessionDescriptionHandlerModifiersReInvite(modifiers) {
        this._sessionDescriptionHandlerModifiersReInvite = modifiers.slice();
    }
    get sessionDescriptionHandlerOptionsReInvite() {
        return this._sessionDescriptionHandlerOptionsReInvite || {};
    }
    set sessionDescriptionHandlerOptionsReInvite(options) {
        this._sessionDescriptionHandlerOptionsReInvite = Object.assign({}, options);
    }
    get state() {
        return this._state;
    }
    get stateChange() {
        return this._stateEventEmitter;
    }
    get userAgent() {
        return this._userAgent;
    }
    /** @param options */
    bye(options = {}) {
        let message = "Session.bye() may only be called if established session.";
        switch (this.state) {
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Initial:
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                if (typeof this.cancel === "function") {
                    message += " However Inviter.invite() has not yet been called.";
                    message += " Perhaps you should have called Inviter.cancel()?";
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                }
                else if (typeof this.reject === "function") {
                    message += " However Invitation.accept() has not yet been called.";
                    message += " Perhaps you should have called Invitation.reject()?";
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Establishing:
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                if (typeof this.cancel === "function") {
                    message += " However a dialog does not yet exist.";
                    message += " Perhaps you should have called Inviter.cancel()?";
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                }
                else if (typeof this.reject === "function") {
                    message += " However Invitation.accept() has not yet been called (or not yet resolved).";
                    message += " Perhaps you should have called Invitation.reject()?";
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established: {
                const requestDelegate = options.requestDelegate;
                const requestOptions = this.copyRequestOptions(options.requestOptions);
                return this._bye(requestDelegate, requestOptions);
            }
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating:
                message += " However this session is already terminating.";
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                if (typeof this.cancel === "function") {
                    message += " Perhaps you have already called Inviter.cancel()?";
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                }
                else if (typeof this.reject === "function") {
                    message += " Perhaps you have already called Session.bye()?";
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated:
                message += " However this session is already terminated.";
                break;
            default:
                throw new Error("Unknown state");
        }
        this.logger.error(message);
        return Promise.reject(new Error(`Invalid session state ${this.state}`));
    }
    /** @param options */
    info(options = {}) {
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            const message = "Session.info() may only be called if established session.";
            this.logger.error(message);
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        const requestDelegate = options.requestDelegate;
        const requestOptions = this.copyRequestOptions(options.requestOptions);
        return this._info(requestDelegate, requestOptions);
    }
    /** @param options */
    invite(options = {}) {
        this.logger.log("Session.invite");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        if (this.pendingReinvite) {
            return Promise.reject(new _exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_2__.RequestPendingError("Reinvite in progress. Please wait until complete, then try again."));
        }
        this.pendingReinvite = true;
        if (options.sessionDescriptionHandlerModifiers) {
            this.sessionDescriptionHandlerModifiersReInvite = options.sessionDescriptionHandlerModifiers;
        }
        if (options.sessionDescriptionHandlerOptions) {
            this.sessionDescriptionHandlerOptionsReInvite = options.sessionDescriptionHandlerOptions;
        }
        const delegate = {
            onAccept: (response) => {
                const body = (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__.getBody)(response.message);
                if (!body) {
                    this.logger.error("Received 2xx response to re-INVITE without a session description");
                    this.ackAndBye(response, 400, "Missing session description");
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                    this.pendingReinvite = false;
                    return;
                }
                if (options.withoutSdp) {
                    const answerOptions = {
                        sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptionsReInvite,
                        sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiersReInvite
                    };
                    this.setOfferAndGetAnswer(body, answerOptions)
                        .then((answerBody) => {
                        response.ack({ body: answerBody });
                    })
                        .catch((error) => {
                        this.logger.error("Failed to handle offer in 2xx response to re-INVITE");
                        this.logger.error(error.message);
                        if (this.state === _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                            response.ack();
                        }
                        else {
                            this.ackAndBye(response, 488, "Bad Media Description");
                            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                        }
                    })
                        .then(() => {
                        this.pendingReinvite = false;
                        if (options.requestDelegate && options.requestDelegate.onAccept) {
                            options.requestDelegate.onAccept(response);
                        }
                    });
                }
                else {
                    const answerOptions = {
                        sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptionsReInvite,
                        sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiersReInvite
                    };
                    this.setAnswer(body, answerOptions)
                        .then(() => {
                        response.ack();
                    })
                        .catch((error) => {
                        this.logger.error("Failed to handle answer in 2xx response to re-INVITE");
                        this.logger.error(error.message);
                        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                            this.ackAndBye(response, 488, "Bad Media Description");
                            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                        }
                        else {
                            response.ack();
                        }
                    })
                        .then(() => {
                        this.pendingReinvite = false;
                        if (options.requestDelegate && options.requestDelegate.onAccept) {
                            options.requestDelegate.onAccept(response);
                        }
                    });
                }
            },
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            onProgress: (response) => {
                return;
            },
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            onRedirect: (response) => {
                return;
            },
            onReject: (response) => {
                this.logger.warn("Received a non-2xx response to re-INVITE");
                this.pendingReinvite = false;
                if (options.withoutSdp) {
                    if (options.requestDelegate && options.requestDelegate.onReject) {
                        options.requestDelegate.onReject(response);
                    }
                }
                else {
                    this.rollbackOffer()
                        .catch((error) => {
                        this.logger.error("Failed to rollback offer on non-2xx response to re-INVITE");
                        this.logger.error(error.message);
                        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                            if (!this.dialog) {
                                throw new Error("Dialog undefined.");
                            }
                            const extraHeaders = [];
                            extraHeaders.push("Reason: " + this.getReasonHeaderValue(500, "Internal Server Error"));
                            this.dialog.bye(undefined, { extraHeaders });
                            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                        }
                    })
                        .then(() => {
                        if (options.requestDelegate && options.requestDelegate.onReject) {
                            options.requestDelegate.onReject(response);
                        }
                    });
                }
            },
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            onTrying: (response) => {
                return;
            }
        };
        const requestOptions = options.requestOptions || {};
        requestOptions.extraHeaders = (requestOptions.extraHeaders || []).slice();
        requestOptions.extraHeaders.push("Allow: " + _core_user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_4__.AllowedMethods.toString());
        requestOptions.extraHeaders.push("Contact: " + this._contact);
        if (options.withoutSdp) {
            if (!this.dialog) {
                this.pendingReinvite = false;
                throw new Error("Dialog undefined.");
            }
            return Promise.resolve(this.dialog.invite(delegate, requestOptions));
        }
        const offerOptions = {
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptionsReInvite,
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiersReInvite
        };
        return this.getOffer(offerOptions)
            .then((offerBody) => {
            if (!this.dialog) {
                this.pendingReinvite = false;
                throw new Error("Dialog undefined.");
            }
            requestOptions.body = offerBody;
            return this.dialog.invite(delegate, requestOptions);
        })
            .catch((error) => {
            this.logger.error(error.message);
            this.logger.error("Failed to send re-INVITE");
            this.pendingReinvite = false;
            throw error;
        });
    }
    /** @param options */
    message(options = {}) {
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            const message = "Session.message() may only be called if established session.";
            this.logger.error(message);
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        const requestDelegate = options.requestDelegate;
        const requestOptions = this.copyRequestOptions(options.requestOptions);
        return this._message(requestDelegate, requestOptions);
    }
    /**
     * @param referTo
     * @param options
     */
    refer(referTo, options = {}) {
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            const message = "Session.refer() may only be called if established session.";
            this.logger.error(message);
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        if (referTo instanceof Session && !referTo.dialog) {
            const message = "Session.refer() may only be called with session which is established. " +
                "You are perhaps attempting to attended transfer to a target for which " +
                "there is not dialog yet established. Perhaps you are attempting a " +
                "'semi-attended' tansfer? Regardless, this is not supported. The recommended " +
                "approached is to check to see if the target Session is in the Established " +
                "state before calling refer(); if the state is not Established you may " +
                "proceed by falling back using a URI as the target (blind transfer).";
            this.logger.error(message);
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        const requestDelegate = options.requestDelegate;
        const requestOptions = this.copyRequestOptions(options.requestOptions);
        requestOptions.extraHeaders = requestOptions.extraHeaders
            ? requestOptions.extraHeaders.concat(this.referExtraHeaders(this.referToString(referTo)))
            : this.referExtraHeaders(this.referToString(referTo));
        return this._refer(options.onNotify, requestDelegate, requestOptions);
    }
    /**
     * @param delegate
     * @param options
     * @internal
     */
    _bye(delegate, options) {
        if (!this.dialog) {
            return Promise.reject(new Error("Session dialog undefined."));
        }
        const dialog = this.dialog;
        switch (dialog.sessionState) {
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Initial:
                throw new Error(`Invalid dialog state ${dialog.sessionState}`);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Early:
                throw new Error(`Invalid dialog state ${dialog.sessionState}`);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.AckWait: {
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating);
                return new Promise((resolve) => {
                    dialog.delegate = {
                        onAck: () => {
                            const request = dialog.bye(delegate, options);
                            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                            resolve(request);
                            return Promise.resolve();
                        },
                        onAckTimeout: () => {
                            const request = dialog.bye(delegate, options);
                            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                            resolve(request);
                        }
                    };
                });
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Confirmed: {
                const request = dialog.bye(delegate, options);
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                return Promise.resolve(request);
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated:
                throw new Error(`Invalid dialog state ${dialog.sessionState}`);
            default:
                throw new Error("Unrecognized state.");
        }
    }
    /**
     * @param delegate
     * @param options
     * @internal
     */
    _info(delegate, options) {
        if (!this.dialog) {
            return Promise.reject(new Error("Session dialog undefined."));
        }
        return Promise.resolve(this.dialog.info(delegate, options));
    }
    /**
     * @param delegate
     * @param options
     * @internal
     */
    _message(delegate, options) {
        if (!this.dialog) {
            return Promise.reject(new Error("Session dialog undefined."));
        }
        return Promise.resolve(this.dialog.message(delegate, options));
    }
    /**
     * @param onNotify
     * @param delegate
     * @param options
     * @internal
     */
    _refer(onNotify, delegate, options) {
        if (!this.dialog) {
            return Promise.reject(new Error("Session dialog undefined."));
        }
        this.onNotify = onNotify;
        return Promise.resolve(this.dialog.refer(delegate, options));
    }
    /**
     * @param inviteResponse
     * @param statusCode
     * @param reasonPhrase
     * @internal
     */
    ackAndBye(response, statusCode, reasonPhrase) {
        response.ack();
        const extraHeaders = [];
        if (statusCode) {
            extraHeaders.push("Reason: " + this.getReasonHeaderValue(statusCode, reasonPhrase));
        }
        response.session.bye(undefined, { extraHeaders });
    }
    /** @internal */
    onAckRequest(request) {
        this.logger.log("Session.onAckRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established && this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating) {
            this.logger.error(`ACK received while in state ${this.state}, dropping request`);
            return Promise.resolve();
        }
        const dialog = this.dialog;
        if (!dialog) {
            throw new Error("Dialog undefined.");
        }
        const answerOptions = {
            sessionDescriptionHandlerOptions: this.pendingReinviteAck
                ? this.sessionDescriptionHandlerOptionsReInvite
                : this.sessionDescriptionHandlerOptions,
            sessionDescriptionHandlerModifiers: this.pendingReinviteAck
                ? this._sessionDescriptionHandlerModifiersReInvite
                : this._sessionDescriptionHandlerModifiers
        };
        if (this.delegate && this.delegate.onAck) {
            const ack = new _ack_js__WEBPACK_IMPORTED_MODULE_6__.Ack(request);
            this.delegate.onAck(ack);
        }
        this.pendingReinviteAck = false;
        switch (dialog.signalingState) {
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Initial: {
                this.logger.error(`Invalid signaling state ${dialog.signalingState}.`);
                const extraHeaders = ["Reason: " + this.getReasonHeaderValue(488, "Bad Media Description")];
                dialog.bye(undefined, { extraHeaders });
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                return Promise.resolve();
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Stable: {
                const body = (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__.getBody)(request.message);
                if (!body) {
                    return Promise.resolve();
                }
                if (body.contentDisposition === "render") {
                    this._renderbody = body.content;
                    this._rendertype = body.contentType;
                    return Promise.resolve();
                }
                if (body.contentDisposition !== "session") {
                    return Promise.resolve();
                }
                return this.setAnswer(body, answerOptions).catch((error) => {
                    this.logger.error(error.message);
                    const extraHeaders = ["Reason: " + this.getReasonHeaderValue(488, "Bad Media Description")];
                    dialog.bye(undefined, { extraHeaders });
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                });
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.HaveLocalOffer: {
                this.logger.error(`Invalid signaling state ${dialog.signalingState}.`);
                const extraHeaders = ["Reason: " + this.getReasonHeaderValue(488, "Bad Media Description")];
                dialog.bye(undefined, { extraHeaders });
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                return Promise.resolve();
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.HaveRemoteOffer: {
                this.logger.error(`Invalid signaling state ${dialog.signalingState}.`);
                const extraHeaders = ["Reason: " + this.getReasonHeaderValue(488, "Bad Media Description")];
                dialog.bye(undefined, { extraHeaders });
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                return Promise.resolve();
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Closed:
                throw new Error(`Invalid signaling state ${dialog.signalingState}.`);
            default:
                throw new Error(`Invalid signaling state ${dialog.signalingState}.`);
        }
    }
    /** @internal */
    onByeRequest(request) {
        this.logger.log("Session.onByeRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`BYE received while in state ${this.state}, dropping request`);
            return;
        }
        if (this.delegate && this.delegate.onBye) {
            const bye = new _bye_js__WEBPACK_IMPORTED_MODULE_7__.Bye(request);
            this.delegate.onBye(bye);
        }
        else {
            request.accept();
        }
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
    }
    /** @internal */
    onInfoRequest(request) {
        this.logger.log("Session.onInfoRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`INFO received while in state ${this.state}, dropping request`);
            return;
        }
        if (this.delegate && this.delegate.onInfo) {
            const info = new _info_js__WEBPACK_IMPORTED_MODULE_8__.Info(request);
            this.delegate.onInfo(info);
        }
        else {
            request.accept();
        }
    }
    /** @internal */
    onInviteRequest(request) {
        this.logger.log("Session.onInviteRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`INVITE received while in state ${this.state}, dropping request`);
            return;
        }
        this.pendingReinviteAck = true;
        const extraHeaders = ["Contact: " + this._contact];
        if (request.message.hasHeader("P-Asserted-Identity")) {
            const header = request.message.getHeader("P-Asserted-Identity");
            if (!header) {
                throw new Error("Header undefined.");
            }
            this._assertedIdentity = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_9__.Grammar.nameAddrHeaderParse(header);
        }
        const options = {
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptionsReInvite,
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiersReInvite
        };
        this.generateResponseOfferAnswerInDialog(options)
            .then((body) => {
            const outgoingResponse = request.accept({ statusCode: 200, extraHeaders, body });
            if (this.delegate && this.delegate.onInvite) {
                this.delegate.onInvite(request.message, outgoingResponse.message, 200);
            }
        })
            .catch((error) => {
            this.logger.error(error.message);
            this.logger.error("Failed to handle to re-INVITE request");
            if (!this.dialog) {
                throw new Error("Dialog undefined.");
            }
            this.logger.error(this.dialog.signalingState);
            if (this.dialog.signalingState === _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Stable) {
                const outgoingResponse = request.reject({ statusCode: 488 });
                if (this.delegate && this.delegate.onInvite) {
                    this.delegate.onInvite(request.message, outgoingResponse.message, 488);
                }
                return;
            }
            this.rollbackOffer()
                .then(() => {
                const outgoingResponse = request.reject({ statusCode: 488 });
                if (this.delegate && this.delegate.onInvite) {
                    this.delegate.onInvite(request.message, outgoingResponse.message, 488);
                }
            })
                .catch((errorRollback) => {
                this.logger.error(errorRollback.message);
                this.logger.error("Failed to rollback offer on re-INVITE request");
                const outgoingResponse = request.reject({ statusCode: 488 });
                if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                    if (!this.dialog) {
                        throw new Error("Dialog undefined.");
                    }
                    const extraHeadersBye = [];
                    extraHeadersBye.push("Reason: " + this.getReasonHeaderValue(500, "Internal Server Error"));
                    this.dialog.bye(undefined, { extraHeaders: extraHeadersBye });
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated);
                }
                if (this.delegate && this.delegate.onInvite) {
                    this.delegate.onInvite(request.message, outgoingResponse.message, 488);
                }
            });
        });
    }
    /** @internal */
    onMessageRequest(request) {
        this.logger.log("Session.onMessageRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`MESSAGE received while in state ${this.state}, dropping request`);
            return;
        }
        if (this.delegate && this.delegate.onMessage) {
            const message = new _message_js__WEBPACK_IMPORTED_MODULE_10__.Message(request);
            this.delegate.onMessage(message);
        }
        else {
            request.accept();
        }
    }
    /** @internal */
    onNotifyRequest(request) {
        this.logger.log("Session.onNotifyRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`NOTIFY received while in state ${this.state}, dropping request`);
            return;
        }
        if (this.onNotify) {
            const notification = new _notification_js__WEBPACK_IMPORTED_MODULE_11__.Notification(request);
            this.onNotify(notification);
            return;
        }
        if (this.delegate && this.delegate.onNotify) {
            const notification = new _notification_js__WEBPACK_IMPORTED_MODULE_11__.Notification(request);
            this.delegate.onNotify(notification);
        }
        else {
            request.accept();
        }
    }
    /** @internal */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    onPrackRequest(request) {
        this.logger.log("Session.onPrackRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`PRACK received while in state ${this.state}, dropping request`);
            return;
        }
        throw new Error("Unimplemented.");
    }
    /** @internal */
    onReferRequest(request) {
        this.logger.log("Session.onReferRequest");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
            this.logger.error(`REFER received while in state ${this.state}, dropping request`);
            return;
        }
        if (!request.message.hasHeader("refer-to")) {
            this.logger.warn("Invalid REFER packet. A refer-to header is required. Rejecting.");
            request.reject();
            return;
        }
        const referral = new _referral_js__WEBPACK_IMPORTED_MODULE_12__.Referral(request, this);
        if (this.delegate && this.delegate.onRefer) {
            this.delegate.onRefer(referral);
        }
        else {
            this.logger.log("No delegate available to handle REFER, automatically accepting and following.");
            referral
                .accept()
                .then(() => referral.makeInviter(this._referralInviterOptions).invite())
                .catch((error) => {
                this.logger.error(error.message);
            });
        }
    }
    /** @internal */
    generateResponseOfferAnswer(request, options) {
        if (this.dialog) {
            return this.generateResponseOfferAnswerInDialog(options);
        }
        const body = (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__.getBody)(request.message);
        if (!body || body.contentDisposition !== "session") {
            return this.getOffer(options);
        }
        else {
            return this.setOfferAndGetAnswer(body, options);
        }
    }
    /** @internal */
    generateResponseOfferAnswerInDialog(options) {
        if (!this.dialog) {
            throw new Error("Dialog undefined.");
        }
        switch (this.dialog.signalingState) {
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Initial:
                return this.getOffer(options);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.HaveLocalOffer:
                return Promise.resolve(undefined);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.HaveRemoteOffer:
                if (!this.dialog.offer) {
                    throw new Error(`Session offer undefined in signaling state ${this.dialog.signalingState}.`);
                }
                return this.setOfferAndGetAnswer(this.dialog.offer, options);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Stable:
                if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established) {
                    return Promise.resolve(undefined);
                }
                return this.getOffer(options);
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Closed:
                throw new Error(`Invalid signaling state ${this.dialog.signalingState}.`);
            default:
                throw new Error(`Invalid signaling state ${this.dialog.signalingState}.`);
        }
    }
    /** @internal */
    getOffer(options) {
        const sdh = this.setupSessionDescriptionHandler();
        const sdhOptions = options.sessionDescriptionHandlerOptions;
        const sdhModifiers = options.sessionDescriptionHandlerModifiers;
        try {
            return sdh
                .getDescription(sdhOptions, sdhModifiers)
                .then((bodyAndContentType) => (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__.fromBodyLegacy)(bodyAndContentType))
                .catch((error) => {
                this.logger.error("Session.getOffer: SDH getDescription rejected...");
                const e = error instanceof Error ? error : new Error("Session.getOffer unknown error.");
                this.logger.error(e.message);
                throw e;
            });
        }
        catch (error) {
            this.logger.error("Session.getOffer: SDH getDescription threw...");
            const e = error instanceof Error ? error : new Error(error);
            this.logger.error(e.message);
            return Promise.reject(e);
        }
    }
    /** @internal */
    rollbackOffer() {
        const sdh = this.setupSessionDescriptionHandler();
        if (sdh.rollbackDescription === undefined) {
            return Promise.resolve();
        }
        try {
            return sdh.rollbackDescription().catch((error) => {
                this.logger.error("Session.rollbackOffer: SDH rollbackDescription rejected...");
                const e = error instanceof Error ? error : new Error("Session.rollbackOffer unknown error.");
                this.logger.error(e.message);
                throw e;
            });
        }
        catch (error) {
            this.logger.error("Session.rollbackOffer: SDH rollbackDescription threw...");
            const e = error instanceof Error ? error : new Error(error);
            this.logger.error(e.message);
            return Promise.reject(e);
        }
    }
    /** @internal */
    setAnswer(answer, options) {
        const sdh = this.setupSessionDescriptionHandler();
        const sdhOptions = options.sessionDescriptionHandlerOptions;
        const sdhModifiers = options.sessionDescriptionHandlerModifiers;
        try {
            if (!sdh.hasDescription(answer.contentType)) {
                return Promise.reject(new _exceptions_content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_13__.ContentTypeUnsupportedError());
            }
        }
        catch (error) {
            this.logger.error("Session.setAnswer: SDH hasDescription threw...");
            const e = error instanceof Error ? error : new Error(error);
            this.logger.error(e.message);
            return Promise.reject(e);
        }
        try {
            return sdh.setDescription(answer.content, sdhOptions, sdhModifiers).catch((error) => {
                this.logger.error("Session.setAnswer: SDH setDescription rejected...");
                const e = error instanceof Error ? error : new Error("Session.setAnswer unknown error.");
                this.logger.error(e.message);
                throw e;
            });
        }
        catch (error) {
            this.logger.error("Session.setAnswer: SDH setDescription threw...");
            const e = error instanceof Error ? error : new Error(error);
            this.logger.error(e.message);
            return Promise.reject(e);
        }
    }
    /** @internal */
    setOfferAndGetAnswer(offer, options) {
        const sdh = this.setupSessionDescriptionHandler();
        const sdhOptions = options.sessionDescriptionHandlerOptions;
        const sdhModifiers = options.sessionDescriptionHandlerModifiers;
        try {
            if (!sdh.hasDescription(offer.contentType)) {
                return Promise.reject(new _exceptions_content_type_unsupported_js__WEBPACK_IMPORTED_MODULE_13__.ContentTypeUnsupportedError());
            }
        }
        catch (error) {
            this.logger.error("Session.setOfferAndGetAnswer: SDH hasDescription threw...");
            const e = error instanceof Error ? error : new Error(error);
            this.logger.error(e.message);
            return Promise.reject(e);
        }
        try {
            return sdh
                .setDescription(offer.content, sdhOptions, sdhModifiers)
                .then(() => sdh.getDescription(sdhOptions, sdhModifiers))
                .then((bodyAndContentType) => (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__.fromBodyLegacy)(bodyAndContentType))
                .catch((error) => {
                this.logger.error("Session.setOfferAndGetAnswer: SDH setDescription or getDescription rejected...");
                const e = error instanceof Error ? error : new Error("Session.setOfferAndGetAnswer unknown error.");
                this.logger.error(e.message);
                throw e;
            });
        }
        catch (error) {
            this.logger.error("Session.setOfferAndGetAnswer: SDH setDescription or getDescription threw...");
            const e = error instanceof Error ? error : new Error(error);
            this.logger.error(e.message);
            return Promise.reject(e);
        }
    }
    /** @internal */
    setSessionDescriptionHandler(sdh) {
        if (this._sessionDescriptionHandler) {
            throw new Error("Session description handler defined.");
        }
        this._sessionDescriptionHandler = sdh;
    }
    /** @internal */
    setupSessionDescriptionHandler() {
        var _a;
        if (this._sessionDescriptionHandler) {
            return this._sessionDescriptionHandler;
        }
        this._sessionDescriptionHandler = this.sessionDescriptionHandlerFactory(this, this.userAgent.configuration.sessionDescriptionHandlerFactoryOptions);
        if ((_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onSessionDescriptionHandler) {
            this.delegate.onSessionDescriptionHandler(this._sessionDescriptionHandler, false);
        }
        return this._sessionDescriptionHandler;
    }
    /** @internal */
    stateTransition(newState) {
        const invalidTransition = () => {
            throw new Error(`Invalid state transition from ${this._state} to ${newState}`);
        };
        switch (this._state) {
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Initial:
                if (newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Establishing &&
                    newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established &&
                    newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating &&
                    newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Establishing:
                if (newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established &&
                    newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating &&
                    newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Established:
                if (newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating && newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminating:
                if (newState !== _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated:
                invalidTransition();
                break;
            default:
                throw new Error("Unrecognized state.");
        }
        this._state = newState;
        this.logger.log(`Session ${this.id} transitioned to state ${this._state}`);
        this._stateEventEmitter.emit(this._state);
        if (newState === _session_state_js__WEBPACK_IMPORTED_MODULE_0__.SessionState.Terminated) {
            this.dispose();
        }
    }
    copyRequestOptions(requestOptions = {}) {
        const extraHeaders = requestOptions.extraHeaders ? requestOptions.extraHeaders.slice() : undefined;
        const body = requestOptions.body
            ? {
                contentDisposition: requestOptions.body.contentDisposition || "render",
                contentType: requestOptions.body.contentType || "text/plain",
                content: requestOptions.body.content || ""
            }
            : undefined;
        return {
            extraHeaders,
            body
        };
    }
    getReasonHeaderValue(code, reason) {
        const cause = code;
        let text = (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_14__.getReasonPhrase)(code);
        if (!text && reason) {
            text = reason;
        }
        return "SIP;cause=" + cause + ';text="' + text + '"';
    }
    referExtraHeaders(referTo) {
        const extraHeaders = [];
        extraHeaders.push("Referred-By: <" + this.userAgent.configuration.uri + ">");
        extraHeaders.push("Contact: " + this._contact);
        extraHeaders.push("Allow: " + ["ACK", "CANCEL", "INVITE", "MESSAGE", "BYE", "OPTIONS", "INFO", "NOTIFY", "REFER"].toString());
        extraHeaders.push("Refer-To: " + referTo);
        return extraHeaders;
    }
    referToString(target) {
        let referTo;
        if (target instanceof _grammar_uri_js__WEBPACK_IMPORTED_MODULE_15__.URI) {
            referTo = target.toString();
        }
        else {
            if (!target.dialog) {
                throw new Error("Dialog undefined.");
            }
            const displayName = target.remoteIdentity.friendlyName;
            const remoteTarget = target.dialog.remoteTarget.toString();
            const callId = target.dialog.callId;
            const remoteTag = target.dialog.remoteTag;
            const localTag = target.dialog.localTag;
            const replaces = encodeURIComponent(`${callId};to-tag=${remoteTag};from-tag=${localTag}`);
            referTo = `"${displayName}" <${remoteTarget}?Replaces=${replaces}>`;
        }
        return referTo;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionState": () => ( SessionState)
 });
/**
 * @remarks
 * @public
 */
var SessionState;
(function (SessionState) {
    SessionState["Initial"] = "Initial";
    SessionState["Establishing"] = "Establishing";
    SessionState["Established"] = "Established";
    SessionState["Terminating"] = "Terminating";
    SessionState["Terminated"] = "Terminated";
})(SessionState = SessionState || (SessionState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "fromBodyLegacy": () => ( fromBodyLegacy),
   "getBody": () => ( getBody),
   "isBody": () => ( isBody)
 });
 var _incoming_request_message_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(19);
 var _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(27);
 var _outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(28);



function contentTypeToContentDisposition(contentType) {
    if (contentType === "application/sdp") {
        return "session";
    }
    else {
        return "render";
    }
}
/**
 * @param bodyLegacy
 * @internal
 */
function fromBodyLegacy(bodyLegacy) {
    const content = typeof bodyLegacy === "string" ? bodyLegacy : bodyLegacy.body;
    const contentType = typeof bodyLegacy === "string" ? "application/sdp" : bodyLegacy.contentType;
    const contentDisposition = contentTypeToContentDisposition(contentType);
    const body = { contentDisposition, contentType, content };
    return body;
}
/**
 * @param body
 * @internal
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function isBody(body) {
    return body &&
        typeof body.content === "string" &&
        typeof body.contentType === "string" &&
        body.contentDisposition === undefined
        ? true
        : typeof body.contentDisposition === "string";
}
/**
 * @param message
 * @internal
 */
function getBody(message) {
    let contentDisposition;
    let contentType;
    let content;
    if (message instanceof _incoming_request_message_js__WEBPACK_IMPORTED_MODULE_0__.IncomingRequestMessage) {
        if (message.body) {
            const parse = message.parseHeader("Content-Disposition");
            contentDisposition = parse ? parse.type : undefined;
            contentType = message.parseHeader("Content-Type");
            content = message.body;
        }
    }
    if (message instanceof _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_1__.IncomingResponseMessage) {
        if (message.body) {
            const parse = message.parseHeader("Content-Disposition");
            contentDisposition = parse ? parse.type : undefined;
            contentType = message.parseHeader("Content-Type");
            content = message.body;
        }
    }
    if (message instanceof _outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_2__.OutgoingRequestMessage) {
        if (message.body) {
            contentDisposition = message.getHeader("Content-Disposition");
            contentType = message.getHeader("Content-Type");
            if (typeof message.body === "string") {
                if (!contentType) {
                    throw new Error("Header content type header does not equal body content type.");
                }
                content = message.body;
            }
            else {
                if (contentType && contentType !== message.body.contentType) {
                    throw new Error("Header content type header does not equal body content type.");
                }
                contentType = message.body.contentType;
                content = message.body.body;
            }
        }
    }
    if (isBody(message)) {
        contentDisposition = message.contentDisposition;
        contentType = message.contentType;
        content = message.content;
    }
    if (!content) {
        return undefined;
    }
    if (contentType && !contentDisposition) {
        contentDisposition = contentTypeToContentDisposition(contentType);
    }
    if (!contentDisposition) {
        throw new Error("Content disposition undefined.");
    }
    if (!contentType) {
        throw new Error("Content type undefined.");
    }
    return {
        contentDisposition,
        contentType,
        content
    };
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "IncomingRequestMessage": () => ( IncomingRequestMessage)
 });
 var _incoming_message_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(20);

/** @public */
class IncomingRequestMessage extends _incoming_message_js__WEBPACK_IMPORTED_MODULE_0__.IncomingMessage {
    constructor() {
        super();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "IncomingMessage": () => ( IncomingMessage)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(22);
 var _utils_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(21);


/** @public */
class IncomingMessage {
    constructor() {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        this.headers = {};
    }
    /**
     * @param name
     * @param value
     */
    addHeader(name, value) {
        const header = { raw: value };
        name = (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name);
        if (this.headers[name]) {
            this.headers[name].push(header);
        }
        else {
            this.headers[name] = [header];
        }
    }
    /**
     * @param name
     * @returns
     */
    getHeader(name) {
        const header = this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)];
        if (header) {
            if (header[0]) {
                return header[0].raw;
            }
        }
        else {
            return;
        }
    }
    /**
     * @param name
     * @returns
     */
    getHeaders(name) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const header = this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)];
        const result = [];
        if (!header) {
            return [];
        }
        for (const headerPart of header) {
            result.push(headerPart.raw);
        }
        return result;
    }
    /**
     * @param name
     * @returns
     */
    hasHeader(name) {
        return !!this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)];
    }
    /**
     * @param name
     * @param idx
     * @returns
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    parseHeader(name, idx = 0) {
        name = (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name);
        if (!this.headers[name]) {
            return;
        }
        else if (idx >= this.headers[name].length) {
            return;
        }
        const header = this.headers[name][idx];
        const value = header.raw;
        if (header.parsed) {
            return header.parsed;
        }
        const parsed = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_1__.Grammar.parse(value, name.replace(/-/g, "_"));
        if (parsed === -1) {
            this.headers[name].splice(idx, 1);
            return;
        }
        else {
            header.parsed = parsed;
            return parsed;
        }
    }
    /**
     * @param name
     * @param idx
     * @returns
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    s(name, idx = 0) {
        return this.parseHeader(name, idx);
    }
    /**
     * @param name
     * @param value
     */
    setHeader(name, value) {
        this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)] = [{ raw: value }];
    }
    toString() {
        return this.data;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "createRandomToken": () => ( createRandomToken),
   "getReasonPhrase": () => ( getReasonPhrase),
   "headerize": () => ( headerize),
   "newTag": () => ( newTag),
   "utf8Length": () => ( utf8Length)
 });
/** @internal */
const REASON_PHRASE = {
    100: "Trying",
    180: "Ringing",
    181: "Call Is Being Forwarded",
    182: "Queued",
    183: "Session Progress",
    199: "Early Dialog Terminated",
    200: "OK",
    202: "Accepted",
    204: "No Notification",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Moved Temporarily",
    305: "Use Proxy",
    380: "Alternative Service",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    410: "Gone",
    412: "Conditional Request Failed",
    413: "Request Entity Too Large",
    414: "Request-URI Too Long",
    415: "Unsupported Media Type",
    416: "Unsupported URI Scheme",
    417: "Unknown Resource-Priority",
    420: "Bad Extension",
    421: "Extension Required",
    422: "Session Interval Too Small",
    423: "Interval Too Brief",
    428: "Use Identity Header",
    429: "Provide Referrer Identity",
    430: "Flow Failed",
    433: "Anonymity Disallowed",
    436: "Bad Identity-Info",
    437: "Unsupported Certificate",
    438: "Invalid Identity Header",
    439: "First Hop Lacks Outbound Support",
    440: "Max-Breadth Exceeded",
    469: "Bad Info Package",
    470: "Consent Needed",
    478: "Unresolvable Destination",
    480: "Temporarily Unavailable",
    481: "Call/Transaction Does Not Exist",
    482: "Loop Detected",
    483: "Too Many Hops",
    484: "Address Incomplete",
    485: "Ambiguous",
    486: "Busy Here",
    487: "Request Terminated",
    488: "Not Acceptable Here",
    489: "Bad Event",
    491: "Request Pending",
    493: "Undecipherable",
    494: "Security Agreement Required",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Server Time-out",
    505: "Version Not Supported",
    513: "Message Too Large",
    580: "Precondition Failure",
    600: "Busy Everywhere",
    603: "Decline",
    604: "Does Not Exist Anywhere",
    606: "Not Acceptable"
};
/**
 * @param size
 * @param base
 * @internal
 */
function createRandomToken(size, base = 32) {
    let token = "";
    for (let i = 0; i < size; i++) {
        const r = Math.floor(Math.random() * base);
        token += r.toString(base);
    }
    return token;
}
/**
 * @internal
 */
function getReasonPhrase(code) {
    return REASON_PHRASE[code] || "";
}
/**
 * @internal
 */
function newTag() {
    return createRandomToken(10);
}
/**
 * @param str
 * @internal
 */
function headerize(str) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const exceptions = {
        "Call-Id": "Call-ID",
        Cseq: "CSeq",
        "Min-Se": "Min-SE",
        Rack: "RAck",
        Rseq: "RSeq",
        "Www-Authenticate": "WWW-Authenticate"
    };
    const name = str.toLowerCase().replace(/_/g, "-").split("-");
    const parts = name.length;
    let hname = "";
    for (let part = 0; part < parts; part++) {
        if (part !== 0) {
            hname += "-";
        }
        hname += name[part].charAt(0).toUpperCase() + name[part].substring(1);
    }
    if (exceptions[hname]) {
        hname = exceptions[hname];
    }
    return hname;
}
/**
 * @param str
 * @internal
 */
function utf8Length(str) {
    return encodeURIComponent(str).replace(/%[A-F\d]{2}/g, "U").length;
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Grammar": () => ( Grammar)
 });
 var _pegjs_dist_grammar_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(23);
/* eslint-disable @typescript-eslint/no-namespace */
/* eslint-disable no-inner-declarations */

/** @internal */
var Grammar;
(function (Grammar) {
    /**
     * @param input
     * @param startRule
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function parse(input, startRule) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const options = { startRule };
        try {
            _pegjs_dist_grammar_js__WEBPACK_IMPORTED_MODULE_0__.parse(input, options);
        }
        catch (e) {
            options.data = -1;
        }
        return options.data;
    }
    Grammar.parse = parse;
    /** @param name_addr_header */
    function nameAddrHeaderParse(nameAddrHeader) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const parsedNameAddrHeader = Grammar.parse(nameAddrHeader, "Name_Addr_Header");
        return parsedNameAddrHeader !== -1 ? parsedNameAddrHeader : undefined;
    }
    Grammar.nameAddrHeaderParse = nameAddrHeaderParse;
    /** @param uri */
    function URIParse(uri) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const parsedUri = Grammar.parse(uri, "SIP_URI");
        return parsedUri !== -1 ? parsedUri : undefined;
    }
    Grammar.URIParse = URIParse;
})(Grammar = Grammar || (Grammar = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SyntaxError": () => ( SyntaxError),
   "parse": () => ( parse)
 });
 var _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(26);
 var _uri_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(24);


function peg$padEnd(str, targetLength, padString) {
    padString = padString || ' ';
    if (str.length > targetLength) {
        return str;
    }
    targetLength -= str.length;
    padString += padString.repeat(targetLength);
    return str + padString.slice(0, targetLength);
}
class SyntaxError extends Error {
    constructor(message, expected, found, location) {
        super();
        this.message = message;
        this.expected = expected;
        this.found = found;
        this.location = location;
        this.name = "SyntaxError";
        if (typeof Object.setPrototypeOf === "function") {
            Object.setPrototypeOf(this, SyntaxError.prototype);
        }
        else {
            this.__proto__ = SyntaxError.prototype;
        }
        if (typeof Error.captureStackTrace === "function") {
            Error.captureStackTrace(this, SyntaxError);
        }
    }
    static buildMessage(expected, found) {
        function hex(ch) {
            return ch.charCodeAt(0).toString(16).toUpperCase();
        }
        function literalEscape(s) {
            return s
                .replace(/\\/g, "\\\\")
                .replace(/"/g, "\\\"")
                .replace(/\0/g, "\\0")
                .replace(/\t/g, "\\t")
                .replace(/\n/g, "\\n")
                .replace(/\r/g, "\\r")
                .replace(/[\x00-\x0F]/g, (ch) => "\\x0" + hex(ch))
                .replace(/[\x10-\x1F\x7F-\x9F]/g, (ch) => "\\x" + hex(ch));
        }
        function classEscape(s) {
            return s
                .replace(/\\/g, "\\\\")
                .replace(/\]/g, "\\]")
                .replace(/\^/g, "\\^")
                .replace(/-/g, "\\-")
                .replace(/\0/g, "\\0")
                .replace(/\t/g, "\\t")
                .replace(/\n/g, "\\n")
                .replace(/\r/g, "\\r")
                .replace(/[\x00-\x0F]/g, (ch) => "\\x0" + hex(ch))
                .replace(/[\x10-\x1F\x7F-\x9F]/g, (ch) => "\\x" + hex(ch));
        }
        function describeExpectation(expectation) {
            switch (expectation.type) {
                case "literal":
                    return "\"" + literalEscape(expectation.text) + "\"";
                case "class":
                    const escapedParts = expectation.parts.map((part) => {
                        return Array.isArray(part)
                            ? classEscape(part[0]) + "-" + classEscape(part[1])
                            : classEscape(part);
                    });
                    return "[" + (expectation.inverted ? "^" : "") + escapedParts + "]";
                case "any":
                    return "any character";
                case "end":
                    return "end of input";
                case "other":
                    return expectation.description;
            }
        }
        function describeExpected(expected1) {
            const descriptions = expected1.map(describeExpectation);
            let i;
            let j;
            descriptions.sort();
            if (descriptions.length > 0) {
                for (i = 1, j = 1; i < descriptions.length; i++) {
                    if (descriptions[i - 1] !== descriptions[i]) {
                        descriptions[j] = descriptions[i];
                        j++;
                    }
                }
                descriptions.length = j;
            }
            switch (descriptions.length) {
                case 1:
                    return descriptions[0];
                case 2:
                    return descriptions[0] + " or " + descriptions[1];
                default:
                    return descriptions.slice(0, -1).join(", ")
                        + ", or "
                        + descriptions[descriptions.length - 1];
            }
        }
        function describeFound(found1) {
            return found1 ? "\"" + literalEscape(found1) + "\"" : "end of input";
        }
        return "Expected " + describeExpected(expected) + " but " + describeFound(found) + " found.";
    }
    format(sources) {
        let str = 'Error: ' + this.message;
        if (this.location) {
            let src = null;
            let k;
            for (k = 0; k < sources.length; k++) {
                if (sources[k].source === this.location.source) {
                    src = sources[k].text.split(/\r\n|\n|\r/g);
                    break;
                }
            }
            let s = this.location.start;
            let loc = this.location.source + ':' + s.line + ':' + s.column;
            if (src) {
                let e = this.location.end;
                let filler = peg$padEnd('', s.line.toString().length, ' ');
                let line = src[s.line - 1];
                let last = s.line === e.line ? e.column : line.length + 1;
                str += '\n --> ' + loc + '\n' + filler + ' |\n' + s.line + ' | ' + line + '\n' + filler + ' | ' +
                    peg$padEnd('', s.column - 1, ' ') +
                    peg$padEnd('', last - s.column, '^');
            }
            else {
                str += '\n at ' + loc;
            }
        }
        return str;
    }
}
function peg$parse(input, options) {
    options = options !== undefined ? options : {};
    const peg$FAILED = {};
    const peg$source = options.grammarSource;
    const peg$startRuleIndices = { Contact: 119, Name_Addr_Header: 156, Record_Route: 176, Request_Response: 81, SIP_URI: 45, Subscription_State: 186, Supported: 191, Require: 182, Via: 194, absoluteURI: 84, Call_ID: 118, Content_Disposition: 130, Content_Length: 135, Content_Type: 136, CSeq: 146, displayName: 122, Event: 149, From: 151, host: 52, Max_Forwards: 154, Min_SE: 213, Proxy_Authenticate: 157, quoted_string: 40, Refer_To: 178, Replaces: 179, Session_Expires: 210, stun_URI: 217, To: 192, turn_URI: 223, uuid: 226, WWW_Authenticate: 209, challenge: 158, sipfrag: 230, Referred_By: 231 };
    let peg$startRuleIndex = 119;
    const peg$consts = [
        "\r\n",
        peg$literalExpectation("\r\n", false),
        /^[0-9]/,
        peg$classExpectation([["0", "9"]], false, false),
        /^[a-zA-Z]/,
        peg$classExpectation([["a", "z"], ["A", "Z"]], false, false),
        /^[0-9a-fA-F]/,
        peg$classExpectation([["0", "9"], ["a", "f"], ["A", "F"]], false, false),
        /^[\0-\xFF]/,
        peg$classExpectation([["\0", "\xFF"]], false, false),
        /^["]/,
        peg$classExpectation(["\""], false, false),
        " ",
        peg$literalExpectation(" ", false),
        "\t",
        peg$literalExpectation("\t", false),
        /^[a-zA-Z0-9]/,
        peg$classExpectation([["a", "z"], ["A", "Z"], ["0", "9"]], false, false),
        ";",
        peg$literalExpectation(";", false),
        "/",
        peg$literalExpectation("/", false),
        "?",
        peg$literalExpectation("?", false),
        ":",
        peg$literalExpectation(":", false),
        "@",
        peg$literalExpectation("@", false),
        "&",
        peg$literalExpectation("&", false),
        "=",
        peg$literalExpectation("=", false),
        "+",
        peg$literalExpectation("+", false),
        "$",
        peg$literalExpectation("$", false),
        ",",
        peg$literalExpectation(",", false),
        "-",
        peg$literalExpectation("-", false),
        "_",
        peg$literalExpectation("_", false),
        ".",
        peg$literalExpectation(".", false),
        "!",
        peg$literalExpectation("!", false),
        "~",
        peg$literalExpectation("~", false),
        "*",
        peg$literalExpectation("*", false),
        "'",
        peg$literalExpectation("'", false),
        "(",
        peg$literalExpectation("(", false),
        ")",
        peg$literalExpectation(")", false),
        "%",
        peg$literalExpectation("%", false),
        function () { return " "; },
        function () { return ':'; },
        /^[!-~]/,
        peg$classExpectation([["!", "~"]], false, false),
        /^[\x80-\uFFFF]/,
        peg$classExpectation([["\x80", "\uFFFF"]], false, false),
        /^[\x80-\xBF]/,
        peg$classExpectation([["\x80", "\xBF"]], false, false),
        /^[a-f]/,
        peg$classExpectation([["a", "f"]], false, false),
        "`",
        peg$literalExpectation("`", false),
        "<",
        peg$literalExpectation("<", false),
        ">",
        peg$literalExpectation(">", false),
        "\\",
        peg$literalExpectation("\\", false),
        "[",
        peg$literalExpectation("[", false),
        "]",
        peg$literalExpectation("]", false),
        "{",
        peg$literalExpectation("{", false),
        "}",
        peg$literalExpectation("}", false),
        function () { return "*"; },
        function () { return "/"; },
        function () { return "="; },
        function () { return "("; },
        function () { return ")"; },
        function () { return ">"; },
        function () { return "<"; },
        function () { return ","; },
        function () { return ";"; },
        function () { return ":"; },
        function () { return "\""; },
        /^[!-']/,
        peg$classExpectation([["!", "'"]], false, false),
        /^[*-[]/,
        peg$classExpectation([["*", "["]], false, false),
        /^[\]-~]/,
        peg$classExpectation([["]", "~"]], false, false),
        function (contents) {
            return contents;
        },
        /^[#-[]/,
        peg$classExpectation([["#", "["]], false, false),
        /^[\0-\t]/,
        peg$classExpectation([["\0", "\t"]], false, false),
        /^[\v-\f]/,
        peg$classExpectation([["\v", "\f"]], false, false),
        /^[\x0E-\x7F]/,
        peg$classExpectation([["\x0E", "\x7F"]], false, false),
        function () {
            options = options || { data: {} };
            options.data.uri = new _uri_js__WEBPACK_IMPORTED_MODULE_0__.URI(options.data.scheme, options.data.user, options.data.host, options.data.port);
            delete options.data.scheme;
            delete options.data.user;
            delete options.data.host;
            delete options.data.host_type;
            delete options.data.port;
        },
        function () {
            options = options || { data: {} };
            options.data.uri = new _uri_js__WEBPACK_IMPORTED_MODULE_0__.URI(options.data.scheme, options.data.user, options.data.host, options.data.port, options.data.uri_params, options.data.uri_headers);
            delete options.data.scheme;
            delete options.data.user;
            delete options.data.host;
            delete options.data.host_type;
            delete options.data.port;
            delete options.data.uri_params;
            if (options.startRule === 'SIP_URI') {
                options.data = options.data.uri;
            }
        },
        "sips",
        peg$literalExpectation("sips", true),
        "sip",
        peg$literalExpectation("sip", true),
        function (uri_scheme) {
            options = options || { data: {} };
            options.data.scheme = uri_scheme;
        },
        function () {
            options = options || { data: {} };
            options.data.user = decodeURIComponent(text().slice(0, -1));
        },
        function () {
            options = options || { data: {} };
            options.data.password = text();
        },
        function () {
            options = options || { data: {} };
            options.data.host = text();
            return options.data.host;
        },
        function () {
            options = options || { data: {} };
            options.data.host_type = 'domain';
            return text();
        },
        /^[a-zA-Z0-9_\-]/,
        peg$classExpectation([["a", "z"], ["A", "Z"], ["0", "9"], "_", "-"], false, false),
        /^[a-zA-Z0-9\-]/,
        peg$classExpectation([["a", "z"], ["A", "Z"], ["0", "9"], "-"], false, false),
        function () {
            options = options || { data: {} };
            options.data.host_type = 'IPv6';
            return text();
        },
        "::",
        peg$literalExpectation("::", false),
        function () {
            options = options || { data: {} };
            options.data.host_type = 'IPv6';
            return text();
        },
        function () {
            options = options || { data: {} };
            options.data.host_type = 'IPv4';
            return text();
        },
        "25",
        peg$literalExpectation("25", false),
        /^[0-5]/,
        peg$classExpectation([["0", "5"]], false, false),
        "2",
        peg$literalExpectation("2", false),
        /^[0-4]/,
        peg$classExpectation([["0", "4"]], false, false),
        "1",
        peg$literalExpectation("1", false),
        /^[1-9]/,
        peg$classExpectation([["1", "9"]], false, false),
        function (port) {
            options = options || { data: {} };
            port = parseInt(port.join(''));
            options.data.port = port;
            return port;
        },
        "transport=",
        peg$literalExpectation("transport=", true),
        "udp",
        peg$literalExpectation("udp", true),
        "tcp",
        peg$literalExpectation("tcp", true),
        "sctp",
        peg$literalExpectation("sctp", true),
        "tls",
        peg$literalExpectation("tls", true),
        function (transport) {
            options = options || { data: {} };
            if (!options.data.uri_params)
                options.data.uri_params = {};
            options.data.uri_params['transport'] = transport.toLowerCase();
        },
        "user=",
        peg$literalExpectation("user=", true),
        "phone",
        peg$literalExpectation("phone", true),
        "ip",
        peg$literalExpectation("ip", true),
        function (user) {
            options = options || { data: {} };
            if (!options.data.uri_params)
                options.data.uri_params = {};
            options.data.uri_params['user'] = user.toLowerCase();
        },
        "method=",
        peg$literalExpectation("method=", true),
        function (method) {
            options = options || { data: {} };
            if (!options.data.uri_params)
                options.data.uri_params = {};
            options.data.uri_params['method'] = method;
        },
        "ttl=",
        peg$literalExpectation("ttl=", true),
        function (ttl) {
            options = options || { data: {} };
            if (!options.data.params)
                options.data.params = {};
            options.data.params['ttl'] = ttl;
        },
        "maddr=",
        peg$literalExpectation("maddr=", true),
        function (maddr) {
            options = options || { data: {} };
            if (!options.data.uri_params)
                options.data.uri_params = {};
            options.data.uri_params['maddr'] = maddr;
        },
        "lr",
        peg$literalExpectation("lr", true),
        function () {
            options = options || { data: {} };
            if (!options.data.uri_params)
                options.data.uri_params = {};
            options.data.uri_params['lr'] = undefined;
        },
        function (param, value) {
            options = options || { data: {} };
            if (!options.data.uri_params)
                options.data.uri_params = {};
            if (value === null) {
                value = undefined;
            }
            else {
                value = value[1];
            }
            options.data.uri_params[param.toLowerCase()] = value;
        },
        function (hname, hvalue) {
            hname = hname.join('').toLowerCase();
            hvalue = hvalue.join('');
            options = options || { data: {} };
            if (!options.data.uri_headers)
                options.data.uri_headers = {};
            if (!options.data.uri_headers[hname]) {
                options.data.uri_headers[hname] = [hvalue];
            }
            else {
                options.data.uri_headers[hname].push(hvalue);
            }
        },
        function () {
            options = options || { data: {} };
            if (options.startRule === 'Refer_To') {
                options.data.uri = new _uri_js__WEBPACK_IMPORTED_MODULE_0__.URI(options.data.scheme, options.data.user, options.data.host, options.data.port, options.data.uri_params, options.data.uri_headers);
                delete options.data.scheme;
                delete options.data.user;
                delete options.data.host;
                delete options.data.host_type;
                delete options.data.port;
                delete options.data.uri_params;
            }
        },
        "//",
        peg$literalExpectation("//", false),
        function () {
            options = options || { data: {} };
            options.data.scheme = text();
        },
        peg$literalExpectation("SIP", true),
        function () {
            options = options || { data: {} };
            options.data.sip_version = text();
        },
        "INVITE",
        peg$literalExpectation("INVITE", false),
        "ACK",
        peg$literalExpectation("ACK", false),
        "VXACH",
        peg$literalExpectation("VXACH", false),
        "OPTIONS",
        peg$literalExpectation("OPTIONS", false),
        "BYE",
        peg$literalExpectation("BYE", false),
        "CANCEL",
        peg$literalExpectation("CANCEL", false),
        "REGISTER",
        peg$literalExpectation("REGISTER", false),
        "SUBSCRIBE",
        peg$literalExpectation("SUBSCRIBE", false),
        "NOTIFY",
        peg$literalExpectation("NOTIFY", false),
        "REFER",
        peg$literalExpectation("REFER", false),
        "PUBLISH",
        peg$literalExpectation("PUBLISH", false),
        function () {
            options = options || { data: {} };
            options.data.method = text();
            return options.data.method;
        },
        function (status_code) {
            options = options || { data: {} };
            options.data.status_code = parseInt(status_code.join(''));
        },
        function () {
            options = options || { data: {} };
            options.data.reason_phrase = text();
        },
        function () {
            options = options || { data: {} };
            options.data = text();
        },
        function () {
            var idx, length;
            options = options || { data: {} };
            length = options.data.multi_header.length;
            for (idx = 0; idx < length; idx++) {
                if (options.data.multi_header[idx].parsed === null) {
                    options.data = null;
                    break;
                }
            }
            if (options.data !== null) {
                options.data = options.data.multi_header;
            }
            else {
                options.data = -1;
            }
        },
        function () {
            var header;
            options = options || { data: {} };
            if (!options.data.multi_header)
                options.data.multi_header = [];
            try {
                header = new _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(options.data.uri, options.data.displayName, options.data.params);
                delete options.data.uri;
                delete options.data.displayName;
                delete options.data.params;
            }
            catch (e) {
                header = null;
            }
            options.data.multi_header.push({ 'position': peg$currPos,
                'offset': location().start.offset,
                'parsed': header
            });
        },
        function (displayName) {
            displayName = text().trim();
            if (displayName[0] === '\"') {
                displayName = displayName.substring(1, displayName.length - 1);
            }
            options = options || { data: {} };
            options.data.displayName = displayName;
        },
        "q",
        peg$literalExpectation("q", true),
        function (q) {
            options = options || { data: {} };
            if (!options.data.params)
                options.data.params = {};
            options.data.params['q'] = q;
        },
        "expires",
        peg$literalExpectation("expires", true),
        function (expires) {
            options = options || { data: {} };
            if (!options.data.params)
                options.data.params = {};
            options.data.params['expires'] = expires;
        },
        function (delta_seconds) {
            return parseInt(delta_seconds.join(''));
        },
        "0",
        peg$literalExpectation("0", false),
        function () {
            return parseFloat(text());
        },
        function (param, value) {
            options = options || { data: {} };
            if (!options.data.params)
                options.data.params = {};
            if (value === null) {
                value = undefined;
            }
            else {
                value = value[1];
            }
            options.data.params[param.toLowerCase()] = value;
        },
        "render",
        peg$literalExpectation("render", true),
        "session",
        peg$literalExpectation("session", true),
        "icon",
        peg$literalExpectation("icon", true),
        "alert",
        peg$literalExpectation("alert", true),
        function () {
            options = options || { data: {} };
            if (options.startRule === 'Content_Disposition') {
                options.data.type = text().toLowerCase();
            }
        },
        "handling",
        peg$literalExpectation("handling", true),
        "optional",
        peg$literalExpectation("optional", true),
        "required",
        peg$literalExpectation("required", true),
        function (length) {
            options = options || { data: {} };
            options.data = parseInt(length.join(''));
        },
        function () {
            options = options || { data: {} };
            options.data = text();
        },
        "text",
        peg$literalExpectation("text", true),
        "image",
        peg$literalExpectation("image", true),
        "audio",
        peg$literalExpectation("audio", true),
        "video",
        peg$literalExpectation("video", true),
        "application",
        peg$literalExpectation("application", true),
        "message",
        peg$literalExpectation("message", true),
        "multipart",
        peg$literalExpectation("multipart", true),
        "x-",
        peg$literalExpectation("x-", true),
        function (cseq_value) {
            options = options || { data: {} };
            options.data.value = parseInt(cseq_value.join(''));
        },
        function (expires) { options = options || { data: {} }; options.data = expires; },
        function (event_type) {
            options = options || { data: {} };
            options.data.event = event_type.toLowerCase();
        },
        function () {
            options = options || { data: {} };
            var tag = options.data.tag;
            options.data = new _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(options.data.uri, options.data.displayName, options.data.params);
            if (tag) {
                options.data.setParam('tag', tag);
            }
        },
        "tag",
        peg$literalExpectation("tag", true),
        function (tag) { options = options || { data: {} }; options.data.tag = tag; },
        function (forwards) {
            options = options || { data: {} };
            options.data = parseInt(forwards.join(''));
        },
        function (min_expires) { options = options || { data: {} }; options.data = min_expires; },
        function () {
            options = options || { data: {} };
            options.data = new _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(options.data.uri, options.data.displayName, options.data.params);
        },
        "digest",
        peg$literalExpectation("Digest", true),
        "realm",
        peg$literalExpectation("realm", true),
        function (realm) { options = options || { data: {} }; options.data.realm = realm; },
        "domain",
        peg$literalExpectation("domain", true),
        "nonce",
        peg$literalExpectation("nonce", true),
        function (nonce) { options = options || { data: {} }; options.data.nonce = nonce; },
        "opaque",
        peg$literalExpectation("opaque", true),
        function (opaque) { options = options || { data: {} }; options.data.opaque = opaque; },
        "stale",
        peg$literalExpectation("stale", true),
        "true",
        peg$literalExpectation("true", true),
        function () { options = options || { data: {} }; options.data.stale = true; },
        "false",
        peg$literalExpectation("false", true),
        function () { options = options || { data: {} }; options.data.stale = false; },
        "algorithm",
        peg$literalExpectation("algorithm", true),
        "md5",
        peg$literalExpectation("MD5", true),
        "md5-sess",
        peg$literalExpectation("MD5-sess", true),
        function (algorithm) {
            options = options || { data: {} };
            options.data.algorithm = algorithm.toUpperCase();
        },
        "qop",
        peg$literalExpectation("qop", true),
        "auth-int",
        peg$literalExpectation("auth-int", true),
        "auth",
        peg$literalExpectation("auth", true),
        function (qop_value) {
            options = options || { data: {} };
            options.data.qop || (options.data.qop = []);
            options.data.qop.push(qop_value.toLowerCase());
        },
        function (rack_value) {
            options = options || { data: {} };
            options.data.value = parseInt(rack_value.join(''));
        },
        function () {
            var idx, length;
            options = options || { data: {} };
            length = options.data.multi_header.length;
            for (idx = 0; idx < length; idx++) {
                if (options.data.multi_header[idx].parsed === null) {
                    options.data = null;
                    break;
                }
            }
            if (options.data !== null) {
                options.data = options.data.multi_header;
            }
            else {
                options.data = -1;
            }
        },
        function () {
            var header;
            options = options || { data: {} };
            if (!options.data.multi_header)
                options.data.multi_header = [];
            try {
                header = new _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(options.data.uri, options.data.displayName, options.data.params);
                delete options.data.uri;
                delete options.data.displayName;
                delete options.data.params;
            }
            catch (e) {
                header = null;
            }
            options.data.multi_header.push({ 'position': peg$currPos,
                'offset': location().start.offset,
                'parsed': header
            });
        },
        function () {
            options = options || { data: {} };
            options.data = new _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(options.data.uri, options.data.displayName, options.data.params);
        },
        function () {
            options = options || { data: {} };
            if (!(options.data.replaces_from_tag && options.data.replaces_to_tag)) {
                options.data = -1;
            }
        },
        function () {
            options = options || { data: {} };
            options.data = {
                call_id: options.data
            };
        },
        "from-tag",
        peg$literalExpectation("from-tag", true),
        function (from_tag) {
            options = options || { data: {} };
            options.data.replaces_from_tag = from_tag;
        },
        "to-tag",
        peg$literalExpectation("to-tag", true),
        function (to_tag) {
            options = options || { data: {} };
            options.data.replaces_to_tag = to_tag;
        },
        "early-only",
        peg$literalExpectation("early-only", true),
        function () {
            options = options || { data: {} };
            options.data.early_only = true;
        },
        function (head, r) { return r; },
        function (head, tail) { return list(head, tail); },
        function (value) {
            options = options || { data: {} };
            if (options.startRule === 'Require') {
                options.data = value || [];
            }
        },
        function (rseq_value) {
            options = options || { data: {} };
            options.data.value = parseInt(rseq_value.join(''));
        },
        "active",
        peg$literalExpectation("active", true),
        "pending",
        peg$literalExpectation("pending", true),
        "terminated",
        peg$literalExpectation("terminated", true),
        function () {
            options = options || { data: {} };
            options.data.state = text();
        },
        "reason",
        peg$literalExpectation("reason", true),
        function (reason) {
            options = options || { data: {} };
            if (typeof reason !== 'undefined')
                options.data.reason = reason;
        },
        function (expires) {
            options = options || { data: {} };
            if (typeof expires !== 'undefined')
                options.data.expires = expires;
        },
        "retry_after",
        peg$literalExpectation("retry_after", true),
        function (retry_after) {
            options = options || { data: {} };
            if (typeof retry_after !== 'undefined')
                options.data.retry_after = retry_after;
        },
        "deactivated",
        peg$literalExpectation("deactivated", true),
        "probation",
        peg$literalExpectation("probation", true),
        "rejected",
        peg$literalExpectation("rejected", true),
        "timeout",
        peg$literalExpectation("timeout", true),
        "giveup",
        peg$literalExpectation("giveup", true),
        "noresource",
        peg$literalExpectation("noresource", true),
        "invariant",
        peg$literalExpectation("invariant", true),
        function (value) {
            options = options || { data: {} };
            if (options.startRule === 'Supported') {
                options.data = value || [];
            }
        },
        function () {
            options = options || { data: {} };
            var tag = options.data.tag;
            options.data = new _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(options.data.uri, options.data.displayName, options.data.params);
            if (tag) {
                options.data.setParam('tag', tag);
            }
        },
        "ttl",
        peg$literalExpectation("ttl", true),
        function (via_ttl_value) {
            options = options || { data: {} };
            options.data.ttl = via_ttl_value;
        },
        "maddr",
        peg$literalExpectation("maddr", true),
        function (via_maddr) {
            options = options || { data: {} };
            options.data.maddr = via_maddr;
        },
        "received",
        peg$literalExpectation("received", true),
        function (via_received) {
            options = options || { data: {} };
            options.data.received = via_received;
        },
        "branch",
        peg$literalExpectation("branch", true),
        function (via_branch) {
            options = options || { data: {} };
            options.data.branch = via_branch;
        },
        "rport",
        peg$literalExpectation("rport", true),
        function (response_port) {
            options = options || { data: {} };
            if (typeof response_port !== 'undefined')
                options.data.rport = response_port.join('');
        },
        function (via_protocol) {
            options = options || { data: {} };
            options.data.protocol = via_protocol;
        },
        peg$literalExpectation("UDP", true),
        peg$literalExpectation("TCP", true),
        peg$literalExpectation("TLS", true),
        peg$literalExpectation("SCTP", true),
        function (via_transport) {
            options = options || { data: {} };
            options.data.transport = via_transport;
        },
        function () {
            options = options || { data: {} };
            options.data.host = text();
        },
        function (via_sent_by_port) {
            options = options || { data: {} };
            options.data.port = parseInt(via_sent_by_port.join(''));
        },
        function (ttl) {
            return parseInt(ttl.join(''));
        },
        function (deltaSeconds) {
            options = options || { data: {} };
            if (options.startRule === 'Session_Expires') {
                options.data.deltaSeconds = deltaSeconds;
            }
        },
        "refresher",
        peg$literalExpectation("refresher", false),
        "uas",
        peg$literalExpectation("uas", false),
        "uac",
        peg$literalExpectation("uac", false),
        function (endpoint) {
            options = options || { data: {} };
            if (options.startRule === 'Session_Expires') {
                options.data.refresher = endpoint;
            }
        },
        function (deltaSeconds) {
            options = options || { data: {} };
            if (options.startRule === 'Min_SE') {
                options.data = deltaSeconds;
            }
        },
        "stuns",
        peg$literalExpectation("stuns", true),
        "stun",
        peg$literalExpectation("stun", true),
        function (scheme) {
            options = options || { data: {} };
            options.data.scheme = scheme;
        },
        function (host) {
            options = options || { data: {} };
            options.data.host = host;
        },
        "?transport=",
        peg$literalExpectation("?transport=", false),
        "turns",
        peg$literalExpectation("turns", true),
        "turn",
        peg$literalExpectation("turn", true),
        function (transport) {
            options = options || { data: {} };
            options.data.transport = transport;
        },
        function () {
            options = options || { data: {} };
            options.data = text();
        },
        "Referred-By",
        peg$literalExpectation("Referred-By", false),
        "b",
        peg$literalExpectation("b", false),
        "cid",
        peg$literalExpectation("cid", false)
    ];
    const peg$bytecode = [
        peg$decode("2 \"\"6 7!"),
        peg$decode("4\"\"\"5!7#"),
        peg$decode("4$\"\"5!7%"),
        peg$decode("4&\"\"5!7'"),
        peg$decode(";'.# &;("),
        peg$decode("4(\"\"5!7)"),
        peg$decode("4*\"\"5!7+"),
        peg$decode("2,\"\"6,7-"),
        peg$decode("2.\"\"6.7/"),
        peg$decode("40\"\"5!71"),
        peg$decode("22\"\"6273.\x89 &24\"\"6475.} &26\"\"6677.q &28\"\"6879.e &2:\"\"6:7;.Y &2<\"\"6<7=.M &2>\"\"6>7?.A &2@\"\"6@7A.5 &2B\"\"6B7C.) &2D\"\"6D7E"),
        peg$decode(";).# &;,"),
        peg$decode("2F\"\"6F7G.} &2H\"\"6H7I.q &2J\"\"6J7K.e &2L\"\"6L7M.Y &2N\"\"6N7O.M &2P\"\"6P7Q.A &2R\"\"6R7S.5 &2T\"\"6T7U.) &2V\"\"6V7W"),
        peg$decode("%%2X\"\"6X7Y/5#;#/,$;#/#$+#)(#'#(\"'#&'#/\"!&,)"),
        peg$decode("%%$;$0#*;$&/,#; /#$+\")(\"'#&'#.\" &\"/=#$;$/&#0#*;$&&&#/'$8\":Z\" )(\"'#&'#"),
        peg$decode(";..\" &\""),
        peg$decode("%$;'.# &;(0)*;'.# &;(&/?#28\"\"6879/0$;//'$8#:[# )(#'#(\"'#&'#"),
        peg$decode("%%$;2/&#0#*;2&&&#/g#$%$;.0#*;.&/,#;2/#$+\")(\"'#&'#0=*%$;.0#*;.&/,#;2/#$+\")(\"'#&'#&/#$+\")(\"'#&'#/\"!&,)"),
        peg$decode("4\\\"\"5!7].# &;3"),
        peg$decode("4^\"\"5!7_"),
        peg$decode("4`\"\"5!7a"),
        peg$decode(";!.) &4b\"\"5!7c"),
        peg$decode("%$;).\x95 &2F\"\"6F7G.\x89 &2J\"\"6J7K.} &2L\"\"6L7M.q &2X\"\"6X7Y.e &2P\"\"6P7Q.Y &2H\"\"6H7I.M &2@\"\"6@7A.A &2d\"\"6d7e.5 &2R\"\"6R7S.) &2N\"\"6N7O/\x9E#0\x9B*;).\x95 &2F\"\"6F7G.\x89 &2J\"\"6J7K.} &2L\"\"6L7M.q &2X\"\"6X7Y.e &2P\"\"6P7Q.Y &2H\"\"6H7I.M &2@\"\"6@7A.A &2d\"\"6d7e.5 &2R\"\"6R7S.) &2N\"\"6N7O&&&#/\"!&,)"),
        peg$decode("%$;).\x89 &2F\"\"6F7G.} &2L\"\"6L7M.q &2X\"\"6X7Y.e &2P\"\"6P7Q.Y &2H\"\"6H7I.M &2@\"\"6@7A.A &2d\"\"6d7e.5 &2R\"\"6R7S.) &2N\"\"6N7O/\x92#0\x8F*;).\x89 &2F\"\"6F7G.} &2L\"\"6L7M.q &2X\"\"6X7Y.e &2P\"\"6P7Q.Y &2H\"\"6H7I.M &2@\"\"6@7A.A &2d\"\"6d7e.5 &2R\"\"6R7S.) &2N\"\"6N7O&&&#/\"!&,)"),
        peg$decode("2T\"\"6T7U.\xE3 &2V\"\"6V7W.\xD7 &2f\"\"6f7g.\xCB &2h\"\"6h7i.\xBF &2:\"\"6:7;.\xB3 &2D\"\"6D7E.\xA7 &22\"\"6273.\x9B &28\"\"6879.\x8F &2j\"\"6j7k.\x83 &;&.} &24\"\"6475.q &2l\"\"6l7m.e &2n\"\"6n7o.Y &26\"\"6677.M &2>\"\"6>7?.A &2p\"\"6p7q.5 &2r\"\"6r7s.) &;'.# &;("),
        peg$decode("%$;).\u012B &2F\"\"6F7G.\u011F &2J\"\"6J7K.\u0113 &2L\"\"6L7M.\u0107 &2X\"\"6X7Y.\xFB &2P\"\"6P7Q.\xEF &2H\"\"6H7I.\xE3 &2@\"\"6@7A.\xD7 &2d\"\"6d7e.\xCB &2R\"\"6R7S.\xBF &2N\"\"6N7O.\xB3 &2T\"\"6T7U.\xA7 &2V\"\"6V7W.\x9B &2f\"\"6f7g.\x8F &2h\"\"6h7i.\x83 &28\"\"6879.w &2j\"\"6j7k.k &;&.e &24\"\"6475.Y &2l\"\"6l7m.M &2n\"\"6n7o.A &26\"\"6677.5 &2p\"\"6p7q.) &2r\"\"6r7s/\u0134#0\u0131*;).\u012B &2F\"\"6F7G.\u011F &2J\"\"6J7K.\u0113 &2L\"\"6L7M.\u0107 &2X\"\"6X7Y.\xFB &2P\"\"6P7Q.\xEF &2H\"\"6H7I.\xE3 &2@\"\"6@7A.\xD7 &2d\"\"6d7e.\xCB &2R\"\"6R7S.\xBF &2N\"\"6N7O.\xB3 &2T\"\"6T7U.\xA7 &2V\"\"6V7W.\x9B &2f\"\"6f7g.\x8F &2h\"\"6h7i.\x83 &28\"\"6879.w &2j\"\"6j7k.k &;&.e &24\"\"6475.Y &2l\"\"6l7m.M &2n\"\"6n7o.A &26\"\"6677.5 &2p\"\"6p7q.) &2r\"\"6r7s&&&#/\"!&,)"),
        peg$decode("%;//?#2P\"\"6P7Q/0$;//'$8#:t# )(#'#(\"'#&'#"),
        peg$decode("%;//?#24\"\"6475/0$;//'$8#:u# )(#'#(\"'#&'#"),
        peg$decode("%;//?#2>\"\"6>7?/0$;//'$8#:v# )(#'#(\"'#&'#"),
        peg$decode("%;//?#2T\"\"6T7U/0$;//'$8#:w# )(#'#(\"'#&'#"),
        peg$decode("%;//?#2V\"\"6V7W/0$;//'$8#:x# )(#'#(\"'#&'#"),
        peg$decode("%2h\"\"6h7i/0#;//'$8\":y\" )(\"'#&'#"),
        peg$decode("%;//6#2f\"\"6f7g/'$8\":z\" )(\"'#&'#"),
        peg$decode("%;//?#2D\"\"6D7E/0$;//'$8#:{# )(#'#(\"'#&'#"),
        peg$decode("%;//?#22\"\"6273/0$;//'$8#:|# )(#'#(\"'#&'#"),
        peg$decode("%;//?#28\"\"6879/0$;//'$8#:}# )(#'#(\"'#&'#"),
        peg$decode("%;//0#;&/'$8\":~\" )(\"'#&'#"),
        peg$decode("%;&/0#;//'$8\":~\" )(\"'#&'#"),
        peg$decode("%;=/T#$;G.) &;K.# &;F0/*;G.) &;K.# &;F&/,$;>/#$+#)(#'#(\"'#&'#"),
        peg$decode("4\x7F\"\"5!7\x80.A &4\x81\"\"5!7\x82.5 &4\x83\"\"5!7\x84.) &;3.# &;."),
        peg$decode("%%;//Q#;&/H$$;J.# &;K0)*;J.# &;K&/,$;&/#$+$)($'#(#'#(\"'#&'#/\"!&,)"),
        peg$decode("%;//]#;&/T$%$;J.# &;K0)*;J.# &;K&/\"!&,)/1$;&/($8$:\x85$!!)($'#(#'#(\"'#&'#"),
        peg$decode(";..G &2L\"\"6L7M.; &4\x86\"\"5!7\x87./ &4\x83\"\"5!7\x84.# &;3"),
        peg$decode("%2j\"\"6j7k/J#4\x88\"\"5!7\x89.5 &4\x8A\"\"5!7\x8B.) &4\x8C\"\"5!7\x8D/#$+\")(\"'#&'#"),
        peg$decode("%;N/M#28\"\"6879/>$;O.\" &\"/0$;S/'$8$:\x8E$ )($'#(#'#(\"'#&'#"),
        peg$decode("%;N/d#28\"\"6879/U$;O.\" &\"/G$;S/>$;_/5$;l.\" &\"/'$8&:\x8F& )(&'#(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%3\x90\"\"5$7\x91.) &3\x92\"\"5#7\x93/' 8!:\x94!! )"),
        peg$decode("%;P/]#%28\"\"6879/,#;R/#$+\")(\"'#&'#.\" &\"/6$2:\"\"6:7;/'$8#:\x95# )(#'#(\"'#&'#"),
        peg$decode("$;+.) &;-.# &;Q/2#0/*;+.) &;-.# &;Q&&&#"),
        peg$decode("2<\"\"6<7=.q &2>\"\"6>7?.e &2@\"\"6@7A.Y &2B\"\"6B7C.M &2D\"\"6D7E.A &22\"\"6273.5 &26\"\"6677.) &24\"\"6475"),
        peg$decode("%$;+._ &;-.Y &2<\"\"6<7=.M &2>\"\"6>7?.A &2@\"\"6@7A.5 &2B\"\"6B7C.) &2D\"\"6D7E0e*;+._ &;-.Y &2<\"\"6<7=.M &2>\"\"6>7?.A &2@\"\"6@7A.5 &2B\"\"6B7C.) &2D\"\"6D7E&/& 8!:\x96! )"),
        peg$decode("%;T/J#%28\"\"6879/,#;^/#$+\")(\"'#&'#.\" &\"/#$+\")(\"'#&'#"),
        peg$decode("%;U.) &;\\.# &;X/& 8!:\x97! )"),
        peg$decode("%$%;V/2#2J\"\"6J7K/#$+\")(\"'#&'#0<*%;V/2#2J\"\"6J7K/#$+\")(\"'#&'#&/D#;W/;$2J\"\"6J7K.\" &\"/'$8#:\x98# )(#'#(\"'#&'#"),
        peg$decode("$4\x99\"\"5!7\x9A/,#0)*4\x99\"\"5!7\x9A&&&#"),
        peg$decode("%4$\"\"5!7%/?#$4\x9B\"\"5!7\x9C0)*4\x9B\"\"5!7\x9C&/#$+\")(\"'#&'#"),
        peg$decode("%2l\"\"6l7m/?#;Y/6$2n\"\"6n7o/'$8#:\x9D# )(#'#(\"'#&'#"),
        peg$decode("%%;Z/\xB3#28\"\"6879/\xA4$;Z/\x9B$28\"\"6879/\x8C$;Z/\x83$28\"\"6879/t$;Z/k$28\"\"6879/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+-)(-'#(,'#(+'#(*'#()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u0790 &%2\x9E\"\"6\x9E7\x9F/\xA4#;Z/\x9B$28\"\"6879/\x8C$;Z/\x83$28\"\"6879/t$;Z/k$28\"\"6879/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+,)(,'#(+'#(*'#()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u06F9 &%2\x9E\"\"6\x9E7\x9F/\x8C#;Z/\x83$28\"\"6879/t$;Z/k$28\"\"6879/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+*)(*'#()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u067A &%2\x9E\"\"6\x9E7\x9F/t#;Z/k$28\"\"6879/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+()(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u0613 &%2\x9E\"\"6\x9E7\x9F/\\#;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+&)(&'#(%'#($'#(#'#(\"'#&'#.\u05C4 &%2\x9E\"\"6\x9E7\x9F/D#;Z/;$28\"\"6879/,$;[/#$+$)($'#(#'#(\"'#&'#.\u058D &%2\x9E\"\"6\x9E7\x9F/,#;[/#$+\")(\"'#&'#.\u056E &%2\x9E\"\"6\x9E7\x9F/,#;Z/#$+\")(\"'#&'#.\u054F &%;Z/\x9B#2\x9E\"\"6\x9E7\x9F/\x8C$;Z/\x83$28\"\"6879/t$;Z/k$28\"\"6879/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$++)(+'#(*'#()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u04C7 &%;Z/\xAA#%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\x83$2\x9E\"\"6\x9E7\x9F/t$;Z/k$28\"\"6879/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+*)(*'#()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u0430 &%;Z/\xB9#%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\x92$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/k$2\x9E\"\"6\x9E7\x9F/\\$;Z/S$28\"\"6879/D$;Z/;$28\"\"6879/,$;[/#$+))()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u038A &%;Z/\xC8#%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xA1$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/z$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/S$2\x9E\"\"6\x9E7\x9F/D$;Z/;$28\"\"6879/,$;[/#$+()(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u02D5 &%;Z/\xD7#%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xB0$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\x89$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/b$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/;$2\x9E\"\"6\x9E7\x9F/,$;[/#$+')(''#(&'#(%'#($'#(#'#(\"'#&'#.\u0211 &%;Z/\xFE#%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xD7$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xB0$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\x89$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/b$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/;$2\x9E\"\"6\x9E7\x9F/,$;Z/#$+()(('#(''#(&'#(%'#($'#(#'#(\"'#&'#.\u0126 &%;Z/\u011C#%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xF5$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xCE$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\xA7$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/\x80$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/Y$%28\"\"6879/,#;Z/#$+\")(\"'#&'#.\" &\"/2$2\x9E\"\"6\x9E7\x9F/#$+()(('#(''#(&'#(%'#($'#(#'#(\"'#&'#/& 8!:\xA0! )"),
        peg$decode("%;#/M#;#.\" &\"/?$;#.\" &\"/1$;#.\" &\"/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode("%;Z/;#28\"\"6879/,$;Z/#$+#)(#'#(\"'#&'#.# &;\\"),
        peg$decode("%;]/o#2J\"\"6J7K/`$;]/W$2J\"\"6J7K/H$;]/?$2J\"\"6J7K/0$;]/'$8':\xA1' )(''#(&'#(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%2\xA2\"\"6\xA27\xA3/2#4\xA4\"\"5!7\xA5/#$+\")(\"'#&'#.\x98 &%2\xA6\"\"6\xA67\xA7/;#4\xA8\"\"5!7\xA9/,$;!/#$+#)(#'#(\"'#&'#.j &%2\xAA\"\"6\xAA7\xAB/5#;!/,$;!/#$+#)(#'#(\"'#&'#.B &%4\xAC\"\"5!7\xAD/,#;!/#$+\")(\"'#&'#.# &;!"),
        peg$decode("%%;!.\" &\"/[#;!.\" &\"/M$;!.\" &\"/?$;!.\" &\"/1$;!.\" &\"/#$+%)(%'#($'#(#'#(\"'#&'#/' 8!:\xAE!! )"),
        peg$decode("$%22\"\"6273/,#;`/#$+\")(\"'#&'#0<*%22\"\"6273/,#;`/#$+\")(\"'#&'#&"),
        peg$decode(";a.A &;b.; &;c.5 &;d./ &;e.) &;f.# &;g"),
        peg$decode("%3\xAF\"\"5*7\xB0/a#3\xB1\"\"5#7\xB2.G &3\xB3\"\"5#7\xB4.; &3\xB5\"\"5$7\xB6./ &3\xB7\"\"5#7\xB8.# &;6/($8\":\xB9\"! )(\"'#&'#"),
        peg$decode("%3\xBA\"\"5%7\xBB/I#3\xBC\"\"5%7\xBD./ &3\xBE\"\"5\"7\xBF.# &;6/($8\":\xC0\"! )(\"'#&'#"),
        peg$decode("%3\xC1\"\"5'7\xC2/1#;\x90/($8\":\xC3\"! )(\"'#&'#"),
        peg$decode("%3\xC4\"\"5$7\xC5/1#;\xF0/($8\":\xC6\"! )(\"'#&'#"),
        peg$decode("%3\xC7\"\"5&7\xC8/1#;T/($8\":\xC9\"! )(\"'#&'#"),
        peg$decode("%3\xCA\"\"5\"7\xCB/N#%2>\"\"6>7?/,#;6/#$+\")(\"'#&'#.\" &\"/'$8\":\xCC\" )(\"'#&'#"),
        peg$decode("%;h/P#%2>\"\"6>7?/,#;i/#$+\")(\"'#&'#.\" &\"/)$8\":\xCD\"\"! )(\"'#&'#"),
        peg$decode("%$;j/&#0#*;j&&&#/\"!&,)"),
        peg$decode("%$;j/&#0#*;j&&&#/\"!&,)"),
        peg$decode(";k.) &;+.# &;-"),
        peg$decode("2l\"\"6l7m.e &2n\"\"6n7o.Y &24\"\"6475.M &28\"\"6879.A &2<\"\"6<7=.5 &2@\"\"6@7A.) &2B\"\"6B7C"),
        peg$decode("%26\"\"6677/n#;m/e$$%2<\"\"6<7=/,#;m/#$+\")(\"'#&'#0<*%2<\"\"6<7=/,#;m/#$+\")(\"'#&'#&/#$+#)(#'#(\"'#&'#"),
        peg$decode("%;n/A#2>\"\"6>7?/2$;o/)$8#:\xCE#\"\" )(#'#(\"'#&'#"),
        peg$decode("$;p.) &;+.# &;-/2#0/*;p.) &;+.# &;-&&&#"),
        peg$decode("$;p.) &;+.# &;-0/*;p.) &;+.# &;-&"),
        peg$decode("2l\"\"6l7m.e &2n\"\"6n7o.Y &24\"\"6475.M &26\"\"6677.A &28\"\"6879.5 &2@\"\"6@7A.) &2B\"\"6B7C"),
        peg$decode(";\x91.# &;r"),
        peg$decode("%;\x90/G#;'/>$;s/5$;'/,$;\x84/#$+%)(%'#($'#(#'#(\"'#&'#"),
        peg$decode(";M.# &;t"),
        peg$decode("%;\x7F/E#28\"\"6879/6$;u.# &;x/'$8#:\xCF# )(#'#(\"'#&'#"),
        peg$decode("%;v.# &;w/J#%26\"\"6677/,#;\x83/#$+\")(\"'#&'#.\" &\"/#$+\")(\"'#&'#"),
        peg$decode("%2\xD0\"\"6\xD07\xD1/:#;\x80/1$;w.\" &\"/#$+#)(#'#(\"'#&'#"),
        peg$decode("%24\"\"6475/,#;{/#$+\")(\"'#&'#"),
        peg$decode("%;z/3#$;y0#*;y&/#$+\")(\"'#&'#"),
        peg$decode(";*.) &;+.# &;-"),
        peg$decode(";+.\x8F &;-.\x89 &22\"\"6273.} &26\"\"6677.q &28\"\"6879.e &2:\"\"6:7;.Y &2<\"\"6<7=.M &2>\"\"6>7?.A &2@\"\"6@7A.5 &2B\"\"6B7C.) &2D\"\"6D7E"),
        peg$decode("%;|/e#$%24\"\"6475/,#;|/#$+\")(\"'#&'#0<*%24\"\"6475/,#;|/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%$;~0#*;~&/e#$%22\"\"6273/,#;}/#$+\")(\"'#&'#0<*%22\"\"6273/,#;}/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("$;~0#*;~&"),
        peg$decode(";+.w &;-.q &28\"\"6879.e &2:\"\"6:7;.Y &2<\"\"6<7=.M &2>\"\"6>7?.A &2@\"\"6@7A.5 &2B\"\"6B7C.) &2D\"\"6D7E"),
        peg$decode("%%;\"/\x87#$;\".G &;!.A &2@\"\"6@7A.5 &2F\"\"6F7G.) &2J\"\"6J7K0M*;\".G &;!.A &2@\"\"6@7A.5 &2F\"\"6F7G.) &2J\"\"6J7K&/#$+\")(\"'#&'#/& 8!:\xD2! )"),
        peg$decode(";\x81.# &;\x82"),
        peg$decode("%%;O/2#2:\"\"6:7;/#$+\")(\"'#&'#.\" &\"/,#;S/#$+\")(\"'#&'#.\" &\""),
        peg$decode("$;+.\x83 &;-.} &2B\"\"6B7C.q &2D\"\"6D7E.e &22\"\"6273.Y &28\"\"6879.M &2:\"\"6:7;.A &2<\"\"6<7=.5 &2>\"\"6>7?.) &2@\"\"6@7A/\x8C#0\x89*;+.\x83 &;-.} &2B\"\"6B7C.q &2D\"\"6D7E.e &22\"\"6273.Y &28\"\"6879.M &2:\"\"6:7;.A &2<\"\"6<7=.5 &2>\"\"6>7?.) &2@\"\"6@7A&&&#"),
        peg$decode("$;y0#*;y&"),
        peg$decode("%3\x92\"\"5#7\xD3/q#24\"\"6475/b$$;!/&#0#*;!&&&#/L$2J\"\"6J7K/=$$;!/&#0#*;!&&&#/'$8%:\xD4% )(%'#($'#(#'#(\"'#&'#"),
        peg$decode("2\xD5\"\"6\xD57\xD6"),
        peg$decode("2\xD7\"\"6\xD77\xD8"),
        peg$decode("2\xD9\"\"6\xD97\xDA"),
        peg$decode("2\xDB\"\"6\xDB7\xDC"),
        peg$decode("2\xDD\"\"6\xDD7\xDE"),
        peg$decode("2\xDF\"\"6\xDF7\xE0"),
        peg$decode("2\xE1\"\"6\xE17\xE2"),
        peg$decode("2\xE3\"\"6\xE37\xE4"),
        peg$decode("2\xE5\"\"6\xE57\xE6"),
        peg$decode("2\xE7\"\"6\xE77\xE8"),
        peg$decode("2\xE9\"\"6\xE97\xEA"),
        peg$decode("%;\x85.Y &;\x86.S &;\x88.M &;\x89.G &;\x8A.A &;\x8B.; &;\x8C.5 &;\x8F./ &;\x8D.) &;\x8E.# &;6/& 8!:\xEB! )"),
        peg$decode("%;\x84/G#;'/>$;\x92/5$;'/,$;\x94/#$+%)(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%;\x93/' 8!:\xEC!! )"),
        peg$decode("%;!/5#;!/,$;!/#$+#)(#'#(\"'#&'#"),
        peg$decode("%$;*.A &;+.; &;-.5 &;3./ &;4.) &;'.# &;(0G*;*.A &;+.; &;-.5 &;3./ &;4.) &;'.# &;(&/& 8!:\xED! )"),
        peg$decode("%;\xB6/Y#$%;A/,#;\xB6/#$+\")(\"'#&'#06*%;A/,#;\xB6/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%;9/N#%2:\"\"6:7;/,#;9/#$+\")(\"'#&'#.\" &\"/'$8\":\xEE\" )(\"'#&'#"),
        peg$decode("%;:.c &%;\x98/Y#$%;A/,#;\x98/#$+\")(\"'#&'#06*%;A/,#;\x98/#$+\")(\"'#&'#&/#$+\")(\"'#&'#/& 8!:\xEF! )"),
        peg$decode("%;L.# &;\x99/]#$%;B/,#;\x9B/#$+\")(\"'#&'#06*%;B/,#;\x9B/#$+\")(\"'#&'#&/'$8\":\xF0\" )(\"'#&'#"),
        peg$decode("%;\x9A.\" &\"/>#;@/5$;M/,$;?/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode("%%;6/Y#$%;./,#;6/#$+\")(\"'#&'#06*%;./,#;6/#$+\")(\"'#&'#&/#$+\")(\"'#&'#.# &;H/' 8!:\xF1!! )"),
        peg$decode(";\x9C.) &;\x9D.# &;\xA0"),
        peg$decode("%3\xF2\"\"5!7\xF3/:#;</1$;\x9F/($8#:\xF4#! )(#'#(\"'#&'#"),
        peg$decode("%3\xF5\"\"5'7\xF6/:#;</1$;\x9E/($8#:\xF7#! )(#'#(\"'#&'#"),
        peg$decode("%$;!/&#0#*;!&&&#/' 8!:\xF8!! )"),
        peg$decode("%2\xF9\"\"6\xF97\xFA/o#%2J\"\"6J7K/M#;!.\" &\"/?$;!.\" &\"/1$;!.\" &\"/#$+$)($'#(#'#(\"'#&'#.\" &\"/'$8\":\xFB\" )(\"'#&'#"),
        peg$decode("%;6/J#%;</,#;\xA1/#$+\")(\"'#&'#.\" &\"/)$8\":\xFC\"\"! )(\"'#&'#"),
        peg$decode(";6.) &;T.# &;H"),
        peg$decode("%;\xA3/Y#$%;B/,#;\xA4/#$+\")(\"'#&'#06*%;B/,#;\xA4/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%3\xFD\"\"5&7\xFE.G &3\xFF\"\"5'7\u0100.; &3\u0101\"\"5$7\u0102./ &3\u0103\"\"5%7\u0104.# &;6/& 8!:\u0105! )"),
        peg$decode(";\xA5.# &;\xA0"),
        peg$decode("%3\u0106\"\"5(7\u0107/M#;</D$3\u0108\"\"5(7\u0109./ &3\u010A\"\"5(7\u010B.# &;6/#$+#)(#'#(\"'#&'#"),
        peg$decode("%;6/Y#$%;A/,#;6/#$+\")(\"'#&'#06*%;A/,#;6/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%$;!/&#0#*;!&&&#/' 8!:\u010C!! )"),
        peg$decode("%;\xA9/& 8!:\u010D! )"),
        peg$decode("%;\xAA/k#;;/b$;\xAF/Y$$%;B/,#;\xB0/#$+\")(\"'#&'#06*%;B/,#;\xB0/#$+\")(\"'#&'#&/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode(";\xAB.# &;\xAC"),
        peg$decode("3\u010E\"\"5$7\u010F.S &3\u0110\"\"5%7\u0111.G &3\u0112\"\"5%7\u0113.; &3\u0114\"\"5%7\u0115./ &3\u0116\"\"5+7\u0117.# &;\xAD"),
        peg$decode("3\u0118\"\"5'7\u0119./ &3\u011A\"\"5)7\u011B.# &;\xAD"),
        peg$decode(";6.# &;\xAE"),
        peg$decode("%3\u011C\"\"5\"7\u011D/,#;6/#$+\")(\"'#&'#"),
        peg$decode(";\xAD.# &;6"),
        peg$decode("%;6/5#;</,$;\xB1/#$+#)(#'#(\"'#&'#"),
        peg$decode(";6.# &;H"),
        peg$decode("%;\xB3/5#;./,$;\x90/#$+#)(#'#(\"'#&'#"),
        peg$decode("%$;!/&#0#*;!&&&#/' 8!:\u011E!! )"),
        peg$decode("%;\x9E/' 8!:\u011F!! )"),
        peg$decode("%;\xB6/^#$%;B/,#;\xA0/#$+\")(\"'#&'#06*%;B/,#;\xA0/#$+\")(\"'#&'#&/($8\":\u0120\"!!)(\"'#&'#"),
        peg$decode("%%;7/e#$%2J\"\"6J7K/,#;7/#$+\")(\"'#&'#0<*%2J\"\"6J7K/,#;7/#$+\")(\"'#&'#&/#$+\")(\"'#&'#/\"!&,)"),
        peg$decode("%;L.# &;\x99/]#$%;B/,#;\xB8/#$+\")(\"'#&'#06*%;B/,#;\xB8/#$+\")(\"'#&'#&/'$8\":\u0121\" )(\"'#&'#"),
        peg$decode(";\xB9.# &;\xA0"),
        peg$decode("%3\u0122\"\"5#7\u0123/:#;</1$;6/($8#:\u0124#! )(#'#(\"'#&'#"),
        peg$decode("%$;!/&#0#*;!&&&#/' 8!:\u0125!! )"),
        peg$decode("%;\x9E/' 8!:\u0126!! )"),
        peg$decode("%$;\x9A0#*;\x9A&/x#;@/o$;M/f$;?/]$$%;B/,#;\xA0/#$+\")(\"'#&'#06*%;B/,#;\xA0/#$+\")(\"'#&'#&/'$8%:\u0127% )(%'#($'#(#'#(\"'#&'#"),
        peg$decode(";\xBE"),
        peg$decode("%3\u0128\"\"5&7\u0129/k#;./b$;\xC1/Y$$%;A/,#;\xC1/#$+\")(\"'#&'#06*%;A/,#;\xC1/#$+\")(\"'#&'#&/#$+$)($'#(#'#(\"'#&'#.# &;\xBF"),
        peg$decode("%;6/k#;./b$;\xC0/Y$$%;A/,#;\xC0/#$+\")(\"'#&'#06*%;A/,#;\xC0/#$+\")(\"'#&'#&/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode("%;6/;#;</2$;6.# &;H/#$+#)(#'#(\"'#&'#"),
        peg$decode(";\xC2.G &;\xC4.A &;\xC6.; &;\xC8.5 &;\xC9./ &;\xCA.) &;\xCB.# &;\xC0"),
        peg$decode("%3\u012A\"\"5%7\u012B/5#;</,$;\xC3/#$+#)(#'#(\"'#&'#"),
        peg$decode("%;I/' 8!:\u012C!! )"),
        peg$decode("%3\u012D\"\"5&7\u012E/\x97#;</\x8E$;D/\x85$;\xC5/|$$%$;'/&#0#*;'&&&#/,#;\xC5/#$+\")(\"'#&'#0C*%$;'/&#0#*;'&&&#/,#;\xC5/#$+\")(\"'#&'#&/,$;E/#$+&)(&'#(%'#($'#(#'#(\"'#&'#"),
        peg$decode(";t.# &;w"),
        peg$decode("%3\u012F\"\"5%7\u0130/5#;</,$;\xC7/#$+#)(#'#(\"'#&'#"),
        peg$decode("%;I/' 8!:\u0131!! )"),
        peg$decode("%3\u0132\"\"5&7\u0133/:#;</1$;I/($8#:\u0134#! )(#'#(\"'#&'#"),
        peg$decode("%3\u0135\"\"5%7\u0136/]#;</T$%3\u0137\"\"5$7\u0138/& 8!:\u0139! ).4 &%3\u013A\"\"5%7\u013B/& 8!:\u013C! )/#$+#)(#'#(\"'#&'#"),
        peg$decode("%3\u013D\"\"5)7\u013E/R#;</I$3\u013F\"\"5#7\u0140./ &3\u0141\"\"5(7\u0142.# &;6/($8#:\u0143#! )(#'#(\"'#&'#"),
        peg$decode("%3\u0144\"\"5#7\u0145/\x93#;</\x8A$;D/\x81$%;\xCC/e#$%2D\"\"6D7E/,#;\xCC/#$+\")(\"'#&'#0<*%2D\"\"6D7E/,#;\xCC/#$+\")(\"'#&'#&/#$+\")(\"'#&'#/,$;E/#$+%)(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%3\u0146\"\"5(7\u0147./ &3\u0148\"\"5$7\u0149.# &;6/' 8!:\u014A!! )"),
        peg$decode("%;6/Y#$%;A/,#;6/#$+\")(\"'#&'#06*%;A/,#;6/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%;\xCF/G#;./>$;\xCF/5$;./,$;\x90/#$+%)(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%$;!/&#0#*;!&&&#/' 8!:\u014B!! )"),
        peg$decode("%;\xD1/]#$%;A/,#;\xD1/#$+\")(\"'#&'#06*%;A/,#;\xD1/#$+\")(\"'#&'#&/'$8\":\u014C\" )(\"'#&'#"),
        peg$decode("%;\x99/]#$%;B/,#;\xA0/#$+\")(\"'#&'#06*%;B/,#;\xA0/#$+\")(\"'#&'#&/'$8\":\u014D\" )(\"'#&'#"),
        peg$decode("%;L.O &;\x99.I &%;@.\" &\"/:#;t/1$;?.\" &\"/#$+#)(#'#(\"'#&'#/]#$%;B/,#;\xA0/#$+\")(\"'#&'#06*%;B/,#;\xA0/#$+\")(\"'#&'#&/'$8\":\u014E\" )(\"'#&'#"),
        peg$decode("%;\xD4/]#$%;B/,#;\xD5/#$+\")(\"'#&'#06*%;B/,#;\xD5/#$+\")(\"'#&'#&/'$8\":\u014F\" )(\"'#&'#"),
        peg$decode("%;\x96/& 8!:\u0150! )"),
        peg$decode("%3\u0151\"\"5(7\u0152/:#;</1$;6/($8#:\u0153#! )(#'#(\"'#&'#.g &%3\u0154\"\"5&7\u0155/:#;</1$;6/($8#:\u0156#! )(#'#(\"'#&'#.: &%3\u0157\"\"5*7\u0158/& 8!:\u0159! ).# &;\xA0"),
        peg$decode("%%;6/k#$%;A/2#;6/)$8\":\u015A\"\"$ )(\"'#&'#0<*%;A/2#;6/)$8\":\u015A\"\"$ )(\"'#&'#&/)$8\":\u015B\"\"! )(\"'#&'#.\" &\"/' 8!:\u015C!! )"),
        peg$decode("%;\xD8/Y#$%;A/,#;\xD8/#$+\")(\"'#&'#06*%;A/,#;\xD8/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%;\x99/Y#$%;B/,#;\xA0/#$+\")(\"'#&'#06*%;B/,#;\xA0/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%$;!/&#0#*;!&&&#/' 8!:\u015D!! )"),
        peg$decode("%;\xDB/Y#$%;B/,#;\xDC/#$+\")(\"'#&'#06*%;B/,#;\xDC/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%3\u015E\"\"5&7\u015F.; &3\u0160\"\"5'7\u0161./ &3\u0162\"\"5*7\u0163.# &;6/& 8!:\u0164! )"),
        peg$decode("%3\u0165\"\"5&7\u0166/:#;</1$;\xDD/($8#:\u0167#! )(#'#(\"'#&'#.} &%3\xF5\"\"5'7\xF6/:#;</1$;\x9E/($8#:\u0168#! )(#'#(\"'#&'#.P &%3\u0169\"\"5+7\u016A/:#;</1$;\x9E/($8#:\u016B#! )(#'#(\"'#&'#.# &;\xA0"),
        peg$decode("3\u016C\"\"5+7\u016D.k &3\u016E\"\"5)7\u016F._ &3\u0170\"\"5(7\u0171.S &3\u0172\"\"5'7\u0173.G &3\u0174\"\"5&7\u0175.; &3\u0176\"\"5*7\u0177./ &3\u0178\"\"5)7\u0179.# &;6"),
        peg$decode(";1.\" &\""),
        peg$decode("%%;6/k#$%;A/2#;6/)$8\":\u015A\"\"$ )(\"'#&'#0<*%;A/2#;6/)$8\":\u015A\"\"$ )(\"'#&'#&/)$8\":\u015B\"\"! )(\"'#&'#.\" &\"/' 8!:\u017A!! )"),
        peg$decode("%;L.# &;\x99/]#$%;B/,#;\xE1/#$+\")(\"'#&'#06*%;B/,#;\xE1/#$+\")(\"'#&'#&/'$8\":\u017B\" )(\"'#&'#"),
        peg$decode(";\xB9.# &;\xA0"),
        peg$decode("%;\xE3/Y#$%;A/,#;\xE3/#$+\")(\"'#&'#06*%;A/,#;\xE3/#$+\")(\"'#&'#&/#$+\")(\"'#&'#"),
        peg$decode("%;\xEA/k#;./b$;\xED/Y$$%;B/,#;\xE4/#$+\")(\"'#&'#06*%;B/,#;\xE4/#$+\")(\"'#&'#&/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode(";\xE5.; &;\xE6.5 &;\xE7./ &;\xE8.) &;\xE9.# &;\xA0"),
        peg$decode("%3\u017C\"\"5#7\u017D/:#;</1$;\xF0/($8#:\u017E#! )(#'#(\"'#&'#"),
        peg$decode("%3\u017F\"\"5%7\u0180/:#;</1$;T/($8#:\u0181#! )(#'#(\"'#&'#"),
        peg$decode("%3\u0182\"\"5(7\u0183/F#;</=$;\\.) &;Y.# &;X/($8#:\u0184#! )(#'#(\"'#&'#"),
        peg$decode("%3\u0185\"\"5&7\u0186/:#;</1$;6/($8#:\u0187#! )(#'#(\"'#&'#"),
        peg$decode("%3\u0188\"\"5%7\u0189/A#;</8$$;!0#*;!&/($8#:\u018A#! )(#'#(\"'#&'#"),
        peg$decode("%;\xEB/G#;;/>$;6/5$;;/,$;\xEC/#$+%)(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%3\x92\"\"5#7\xD3.# &;6/' 8!:\u018B!! )"),
        peg$decode("%3\xB1\"\"5#7\u018C.G &3\xB3\"\"5#7\u018D.; &3\xB7\"\"5#7\u018E./ &3\xB5\"\"5$7\u018F.# &;6/' 8!:\u0190!! )"),
        peg$decode("%;\xEE/D#%;C/,#;\xEF/#$+\")(\"'#&'#.\" &\"/#$+\")(\"'#&'#"),
        peg$decode("%;U.) &;\\.# &;X/& 8!:\u0191! )"),
        peg$decode("%%;!.\" &\"/[#;!.\" &\"/M$;!.\" &\"/?$;!.\" &\"/1$;!.\" &\"/#$+%)(%'#($'#(#'#(\"'#&'#/' 8!:\u0192!! )"),
        peg$decode("%%;!/?#;!.\" &\"/1$;!.\" &\"/#$+#)(#'#(\"'#&'#/' 8!:\u0193!! )"),
        peg$decode(";\xBE"),
        peg$decode("%;\x9E/^#$%;B/,#;\xF3/#$+\")(\"'#&'#06*%;B/,#;\xF3/#$+\")(\"'#&'#&/($8\":\u0194\"!!)(\"'#&'#"),
        peg$decode(";\xF4.# &;\xA0"),
        peg$decode("%2\u0195\"\"6\u01957\u0196/L#;</C$2\u0197\"\"6\u01977\u0198.) &2\u0199\"\"6\u01997\u019A/($8#:\u019B#! )(#'#(\"'#&'#"),
        peg$decode("%;\x9E/^#$%;B/,#;\xA0/#$+\")(\"'#&'#06*%;B/,#;\xA0/#$+\")(\"'#&'#&/($8\":\u019C\"!!)(\"'#&'#"),
        peg$decode("%;6/5#;0/,$;\xF7/#$+#)(#'#(\"'#&'#"),
        peg$decode("$;2.) &;4.# &;.0/*;2.) &;4.# &;.&"),
        peg$decode("$;%0#*;%&"),
        peg$decode("%;\xFA/;#28\"\"6879/,$;\xFB/#$+#)(#'#(\"'#&'#"),
        peg$decode("%3\u019D\"\"5%7\u019E.) &3\u019F\"\"5$7\u01A0/' 8!:\u01A1!! )"),
        peg$decode("%;\xFC/J#%28\"\"6879/,#;^/#$+\")(\"'#&'#.\" &\"/#$+\")(\"'#&'#"),
        peg$decode("%;\\.) &;X.# &;\x82/' 8!:\u01A2!! )"),
        peg$decode(";\".S &;!.M &2F\"\"6F7G.A &2J\"\"6J7K.5 &2H\"\"6H7I.) &2N\"\"6N7O"),
        peg$decode("2L\"\"6L7M.\x95 &2B\"\"6B7C.\x89 &2<\"\"6<7=.} &2R\"\"6R7S.q &2T\"\"6T7U.e &2V\"\"6V7W.Y &2P\"\"6P7Q.M &2@\"\"6@7A.A &2D\"\"6D7E.5 &22\"\"6273.) &2>\"\"6>7?"),
        peg$decode("%;\u0100/b#28\"\"6879/S$;\xFB/J$%2\u01A3\"\"6\u01A37\u01A4/,#;\xEC/#$+\")(\"'#&'#.\" &\"/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode("%3\u01A5\"\"5%7\u01A6.) &3\u01A7\"\"5$7\u01A8/' 8!:\u01A1!! )"),
        peg$decode("%3\xB1\"\"5#7\xB2.6 &3\xB3\"\"5#7\xB4.* &$;+0#*;+&/' 8!:\u01A9!! )"),
        peg$decode("%;\u0104/\x87#2F\"\"6F7G/x$;\u0103/o$2F\"\"6F7G/`$;\u0103/W$2F\"\"6F7G/H$;\u0103/?$2F\"\"6F7G/0$;\u0105/'$8):\u01AA) )()'#(('#(''#(&'#(%'#($'#(#'#(\"'#&'#"),
        peg$decode("%;#/>#;#/5$;#/,$;#/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode("%;\u0103/,#;\u0103/#$+\")(\"'#&'#"),
        peg$decode("%;\u0103/5#;\u0103/,$;\u0103/#$+#)(#'#(\"'#&'#"),
        peg$decode("%;q/T#$;m0#*;m&/D$%; /,#;\xF8/#$+\")(\"'#&'#.\" &\"/#$+#)(#'#(\"'#&'#"),
        peg$decode("%2\u01AB\"\"6\u01AB7\u01AC.) &2\u01AD\"\"6\u01AD7\u01AE/w#;0/n$;\u0108/e$$%;B/2#;\u0109.# &;\xA0/#$+\")(\"'#&'#0<*%;B/2#;\u0109.# &;\xA0/#$+\")(\"'#&'#&/#$+$)($'#(#'#(\"'#&'#"),
        peg$decode(";\x99.# &;L"),
        peg$decode("%2\u01AF\"\"6\u01AF7\u01B0/5#;</,$;\u010A/#$+#)(#'#(\"'#&'#"),
        peg$decode("%;D/S#;,/J$2:\"\"6:7;/;$;,.# &;T/,$;E/#$+%)(%'#($'#(#'#(\"'#&'#")
    ];
    let peg$currPos = 0;
    let peg$savedPos = 0;
    const peg$posDetailsCache = [{ line: 1, column: 1 }];
    let peg$maxFailPos = 0;
    let peg$maxFailExpected = [];
    let peg$silentFails = 0;
    let peg$result;
    if (options.startRule !== undefined) {
        if (!(options.startRule in peg$startRuleIndices)) {
            throw new Error("Can't start parsing from rule \"" + options.startRule + "\".");
        }
        peg$startRuleIndex = peg$startRuleIndices[options.startRule];
    }
    function text() {
        return input.substring(peg$savedPos, peg$currPos);
    }
    function location() {
        return peg$computeLocation(peg$savedPos, peg$currPos);
    }
    function expected(description, location1) {
        location1 = location1 !== undefined
            ? location1
            : peg$computeLocation(peg$savedPos, peg$currPos);
        throw peg$buildStructuredError([peg$otherExpectation(description)], input.substring(peg$savedPos, peg$currPos), location1);
    }
    function error(message, location1) {
        location1 = location1 !== undefined
            ? location1
            : peg$computeLocation(peg$savedPos, peg$currPos);
        throw peg$buildSimpleError(message, location1);
    }
    function peg$literalExpectation(text1, ignoreCase) {
        return { type: "literal", text: text1, ignoreCase: ignoreCase };
    }
    function peg$classExpectation(parts, inverted, ignoreCase) {
        return { type: "class", parts: parts, inverted: inverted, ignoreCase: ignoreCase };
    }
    function peg$anyExpectation() {
        return { type: "any" };
    }
    function peg$endExpectation() {
        return { type: "end" };
    }
    function peg$otherExpectation(description) {
        return { type: "other", description: description };
    }
    function peg$computePosDetails(pos) {
        let details = peg$posDetailsCache[pos];
        let p;
        if (details) {
            return details;
        }
        else {
            p = pos - 1;
            while (!peg$posDetailsCache[p]) {
                p--;
            }
            details = peg$posDetailsCache[p];
            details = {
                line: details.line,
                column: details.column
            };
            while (p < pos) {
                if (input.charCodeAt(p) === 10) {
                    details.line++;
                    details.column = 1;
                }
                else {
                    details.column++;
                }
                p++;
            }
            peg$posDetailsCache[pos] = details;
            return details;
        }
    }
    function peg$computeLocation(startPos, endPos) {
        const startPosDetails = peg$computePosDetails(startPos);
        const endPosDetails = peg$computePosDetails(endPos);
        return {
            source: peg$source,
            start: {
                offset: startPos,
                line: startPosDetails.line,
                column: startPosDetails.column
            },
            end: {
                offset: endPos,
                line: endPosDetails.line,
                column: endPosDetails.column
            }
        };
    }
    function peg$fail(expected1) {
        if (peg$currPos < peg$maxFailPos) {
            return;
        }
        if (peg$currPos > peg$maxFailPos) {
            peg$maxFailPos = peg$currPos;
            peg$maxFailExpected = [];
        }
        peg$maxFailExpected.push(expected1);
    }
    function peg$buildSimpleError(message, location1) {
        return new SyntaxError(message, [], "", location1);
    }
    function peg$buildStructuredError(expected1, found, location1) {
        return new SyntaxError(SyntaxError.buildMessage(expected1, found), expected1, found, location1);
    }
    function peg$decode(s) {
        return s.split("").map((ch) => ch.charCodeAt(0) - 32);
    }
    function peg$parseRule(index) {
        const bc = peg$bytecode[index];
        let ip = 0;
        const ips = [];
        let end = bc.length;
        const ends = [];
        const stack = [];
        let params;
        while (true) {
            while (ip < end) {
                switch (bc[ip]) {
                    case 0:
                        stack.push(peg$consts[bc[ip + 1]]);
                        ip += 2;
                        break;
                    case 1:
                        stack.push(undefined);
                        ip++;
                        break;
                    case 2:
                        stack.push(null);
                        ip++;
                        break;
                    case 3:
                        stack.push(peg$FAILED);
                        ip++;
                        break;
                    case 4:
                        stack.push([]);
                        ip++;
                        break;
                    case 5:
                        stack.push(peg$currPos);
                        ip++;
                        break;
                    case 6:
                        stack.pop();
                        ip++;
                        break;
                    case 7:
                        peg$currPos = stack.pop();
                        ip++;
                        break;
                    case 8:
                        stack.length -= bc[ip + 1];
                        ip += 2;
                        break;
                    case 9:
                        stack.splice(-2, 1);
                        ip++;
                        break;
                    case 10:
                        stack[stack.length - 2].push(stack.pop());
                        ip++;
                        break;
                    case 11:
                        stack.push(stack.splice(stack.length - bc[ip + 1], bc[ip + 1]));
                        ip += 2;
                        break;
                    case 12:
                        stack.push(input.substring(stack.pop(), peg$currPos));
                        ip++;
                        break;
                    case 13:
                        ends.push(end);
                        ips.push(ip + 3 + bc[ip + 1] + bc[ip + 2]);
                        if (stack[stack.length - 1]) {
                            end = ip + 3 + bc[ip + 1];
                            ip += 3;
                        }
                        else {
                            end = ip + 3 + bc[ip + 1] + bc[ip + 2];
                            ip += 3 + bc[ip + 1];
                        }
                        break;
                    case 14:
                        ends.push(end);
                        ips.push(ip + 3 + bc[ip + 1] + bc[ip + 2]);
                        if (stack[stack.length - 1] === peg$FAILED) {
                            end = ip + 3 + bc[ip + 1];
                            ip += 3;
                        }
                        else {
                            end = ip + 3 + bc[ip + 1] + bc[ip + 2];
                            ip += 3 + bc[ip + 1];
                        }
                        break;
                    case 15:
                        ends.push(end);
                        ips.push(ip + 3 + bc[ip + 1] + bc[ip + 2]);
                        if (stack[stack.length - 1] !== peg$FAILED) {
                            end = ip + 3 + bc[ip + 1];
                            ip += 3;
                        }
                        else {
                            end = ip + 3 + bc[ip + 1] + bc[ip + 2];
                            ip += 3 + bc[ip + 1];
                        }
                        break;
                    case 16:
                        if (stack[stack.length - 1] !== peg$FAILED) {
                            ends.push(end);
                            ips.push(ip);
                            end = ip + 2 + bc[ip + 1];
                            ip += 2;
                        }
                        else {
                            ip += 2 + bc[ip + 1];
                        }
                        break;
                    case 17:
                        ends.push(end);
                        ips.push(ip + 3 + bc[ip + 1] + bc[ip + 2]);
                        if (input.length > peg$currPos) {
                            end = ip + 3 + bc[ip + 1];
                            ip += 3;
                        }
                        else {
                            end = ip + 3 + bc[ip + 1] + bc[ip + 2];
                            ip += 3 + bc[ip + 1];
                        }
                        break;
                    case 18:
                        ends.push(end);
                        ips.push(ip + 4 + bc[ip + 2] + bc[ip + 3]);
                        if (input.substr(peg$currPos, peg$consts[bc[ip + 1]].length) === peg$consts[bc[ip + 1]]) {
                            end = ip + 4 + bc[ip + 2];
                            ip += 4;
                        }
                        else {
                            end = ip + 4 + bc[ip + 2] + bc[ip + 3];
                            ip += 4 + bc[ip + 2];
                        }
                        break;
                    case 19:
                        ends.push(end);
                        ips.push(ip + 4 + bc[ip + 2] + bc[ip + 3]);
                        if (input.substr(peg$currPos, peg$consts[bc[ip + 1]].length).toLowerCase() === peg$consts[bc[ip + 1]]) {
                            end = ip + 4 + bc[ip + 2];
                            ip += 4;
                        }
                        else {
                            end = ip + 4 + bc[ip + 2] + bc[ip + 3];
                            ip += 4 + bc[ip + 2];
                        }
                        break;
                    case 20:
                        ends.push(end);
                        ips.push(ip + 4 + bc[ip + 2] + bc[ip + 3]);
                        if (peg$consts[bc[ip + 1]].test(input.charAt(peg$currPos))) {
                            end = ip + 4 + bc[ip + 2];
                            ip += 4;
                        }
                        else {
                            end = ip + 4 + bc[ip + 2] + bc[ip + 3];
                            ip += 4 + bc[ip + 2];
                        }
                        break;
                    case 21:
                        stack.push(input.substr(peg$currPos, bc[ip + 1]));
                        peg$currPos += bc[ip + 1];
                        ip += 2;
                        break;
                    case 22:
                        stack.push(peg$consts[bc[ip + 1]]);
                        peg$currPos += peg$consts[bc[ip + 1]].length;
                        ip += 2;
                        break;
                    case 23:
                        stack.push(peg$FAILED);
                        if (peg$silentFails === 0) {
                            peg$fail(peg$consts[bc[ip + 1]]);
                        }
                        ip += 2;
                        break;
                    case 24:
                        peg$savedPos = stack[stack.length - 1 - bc[ip + 1]];
                        ip += 2;
                        break;
                    case 25:
                        peg$savedPos = peg$currPos;
                        ip++;
                        break;
                    case 26:
                        params = bc.slice(ip + 4, ip + 4 + bc[ip + 3])
                            .map(function (p) { return stack[stack.length - 1 - p]; });
                        stack.splice(stack.length - bc[ip + 2], bc[ip + 2], peg$consts[bc[ip + 1]].apply(null, params));
                        ip += 4 + bc[ip + 3];
                        break;
                    case 27:
                        stack.push(peg$parseRule(bc[ip + 1]));
                        ip += 2;
                        break;
                    case 28:
                        peg$silentFails++;
                        ip++;
                        break;
                    case 29:
                        peg$silentFails--;
                        ip++;
                        break;
                    default:
                        throw new Error("Invalid opcode: " + bc[ip] + ".");
                }
            }
            if (ends.length > 0) {
                end = ends.pop();
                ip = ips.pop();
            }
            else {
                break;
            }
        }
        return stack[0];
    }
    options.data = {};
    function list(head, tail) {
        return [head].concat(tail);
    }
    peg$result = peg$parseRule(peg$startRuleIndex);
    if (peg$result !== peg$FAILED && peg$currPos === input.length) {
        return peg$result;
    }
    else {
        if (peg$result !== peg$FAILED && peg$currPos < input.length) {
            peg$fail(peg$endExpectation());
        }
        throw peg$buildStructuredError(peg$maxFailExpected, peg$maxFailPos < input.length ? input.charAt(peg$maxFailPos) : null, peg$maxFailPos < input.length
            ? peg$computeLocation(peg$maxFailPos, peg$maxFailPos + 1)
            : peg$computeLocation(peg$maxFailPos, peg$maxFailPos));
    }
}
const parse = peg$parse;


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "URI": () => ( URI),
   "equivalentURI": () => ( equivalentURI)
 });
 var _parameters_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(25);
/* eslint-disable @typescript-eslint/no-explicit-any */

/** @public */
class URI extends _parameters_js__WEBPACK_IMPORTED_MODULE_0__.Parameters {
    /**
     * @param scheme
     * @param user
     * @param host
     * @param port
     * @param parameters
     * @param headers
     */
    constructor(scheme = "sip", user, host, port, parameters, headers) {
        super(parameters || {});
        this.headers = {};
        if (!host) {
            throw new TypeError('missing or invalid "host" parameter');
        }
        for (const header in headers) {
            // eslint-disable-next-line no-prototype-builtins
            if (headers.hasOwnProperty(header)) {
                this.setHeader(header, headers[header]);
            }
        }
        this.raw = {
            scheme,
            user,
            host,
            port
        };
        this.normal = {
            scheme: scheme.toLowerCase(),
            user,
            host: host.toLowerCase(),
            port
        };
    }
    get scheme() { return this.normal.scheme; }
    set scheme(value) {
        this.raw.scheme = value;
        this.normal.scheme = value.toLowerCase();
    }
    get user() { return this.normal.user; }
    set user(value) {
        this.normal.user = this.raw.user = value;
    }
    get host() { return this.normal.host; }
    set host(value) {
        this.raw.host = value;
        this.normal.host = value.toLowerCase();
    }
    get aor() { return this.normal.user + "@" + this.normal.host; }
    get port() { return this.normal.port; }
    set port(value) {
        this.normal.port = this.raw.port = value === 0 ? value : value;
    }
    setHeader(name, value) {
        this.headers[this.headerize(name)] = (value instanceof Array) ? value : [value];
    }
    getHeader(name) {
        if (name) {
            return this.headers[this.headerize(name)];
        }
    }
    hasHeader(name) {
        // eslint-disable-next-line no-prototype-builtins
        return !!name && !!this.headers.hasOwnProperty(this.headerize(name));
    }
    deleteHeader(header) {
        header = this.headerize(header);
        // eslint-disable-next-line no-prototype-builtins
        if (this.headers.hasOwnProperty(header)) {
            const value = this.headers[header];
            delete this.headers[header];
            return value;
        }
    }
    clearHeaders() {
        this.headers = {};
    }
    clone() {
        return new URI(this._raw.scheme, this._raw.user || "", this._raw.host, this._raw.port, JSON.parse(JSON.stringify(this.parameters)), JSON.parse(JSON.stringify(this.headers)));
    }
    toRaw() {
        return this._toString(this._raw);
    }
    toString() {
        return this._toString(this._normal);
    }
    get _normal() { return this.normal; }
    get _raw() { return this.raw; }
    _toString(uri) {
        let uriString = uri.scheme + ":";
        if (!uri.scheme.toLowerCase().match("^sips?$")) {
            uriString += "//";
        }
        if (uri.user) {
            uriString += this.escapeUser(uri.user) + "@";
        }
        uriString += uri.host;
        if (uri.port || uri.port === 0) {
            uriString += ":" + uri.port;
        }
        for (const parameter in this.parameters) {
            // eslint-disable-next-line no-prototype-builtins
            if (this.parameters.hasOwnProperty(parameter)) {
                uriString += ";" + parameter;
                if (this.parameters[parameter] !== null) {
                    uriString += "=" + this.parameters[parameter];
                }
            }
        }
        const headers = [];
        for (const header in this.headers) {
            // eslint-disable-next-line no-prototype-builtins
            if (this.headers.hasOwnProperty(header)) {
                // eslint-disable-next-line @typescript-eslint/no-for-in-array
                for (const idx in this.headers[header]) {
                    // eslint-disable-next-line no-prototype-builtins
                    if (this.headers[header].hasOwnProperty(idx)) {
                        headers.push(header + "=" + this.headers[header][idx]);
                    }
                }
            }
        }
        if (headers.length > 0) {
            uriString += "?" + headers.join("&");
        }
        return uriString;
    }





    escapeUser(user) {
        let decodedUser;
        // eslint-disable-next-line no-useless-catch
        try {
            decodedUser = decodeURIComponent(user);
        }
        catch (error) {
            throw error;
        }
        return encodeURIComponent(decodedUser)
            .replace(/%3A/ig, ":")
            .replace(/%2B/ig, "+")
            .replace(/%3F/ig, "?")
            .replace(/%2F/ig, "/");
    }
    headerize(str) {
        const exceptions = {
            "Call-Id": "Call-ID",
            "Cseq": "CSeq",
            "Min-Se": "Min-SE",
            "Rack": "RAck",
            "Rseq": "RSeq",
            "Www-Authenticate": "WWW-Authenticate",
        };
        const name = str.toLowerCase().replace(/_/g, "-").split("-");
        const parts = name.length;
        let hname = "";
        for (let part = 0; part < parts; part++) {
            if (part !== 0) {
                hname += "-";
            }
            hname += name[part].charAt(0).toUpperCase() + name[part].substring(1);
        }
        if (exceptions[hname]) {
            hname = exceptions[hname];
        }
        return hname;
    }
}
/**
 * @param a
 * @param b
 * @remarks
 * @internal
 */
function equivalentURI(a, b) {
    if (a.scheme !== b.scheme) {
        return false;
    }
    if (a.user !== b.user || a.host !== b.host || a.port !== b.port) {
        return false;
    }
    function compareParameters(a, b) {
        const parameterKeysA = Object.keys(a.parameters);
        const parameterKeysB = Object.keys(b.parameters);
        const intersection = parameterKeysA.filter(x => parameterKeysB.includes(x));
        if (!intersection.every(key => a.parameters[key] === b.parameters[key])) {
            return false;
        }
        if (!["user", "ttl", "method", "transport"].every(key => a.hasParam(key) && b.hasParam(key) || !a.hasParam(key) && !b.hasParam(key))) {
            return false;
        }
        if (!["maddr"].every(key => a.hasParam(key) && b.hasParam(key) || !a.hasParam(key) && !b.hasParam(key))) {
            return false;
        }
        return true;
    }
    if (!compareParameters(a, b)) {
        return false;
    }
    const headerKeysA = Object.keys(a.headers);
    const headerKeysB = Object.keys(b.headers);
    if (headerKeysA.length !== 0 || headerKeysB.length !== 0) {
        if (headerKeysA.length !== headerKeysB.length) {
            return false;
        }
        const intersection = headerKeysA.filter(x => headerKeysB.includes(x));
        if (intersection.length !== headerKeysB.length) {
            return false;
        }
        if (!intersection.every(key => a.headers[key].length && b.headers[key].length && a.headers[key][0] === b.headers[key][0])) {
            return false;
        }
    }
    return true;
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Parameters": () => ( Parameters)
 });
/**
 * @internal
 */
class Parameters {
    constructor(parameters) {
        this.parameters = {};
        for (const param in parameters) {
            // eslint-disable-next-line no-prototype-builtins
            if (parameters.hasOwnProperty(param)) {
                this.setParam(param, parameters[param]);
            }
        }
    }
    setParam(key, value) {
        if (key) {
            this.parameters[key.toLowerCase()] = (typeof value === "undefined" || value === null) ? null : value.toString();
        }
    }
    getParam(key) {
        if (key) {
            return this.parameters[key.toLowerCase()];
        }
    }
    hasParam(key) {
        return !!(key && this.parameters[key.toLowerCase()] !== undefined);
    }
    deleteParam(key) {
        key = key.toLowerCase();
        if (this.hasParam(key)) {
            const value = this.parameters[key];
            delete this.parameters[key];
            return value;
        }
    }
    clearParams() {
        this.parameters = {};
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "NameAddrHeader": () => ( NameAddrHeader)
 });
 var _parameters_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(25);

/** @public */
class NameAddrHeader extends _parameters_js__WEBPACK_IMPORTED_MODULE_0__.Parameters {
    /**
     * @param uri
     * @param displayName
     * @param parameters
     */
    constructor(uri, displayName, parameters) {
        super(parameters);
        this.uri = uri;
        this._displayName = displayName;
    }
    get friendlyName() {
        return this.displayName || this.uri.aor;
    }
    get displayName() { return this._displayName; }
    set displayName(value) {
        this._displayName = value;
    }
    clone() {
        return new NameAddrHeader(this.uri.clone(), this._displayName, JSON.parse(JSON.stringify(this.parameters)));
    }
    toString() {
        let body = (this.displayName || this.displayName === "0") ? '"' + this.displayName + '" ' : "";
        body += "<" + this.uri.toString() + ">";
        for (const parameter in this.parameters) {
            // eslint-disable-next-line no-prototype-builtins
            if (this.parameters.hasOwnProperty(parameter)) {
                body += ";" + parameter;
                if (this.parameters[parameter] !== null) {
                    body += "=" + this.parameters[parameter];
                }
            }
        }
        return body;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "IncomingResponseMessage": () => ( IncomingResponseMessage)
 });
 var _incoming_message_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(20);

/** @public */
class IncomingResponseMessage extends _incoming_message_js__WEBPACK_IMPORTED_MODULE_0__.IncomingMessage {
    constructor() {
        super();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "OutgoingRequestMessage": () => ( OutgoingRequestMessage)
 });
 var _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(26);
 var _utils_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(21);


/** @public */
class OutgoingRequestMessage {
    constructor(method, ruri, fromURI, toURI, options, extraHeaders, body) {
        this.headers = {};
        this.extraHeaders = [];
        this.options = OutgoingRequestMessage.getDefaultOptions();
        if (options) {
            this.options = Object.assign(Object.assign({}, this.options), options);
            if (this.options.optionTags && this.options.optionTags.length) {
                this.options.optionTags = this.options.optionTags.slice();
            }
            if (this.options.routeSet && this.options.routeSet.length) {
                this.options.routeSet = this.options.routeSet.slice();
            }
        }
        if (extraHeaders && extraHeaders.length) {
            this.extraHeaders = extraHeaders.slice();
        }
        if (body) {
            this.body = {
                body: body.content,
                contentType: body.contentType
            };
        }
        this.method = method;
        this.ruri = ruri.clone();
        this.fromURI = fromURI.clone();
        this.fromTag = this.options.fromTag ? this.options.fromTag : (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.newTag)();
        this.from = OutgoingRequestMessage.makeNameAddrHeader(this.fromURI, this.options.fromDisplayName, this.fromTag);
        this.toURI = toURI.clone();
        this.toTag = this.options.toTag;
        this.to = OutgoingRequestMessage.makeNameAddrHeader(this.toURI, this.options.toDisplayName, this.toTag);
        this.callId = this.options.callId ? this.options.callId : this.options.callIdPrefix + (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.createRandomToken)(15);
        this.cseq = this.options.cseq;
        this.setHeader("route", this.options.routeSet);
        this.setHeader("via", "");
        this.setHeader("to", this.to.toString());
        this.setHeader("from", this.from.toString());
        this.setHeader("cseq", this.cseq + " " + this.method);
        this.setHeader("call-id", this.callId);
        this.setHeader("max-forwards", "70");
    }
    static getDefaultOptions() {
        return {
            callId: "",
            callIdPrefix: "",
            cseq: 1,
            toDisplayName: "",
            toTag: "",
            fromDisplayName: "",
            fromTag: "",
            forceRport: false,
            hackViaTcp: false,
            optionTags: ["outbound"],
            routeSet: [],
            userAgentString: "sip.js",
            viaHost: ""
        };
    }
    static makeNameAddrHeader(uri, displayName, tag) {
        const parameters = {};
        if (tag) {
            parameters.tag = tag;
        }
        return new _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader(uri, displayName, parameters);
    }
    /**
     * @param name
     * @returns
     */
    getHeader(name) {
        const header = this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)];
        if (header) {
            if (header[0]) {
                return header[0];
            }
        }
        else {
            const regexp = new RegExp("^\\s*" + name + "\\s*:", "i");
            for (const exHeader of this.extraHeaders) {
                if (regexp.test(exHeader)) {
                    return exHeader.substring(exHeader.indexOf(":") + 1).trim();
                }
            }
        }
        return;
    }
    /**
     * @param name
     * @returns
     */
    getHeaders(name) {
        const result = [];
        const headerArray = this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)];
        if (headerArray) {
            for (const headerPart of headerArray) {
                result.push(headerPart);
            }
        }
        else {
            const regexp = new RegExp("^\\s*" + name + "\\s*:", "i");
            for (const exHeader of this.extraHeaders) {
                if (regexp.test(exHeader)) {
                    result.push(exHeader.substring(exHeader.indexOf(":") + 1).trim());
                }
            }
        }
        return result;
    }
    /**
     * @param name
     * @returns
     */
    hasHeader(name) {
        if (this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)]) {
            return true;
        }
        else {
            const regexp = new RegExp("^\\s*" + name + "\\s*:", "i");
            for (const extraHeader of this.extraHeaders) {
                if (regexp.test(extraHeader)) {
                    return true;
                }
            }
        }
        return false;
    }
    /**
     * @param name
     * @param value
     */
    setHeader(name, value) {
        this.headers[(0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.headerize)(name)] = value instanceof Array ? value : [value];
    }
    /**
     * @param branchParameter
     * @param transport
     */
    setViaHeader(branch, transport) {
        if (this.options.hackViaTcp) {
            transport = "TCP";
        }
        let via = "SIP/2.0/" + transport;
        via += " " + this.options.viaHost + ";branch=" + branch;
        if (this.options.forceRport) {
            via += ";rport";
        }
        this.setHeader("via", via);
        this.branch = branch;
    }
    toString() {
        let msg = "";
        msg += this.method + " " + this.ruri.toRaw() + " SIP/2.0\r\n";
        for (const header in this.headers) {
            if (this.headers[header]) {
                for (const headerPart of this.headers[header]) {
                    msg += header + ": " + headerPart + "\r\n";
                }
            }
        }
        for (const header of this.extraHeaders) {
            msg += header.trim() + "\r\n";
        }
        msg += "Supported: " + this.options.optionTags.join(", ") + "\r\n";
        msg += "User-Agent: " + this.options.userAgentString + "\r\n";
        if (this.body) {
            if (typeof this.body === "string") {
                msg += "Content-Length: " + (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.utf8Length)(this.body) + "\r\n\r\n";
                msg += this.body;
            }
            else {
                if (this.body.body && this.body.contentType) {
                    msg += "Content-Type: " + this.body.contentType + "\r\n";
                    msg += "Content-Length: " + (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.utf8Length)(this.body.body) + "\r\n\r\n";
                    msg += this.body.body;
                }
                else {
                    msg += "Content-Length: " + 0 + "\r\n\r\n";
                }
            }
        }
        else {
            msg += "Content-Length: " + 0 + "\r\n\r\n";
        }
        return msg;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "AllowedMethods": () => ( AllowedMethods)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(30);

const AllowedMethods = [
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.ACK,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.BYE,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.CANCEL,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.INFO,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.INVITE,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.MESSAGE,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.NOTIFY,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.OPTIONS,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.PRACK,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.REFER,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.REGISTER,
    _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.SUBSCRIBE
];


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "C": () => ( C)
 });
/* eslint-disable @typescript-eslint/no-namespace */
/** @internal */
var C;
(function (C) {
    C.ACK = "ACK";
    C.BYE = "BYE";
    C.CANCEL = "CANCEL";
    C.INFO = "INFO";
    C.INVITE = "INVITE";
    C.MESSAGE = "MESSAGE";
    C.NOTIFY = "NOTIFY";
    C.OPTIONS = "OPTIONS";
    C.REGISTER = "REGISTER";
    C.UPDATE = "UPDATE";
    C.SUBSCRIBE = "SUBSCRIBE";
    C.PUBLISH = "PUBLISH";
    C.REFER = "REFER";
    C.PRACK = "PRACK";
})(C = C || (C = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionState": () => ( SessionState),
   "SignalingState": () => ( SignalingState)
 });
/**
 * @remarks
 * @public
 */
var SessionState;
(function (SessionState) {
    SessionState["Initial"] = "Initial";
    SessionState["Early"] = "Early";
    SessionState["AckWait"] = "AckWait";
    SessionState["Confirmed"] = "Confirmed";
    SessionState["Terminated"] = "Terminated";
})(SessionState = SessionState || (SessionState = {}));
/**
 * @remarks
 * @public
 */
var SignalingState;
(function (SignalingState) {
    SignalingState["Initial"] = "Initial";
    SignalingState["HaveLocalOffer"] = "HaveLocalOffer";
    SignalingState["HaveRemoteOffer"] = "HaveRemoteOffer";
    SignalingState["Stable"] = "Stable";
    SignalingState["Closed"] = "Closed";
})(SignalingState = SignalingState || (SignalingState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Message": () => ( Message)
 });
/** @public */
class Message {
    /** @internal */
    constructor(incomingMessageRequest) {
        this.incomingMessageRequest = incomingMessageRequest;
    }
    get request() {
        return this.incomingMessageRequest.message;
    }
    accept(options) {
        this.incomingMessageRequest.accept(options);
        return Promise.resolve();
    }
    reject(options) {
        this.incomingMessageRequest.reject(options);
        return Promise.resolve();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Notification": () => ( Notification)
 });
/** @public */
class Notification {
    /** @internal */
    constructor(incomingNotifyRequest) {
        this.incomingNotifyRequest = incomingNotifyRequest;
    }
    get request() {
        return this.incomingNotifyRequest.message;
    }
    accept(options) {
        this.incomingNotifyRequest.accept(options);
        return Promise.resolve();
    }
    reject(options) {
        this.incomingNotifyRequest.reject(options);
        return Promise.resolve();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Referral": () => ( Referral)
 });
 var _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(26);

/** @public */
class Referral {
    /** @internal */
    constructor(incomingReferRequest, session) {
        this.incomingReferRequest = incomingReferRequest;
        this.session = session;
    }
    get referTo() {
        const referTo = this.incomingReferRequest.message.parseHeader("refer-to");
        if (!(referTo instanceof _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_0__.NameAddrHeader)) {
            throw new Error("Failed to parse Refer-To header.");
        }
        return referTo;
    }
    get referredBy() {
        return this.incomingReferRequest.message.getHeader("referred-by");
    }
    get replaces() {
        const value = this.referTo.uri.getHeader("replaces");
        if (value instanceof Array) {
            return value[0];
        }
        return value;
    }
    get request() {
        return this.incomingReferRequest.message;
    }
    accept(options = { statusCode: 202 }) {
        this.incomingReferRequest.accept(options);
        return Promise.resolve();
    }
    reject(options) {
        this.incomingReferRequest.reject(options);
        return Promise.resolve();
    }
    /**
     * @remarks
     * @param options
     * @param modifiers
     */
    makeInviter(options) {
        if (this.inviter) {
            return this.inviter;
        }
        const targetURI = this.referTo.uri.clone();
        targetURI.clearHeaders();
        options = options || {};
        const extraHeaders = (options.extraHeaders || []).slice();
        const replaces = this.replaces;
        if (replaces) {
            extraHeaders.push("Replaces: " + decodeURIComponent(replaces));
        }
        const referredBy = this.referredBy;
        if (referredBy) {
            extraHeaders.push("Referred-By: " + referredBy);
        }
        options.extraHeaders = extraHeaders;
        this.inviter = this.session.userAgent._makeInviter(targetURI, options);
        this.inviter._referred = this.session;
        this.session._referral = this.inviter;
        return this.inviter;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SIPExtension": () => ( SIPExtension),
   "UserAgentRegisteredOptionTags": () => ( UserAgentRegisteredOptionTags)
 });
/** @public */
var SIPExtension;
(function (SIPExtension) {
    SIPExtension["Required"] = "Required";
    SIPExtension["Supported"] = "Supported";
    SIPExtension["Unsupported"] = "Unsupported";
})(SIPExtension = SIPExtension || (SIPExtension = {}));
/**
 * @remarks
 * @public
 */
const UserAgentRegisteredOptionTags = {
    "100rel": true,
    "199": true,
    answermode: true,
    "early-session": true,
    eventlist: true,
    explicitsub: true,
    "from-change": true,
    "geolocation-http": true,
    "geolocation-sip": true,
    gin: true,
    gruu: true,
    histinfo: true,
    ice: true,
    join: true,
    "multiple-refer": true,
    norefersub: true,
    nosub: true,
    outbound: true,
    path: true,
    policy: true,
    precondition: true,
    pref: true,
    privacy: true,
    "recipient-list-invite": true,
    "recipient-list-message": true,
    "recipient-list-subscribe": true,
    replaces: true,
    "resource-priority": true,
    "sdp-anat": true,
    "sec-agree": true,
    tdialog: true,
    timer: true,
    uui: true
};


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "TransactionStateError": () => ( TransactionStateError)
 });
 var _exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class TransactionStateError extends _exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    constructor(message) {
        super(message ? message : "Transaction state error.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Timers": () => ( Timers)
 });
const T1 = 500;
const T2 = 4000;
const T4 = 5000;
/** @public */
const Timers = {
    T1,
    T2,
    T4,
    TIMER_B: 64 * T1,
    TIMER_D: 0 * T1,
    TIMER_F: 64 * T1,
    TIMER_H: 64 * T1,
    TIMER_I: 0 * T4,
    TIMER_J: 0 * T1,
    TIMER_K: 0 * T4,
    TIMER_L: 64 * T1,
    TIMER_M: 64 * T1,
    TIMER_N: 64 * T1,
    PROVISIONAL_RESPONSE_INTERVAL: 60000
};


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Inviter": () => ( Inviter)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(22);
 var _core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(30);
 var _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(31);
 var _core_messages_utils_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(21);
 var _session_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(16);
 var _session_state_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(17);
 var _user_agent_options_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(35);







/** @public */
class Inviter extends _session_js__WEBPACK_IMPORTED_MODULE_0__.Session {
    /**
     * @param userAgent
     * @param targetURI
     * @param options
     */
    constructor(userAgent, targetURI, options = {}) {
        super(userAgent, options);
        this.disposed = false;
        this.earlyMedia = false;
        this.earlyMediaSessionDescriptionHandlers = new Map();
        this.isCanceled = false;
        this.inviteWithoutSdp = false;
        this.logger = userAgent.getLogger("sip.Inviter");
        this.earlyMedia = options.earlyMedia !== undefined ? options.earlyMedia : this.earlyMedia;
        this.fromTag = (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_1__.newTag)();
        this.inviteWithoutSdp = options.inviteWithoutSdp !== undefined ? options.inviteWithoutSdp : this.inviteWithoutSdp;
        const inviterOptions = Object.assign({}, options);
        inviterOptions.params = Object.assign({}, options.params);
        const anonymous = options.anonymous || false;
        const contact = userAgent.contact.toString({
            anonymous,
            outbound: anonymous ? !userAgent.contact.tempGruu : !userAgent.contact.pubGruu
        });
        if (anonymous && userAgent.configuration.uri) {
            inviterOptions.params.fromDisplayName = "Anonymous";
            inviterOptions.params.fromUri = "sip:anonymous@anonymous.invalid";
        }
        let fromURI = userAgent.userAgentCore.configuration.aor;
        if (inviterOptions.params.fromUri) {
            fromURI =
                typeof inviterOptions.params.fromUri === "string"
                    ? _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.URIParse(inviterOptions.params.fromUri)
                    : inviterOptions.params.fromUri;
        }
        if (!fromURI) {
            throw new TypeError("Invalid from URI: " + inviterOptions.params.fromUri);
        }
        let toURI = targetURI;
        if (inviterOptions.params.toUri) {
            toURI =
                typeof inviterOptions.params.toUri === "string"
                    ? _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.URIParse(inviterOptions.params.toUri)
                    : inviterOptions.params.toUri;
        }
        if (!toURI) {
            throw new TypeError("Invalid to URI: " + inviterOptions.params.toUri);
        }
        const messageOptions = Object.assign({}, inviterOptions.params);
        messageOptions.fromTag = this.fromTag;
        const extraHeaders = (inviterOptions.extraHeaders || []).slice();
        if (anonymous && userAgent.configuration.uri) {
            extraHeaders.push("P-Preferred-Identity: " + userAgent.configuration.uri.toString());
            extraHeaders.push("Privacy: id");
        }
        extraHeaders.push("Contact: " + contact);
        extraHeaders.push("Allow: " + ["ACK", "CANCEL", "INVITE", "MESSAGE", "BYE", "OPTIONS", "INFO", "NOTIFY", "REFER"].toString());
        if (userAgent.configuration.sipExtension100rel === _user_agent_options_js__WEBPACK_IMPORTED_MODULE_3__.SIPExtension.Required) {
            extraHeaders.push("Require: 100rel");
        }
        if (userAgent.configuration.sipExtensionReplaces === _user_agent_options_js__WEBPACK_IMPORTED_MODULE_3__.SIPExtension.Required) {
            extraHeaders.push("Require: replaces");
        }
        inviterOptions.extraHeaders = extraHeaders;
        const body = undefined;
        this.outgoingRequestMessage = userAgent.userAgentCore.makeOutgoingRequestMessage(_core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.INVITE, targetURI, fromURI, toURI, messageOptions, extraHeaders, body);
        this._contact = contact;
        this._referralInviterOptions = inviterOptions;
        this._renderbody = options.renderbody;
        this._rendertype = options.rendertype;
        if (options.sessionDescriptionHandlerModifiers) {
            this.sessionDescriptionHandlerModifiers = options.sessionDescriptionHandlerModifiers;
        }
        if (options.sessionDescriptionHandlerOptions) {
            this.sessionDescriptionHandlerOptions = options.sessionDescriptionHandlerOptions;
        }
        if (options.sessionDescriptionHandlerModifiersReInvite) {
            this.sessionDescriptionHandlerModifiersReInvite = options.sessionDescriptionHandlerModifiersReInvite;
        }
        if (options.sessionDescriptionHandlerOptionsReInvite) {
            this.sessionDescriptionHandlerOptionsReInvite = options.sessionDescriptionHandlerOptionsReInvite;
        }
        this._id = this.outgoingRequestMessage.callId + this.fromTag;
        this.userAgent._sessions[this._id] = this;
    }
    dispose() {
        if (this.disposed) {
            return Promise.resolve();
        }
        this.disposed = true;
        this.disposeEarlyMedia();
        switch (this.state) {
            case _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Initial:
                return this.cancel().then(() => super.dispose());
            case _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing:
                return this.cancel().then(() => super.dispose());
            case _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Established:
                return super.dispose();
            case _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminating:
                return super.dispose();
            case _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated:
                return super.dispose();
            default:
                throw new Error("Unknown state.");
        }
    }
    get body() {
        return this.outgoingRequestMessage.body;
    }
    get localIdentity() {
        return this.outgoingRequestMessage.from;
    }
    get remoteIdentity() {
        return this.outgoingRequestMessage.to;
    }
    get request() {
        return this.outgoingRequestMessage;
    }
    /**
     * @remarks
     * @param options
     */
    cancel(options = {}) {
        this.logger.log("Inviter.cancel");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Initial && this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing) {
            const error = new Error(`Invalid session state ${this.state}`);
            this.logger.error(error.message);
            return Promise.reject(error);
        }
        this.isCanceled = true;
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminating);
        function getCancelReason(code, reason) {
            if ((code && code < 200) || code > 699) {
                throw new TypeError("Invalid statusCode: " + code);
            }
            else if (code) {
                const cause = code;
                const text = (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_1__.getReasonPhrase)(code) || reason;
                return "SIP;cause=" + cause + ';text="' + text + '"';
            }
        }
        if (this.outgoingInviteRequest) {
            let cancelReason;
            if (options.statusCode && options.reasonPhrase) {
                cancelReason = getCancelReason(options.statusCode, options.reasonPhrase);
            }
            this.outgoingInviteRequest.cancel(cancelReason, options);
        }
        else {
            this.logger.warn("Canceled session before INVITE was sent");
            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
        }
        return Promise.resolve();
    }
    invite(options = {}) {
        this.logger.log("Inviter.invite");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Initial) {
            return super.invite(options);
        }
        if (options.sessionDescriptionHandlerModifiers) {
            this.sessionDescriptionHandlerModifiers = options.sessionDescriptionHandlerModifiers;
        }
        if (options.sessionDescriptionHandlerOptions) {
            this.sessionDescriptionHandlerOptions = options.sessionDescriptionHandlerOptions;
        }
        if (options.withoutSdp || this.inviteWithoutSdp) {
            if (this._renderbody && this._rendertype) {
                this.outgoingRequestMessage.body = { contentType: this._rendertype, body: this._renderbody };
            }
            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing);
            return Promise.resolve(this.sendInvite(options));
        }
        const offerOptions = {
            sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers,
            sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions
        };
        return this.getOffer(offerOptions)
            .then((body) => {
            this.outgoingRequestMessage.body = { body: body.content, contentType: body.contentType };
            this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing);
            return this.sendInvite(options);
        })
            .catch((error) => {
            this.logger.log(error.message);
            if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated) {
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
            }
            throw error;
        });
    }
    sendInvite(options = {}) {
        this.outgoingInviteRequest = this.userAgent.userAgentCore.invite(this.outgoingRequestMessage, {
            onAccept: (inviteResponse) => {
                if (this.dialog) {
                    this.logger.log("Additional confirmed dialog, sending ACK and BYE");
                    this.ackAndBye(inviteResponse);
                    return;
                }
                if (this.isCanceled) {
                    this.logger.log("Canceled session accepted, sending ACK and BYE");
                    this.ackAndBye(inviteResponse);
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                    return;
                }
                this.notifyReferer(inviteResponse);
                this.onAccept(inviteResponse)
                    .then(() => {
                    this.disposeEarlyMedia();
                })
                    .catch(() => {
                    this.disposeEarlyMedia();
                })
                    .then(() => {
                    if (options.requestDelegate && options.requestDelegate.onAccept) {
                        options.requestDelegate.onAccept(inviteResponse);
                    }
                });
            },
            onProgress: (inviteResponse) => {
                if (this.isCanceled) {
                    return;
                }
                this.notifyReferer(inviteResponse);
                this.onProgress(inviteResponse)
                    .catch(() => {
                    this.disposeEarlyMedia();
                })
                    .then(() => {
                    if (options.requestDelegate && options.requestDelegate.onProgress) {
                        options.requestDelegate.onProgress(inviteResponse);
                    }
                });
            },
            onRedirect: (inviteResponse) => {
                this.notifyReferer(inviteResponse);
                this.onRedirect(inviteResponse);
                if (options.requestDelegate && options.requestDelegate.onRedirect) {
                    options.requestDelegate.onRedirect(inviteResponse);
                }
            },
            onReject: (inviteResponse) => {
                this.notifyReferer(inviteResponse);
                this.onReject(inviteResponse);
                if (options.requestDelegate && options.requestDelegate.onReject) {
                    options.requestDelegate.onReject(inviteResponse);
                }
            },
            onTrying: (inviteResponse) => {
                this.notifyReferer(inviteResponse);
                this.onTrying(inviteResponse);
                if (options.requestDelegate && options.requestDelegate.onTrying) {
                    options.requestDelegate.onTrying(inviteResponse);
                }
            }
        });
        return this.outgoingInviteRequest;
    }
    disposeEarlyMedia() {
        this.earlyMediaSessionDescriptionHandlers.forEach((sessionDescriptionHandler) => {
            sessionDescriptionHandler.close();
        });
        this.earlyMediaSessionDescriptionHandlers.clear();
    }
    notifyReferer(response) {
        if (!this._referred) {
            return;
        }
        if (!(this._referred instanceof _session_js__WEBPACK_IMPORTED_MODULE_0__.Session)) {
            throw new Error("Referred session not instance of session");
        }
        if (!this._referred.dialog) {
            return;
        }
        if (!response.message.statusCode) {
            throw new Error("Status code undefined.");
        }
        if (!response.message.reasonPhrase) {
            throw new Error("Reason phrase undefined.");
        }
        const statusCode = response.message.statusCode;
        const reasonPhrase = response.message.reasonPhrase;
        const body = `SIP/2.0 ${statusCode} ${reasonPhrase}`.trim();
        const outgoingNotifyRequest = this._referred.dialog.notify(undefined, {
            extraHeaders: ["Event: refer", "Subscription-State: terminated"],
            body: {
                contentDisposition: "render",
                contentType: "message/sipfrag",
                content: body
            }
        });
        outgoingNotifyRequest.delegate = {
            onReject: () => {
                this._referred = undefined;
            }
        };
    }
    /** @param inviteResponse */
    onAccept(inviteResponse) {
        this.logger.log("Inviter.onAccept");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing) {
            this.logger.error(`Accept received while in state ${this.state}, dropping response`);
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        const response = inviteResponse.message;
        const session = inviteResponse.session;
        if (response.hasHeader("P-Asserted-Identity")) {
            this._assertedIdentity = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.nameAddrHeaderParse(response.getHeader("P-Asserted-Identity"));
        }
        session.delegate = {
            onAck: (ackRequest) => this.onAckRequest(ackRequest),
            onBye: (byeRequest) => this.onByeRequest(byeRequest),
            onInfo: (infoRequest) => this.onInfoRequest(infoRequest),
            onInvite: (inviteRequest) => this.onInviteRequest(inviteRequest),
            onMessage: (messageRequest) => this.onMessageRequest(messageRequest),
            onNotify: (notifyRequest) => this.onNotifyRequest(notifyRequest),
            onPrack: (prackRequest) => this.onPrackRequest(prackRequest),
            onRefer: (referRequest) => this.onReferRequest(referRequest)
        };
        this._dialog = session;
        switch (session.signalingState) {
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Initial:
                this.logger.error("Received 2xx response to INVITE without a session description");
                this.ackAndBye(inviteResponse, 400, "Missing session description");
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                return Promise.reject(new Error("Bad Media Description"));
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.HaveLocalOffer:
                this.logger.error("Received 2xx response to INVITE without a session description");
                this.ackAndBye(inviteResponse, 400, "Missing session description");
                this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                return Promise.reject(new Error("Bad Media Description"));
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.HaveRemoteOffer: {
                if (!this._dialog.offer) {
                    throw new Error(`Session offer undefined in signaling state ${this._dialog.signalingState}.`);
                }
                const options = {
                    sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers,
                    sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions
                };
                return this.setOfferAndGetAnswer(this._dialog.offer, options)
                    .then((body) => {
                    inviteResponse.ack({ body });
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Established);
                })
                    .catch((error) => {
                    this.ackAndBye(inviteResponse, 488, "Invalid session description");
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                    throw error;
                });
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Stable: {
                if (this.earlyMediaSessionDescriptionHandlers.size > 0) {
                    const sdh = this.earlyMediaSessionDescriptionHandlers.get(session.id);
                    if (!sdh) {
                        throw new Error("Session description handler undefined.");
                    }
                    this.setSessionDescriptionHandler(sdh);
                    this.earlyMediaSessionDescriptionHandlers.delete(session.id);
                    inviteResponse.ack();
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Established);
                    return Promise.resolve();
                }
                if (this.earlyMediaDialog) {
                    if (this.earlyMediaDialog !== session) {
                        if (this.earlyMedia) {
                            const message = "You have set the 'earlyMedia' option to 'true' which requires that your INVITE requests " +
                                "do not fork and yet this INVITE request did in fact fork. Consequentially and not surprisingly " +
                                "the end point which accepted the INVITE (confirmed dialog) does not match the end point with " +
                                "which early media has been setup (early dialog) and thus this session is unable to proceed. " +
                                "In accordance with the SIP specifications, the SIP servers your end point is connected to " +
                                "determine if an INVITE forks and the forking behavior of those servers cannot be controlled " +
                                "by this library. If you wish to use early media with this library you must configure those " +
                                "servers accordingly. Alternatively you may set the 'earlyMedia' to 'false' which will allow " +
                                "this library to function with any INVITE requests which do fork.";
                            this.logger.error(message);
                        }
                        const error = new Error("Early media dialog does not equal confirmed dialog, terminating session");
                        this.logger.error(error.message);
                        this.ackAndBye(inviteResponse, 488, "Not Acceptable Here");
                        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                        return Promise.reject(error);
                    }
                    inviteResponse.ack();
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Established);
                    return Promise.resolve();
                }
                const answer = session.answer;
                if (!answer) {
                    throw new Error("Answer is undefined.");
                }
                const options = {
                    sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers,
                    sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions
                };
                return this.setAnswer(answer, options)
                    .then(() => {
                    let ackOptions;
                    if (this._renderbody && this._rendertype) {
                        ackOptions = {
                            body: { contentDisposition: "render", contentType: this._rendertype, content: this._renderbody }
                        };
                    }
                    inviteResponse.ack(ackOptions);
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Established);
                })
                    .catch((error) => {
                    this.logger.error(error.message);
                    this.ackAndBye(inviteResponse, 488, "Not Acceptable Here");
                    this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                    throw error;
                });
            }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Closed:
                return Promise.reject(new Error("Terminated."));
            default:
                throw new Error("Unknown session signaling state.");
        }
    }
    /** @param inviteResponse */
    onProgress(inviteResponse) {
        var _a;
        this.logger.log("Inviter.onProgress");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing) {
            this.logger.error(`Progress received while in state ${this.state}, dropping response`);
            return Promise.reject(new Error(`Invalid session state ${this.state}`));
        }
        if (!this.outgoingInviteRequest) {
            throw new Error("Outgoing INVITE request undefined.");
        }
        const response = inviteResponse.message;
        const session = inviteResponse.session;
        if (response.hasHeader("P-Asserted-Identity")) {
            this._assertedIdentity = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.nameAddrHeaderParse(response.getHeader("P-Asserted-Identity"));
        }
        const requireHeader = response.getHeader("require");
        const rseqHeader = response.getHeader("rseq");
        const rseq = requireHeader && requireHeader.includes("100rel") && rseqHeader ? Number(rseqHeader) : undefined;
        const responseReliable = !!rseq;
        const extraHeaders = [];
        if (responseReliable) {
            extraHeaders.push("RAck: " + response.getHeader("rseq") + " " + response.getHeader("cseq"));
        }
        switch (session.signalingState) {
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Initial:
                if (responseReliable) {
                    this.logger.warn("First reliable provisional response received MUST contain an offer when INVITE does not contain an offer.");
                    inviteResponse.prack({ extraHeaders });
                }
                return Promise.resolve();
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.HaveLocalOffer:
                if (responseReliable) {
                    inviteResponse.prack({ extraHeaders });
                }
                return Promise.resolve();
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.HaveRemoteOffer:
                if (!responseReliable) {
                    this.logger.warn("Non-reliable provisional response MUST NOT contain an initial offer, discarding response.");
                    return Promise.resolve();
                }
                {
                    const sdh = this.sessionDescriptionHandlerFactory(this, this.userAgent.configuration.sessionDescriptionHandlerFactoryOptions || {});
                    if ((_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onSessionDescriptionHandler) {
                        this.delegate.onSessionDescriptionHandler(sdh, true);
                    }
                    this.earlyMediaSessionDescriptionHandlers.set(session.id, sdh);
                    return sdh
                        .setDescription(response.body, this.sessionDescriptionHandlerOptions, this.sessionDescriptionHandlerModifiers)
                        .then(() => sdh.getDescription(this.sessionDescriptionHandlerOptions, this.sessionDescriptionHandlerModifiers))
                        .then((description) => {
                        const body = {
                            contentDisposition: "session",
                            contentType: description.contentType,
                            content: description.body
                        };
                        inviteResponse.prack({ extraHeaders, body });
                    })
                        .catch((error) => {
                        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                        throw error;
                    });
                }
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Stable:
                if (responseReliable) {
                    inviteResponse.prack({ extraHeaders });
                }
                if (this.earlyMedia && !this.earlyMediaDialog) {
                    this.earlyMediaDialog = session;
                    const answer = session.answer;
                    if (!answer) {
                        throw new Error("Answer is undefined.");
                    }
                    const options = {
                        sessionDescriptionHandlerModifiers: this.sessionDescriptionHandlerModifiers,
                        sessionDescriptionHandlerOptions: this.sessionDescriptionHandlerOptions
                    };
                    return this.setAnswer(answer, options).catch((error) => {
                        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
                        throw error;
                    });
                }
                return Promise.resolve();
            case _core_session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Closed:
                return Promise.reject(new Error("Terminated."));
            default:
                throw new Error("Unknown session signaling state.");
        }
    }
    /** @param inviteResponse */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    onRedirect(inviteResponse) {
        this.logger.log("Inviter.onRedirect");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing && this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminating) {
            this.logger.error(`Redirect received while in state ${this.state}, dropping response`);
            return;
        }
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
    }
    /** @param inviteResponse */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    onReject(inviteResponse) {
        this.logger.log("Inviter.onReject");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing && this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminating) {
            this.logger.error(`Reject received while in state ${this.state}, dropping response`);
            return;
        }
        this.stateTransition(_session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Terminated);
    }
    /** @param inviteResponse */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    onTrying(inviteResponse) {
        this.logger.log("Inviter.onTrying");
        if (this.state !== _session_state_js__WEBPACK_IMPORTED_MODULE_5__.SessionState.Establishing) {
            this.logger.error(`Trying received while in state ${this.state}, dropping response`);
            return;
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Messager": () => ( Messager)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(22);
 var _core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);


/** @public */
class Messager {
    /**
     * @param userAgent
     * @param targetURI
     * @param content
     * @param contentType
     * @param options
     */
    constructor(userAgent, targetURI, content, contentType = "text/plain", options = {}) {
        this.logger = userAgent.getLogger("sip.Messager");
        options.params = options.params || {};
        let fromURI = userAgent.userAgentCore.configuration.aor;
        if (options.params.fromUri) {
            fromURI =
                typeof options.params.fromUri === "string" ? _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__.Grammar.URIParse(options.params.fromUri) : options.params.fromUri;
        }
        if (!fromURI) {
            throw new TypeError("Invalid from URI: " + options.params.fromUri);
        }
        let toURI = targetURI;
        if (options.params.toUri) {
            toURI = typeof options.params.toUri === "string" ? _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__.Grammar.URIParse(options.params.toUri) : options.params.toUri;
        }
        if (!toURI) {
            throw new TypeError("Invalid to URI: " + options.params.toUri);
        }
        const params = options.params ? Object.assign({}, options.params) : {};
        const extraHeaders = (options.extraHeaders || []).slice();
        const contentDisposition = "render";
        const body = {
            contentDisposition,
            contentType,
            content
        };
        this.request = userAgent.userAgentCore.makeOutgoingRequestMessage(_core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.MESSAGE, targetURI, fromURI, toURI, params, extraHeaders, body);
        this.userAgent = userAgent;
    }
    message(options = {}) {
        this.userAgent.userAgentCore.request(this.request, options.requestDelegate);
        return Promise.resolve();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "PublisherState": () => ( PublisherState)
 });
/**
 * @remarks
 * @public
 */
var PublisherState;
(function (PublisherState) {
    PublisherState["Initial"] = "Initial";
    PublisherState["Published"] = "Published";
    PublisherState["Unpublished"] = "Unpublished";
    PublisherState["Terminated"] = "Terminated";
})(PublisherState = PublisherState || (PublisherState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Publisher": () => ( Publisher)
 });
 var _core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(18);
 var _core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(30);
 var _emitter_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(13);
 var _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(40);




/** @public */
class Publisher {
    /**
     * @param userAgent
     * @param targetURI
     * @param eventType
     * @param options
     */
    constructor(userAgent, targetURI, eventType, options = {}) {
        this.disposed = false;
        this._state = _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Initial;
        this._stateEventEmitter = new _emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this.userAgent = userAgent;
        options.extraHeaders = (options.extraHeaders || []).slice();
        options.contentType = options.contentType || "text/plain";
        if (typeof options.expires !== "number" || options.expires % 1 !== 0) {
            options.expires = 3600;
        }
        else {
            options.expires = Number(options.expires);
        }
        if (typeof options.unpublishOnClose !== "boolean") {
            options.unpublishOnClose = true;
        }
        this.target = targetURI;
        this.event = eventType;
        this.options = options;
        this.pubRequestExpires = options.expires;
        this.logger = userAgent.getLogger("sip.Publisher");
        const params = options.params || {};
        const fromURI = params.fromUri ? params.fromUri : userAgent.userAgentCore.configuration.aor;
        const toURI = params.toUri ? params.toUri : targetURI;
        let body;
        if (options.body && options.contentType) {
            const contentDisposition = "render";
            const contentType = options.contentType;
            const content = options.body;
            body = {
                contentDisposition,
                contentType,
                content
            };
        }
        const extraHeaders = (options.extraHeaders || []).slice();
        this.request = userAgent.userAgentCore.makeOutgoingRequestMessage(_core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.PUBLISH, targetURI, fromURI, toURI, params, extraHeaders, body);
        this.id = this.target.toString() + ":" + this.event;
        this.userAgent._publishers[this.id] = this;
    }
    dispose() {
        if (this.disposed) {
            return Promise.resolve();
        }
        this.disposed = true;
        this.logger.log(`Publisher ${this.id} in state ${this.state} is being disposed`);
        delete this.userAgent._publishers[this.id];
        if (this.options.unpublishOnClose && this.state === _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Published) {
            return this.unpublish();
        }
        if (this.publishRefreshTimer) {
            clearTimeout(this.publishRefreshTimer);
            this.publishRefreshTimer = undefined;
        }
        this.pubRequestBody = undefined;
        this.pubRequestExpires = 0;
        this.pubRequestEtag = undefined;
        return Promise.resolve();
    }
    get state() {
        return this._state;
    }
    get stateChange() {
        return this._stateEventEmitter;
    }
    /** @param content */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    publish(content, options = {}) {
        if (this.publishRefreshTimer) {
            clearTimeout(this.publishRefreshTimer);
            this.publishRefreshTimer = undefined;
        }
        this.options.body = content;
        this.pubRequestBody = this.options.body;
        if (this.pubRequestExpires === 0) {
            if (this.options.expires === undefined) {
                throw new Error("Expires undefined.");
            }
            this.pubRequestExpires = this.options.expires;
            this.pubRequestEtag = undefined;
        }
        this.sendPublishRequest();
        return Promise.resolve();
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    unpublish(options = {}) {
        if (this.publishRefreshTimer) {
            clearTimeout(this.publishRefreshTimer);
            this.publishRefreshTimer = undefined;
        }
        this.pubRequestBody = undefined;
        this.pubRequestExpires = 0;
        if (this.pubRequestEtag !== undefined) {
            this.sendPublishRequest();
        }
        return Promise.resolve();
    }
    /** @internal */
    receiveResponse(response) {
        const statusCode = response.statusCode || 0;
        switch (true) {
            case /^1[0-9]{2}$/.test(statusCode.toString()):
                break;
            case /^2[0-9]{2}$/.test(statusCode.toString()):
                if (response.hasHeader("SIP-ETag")) {
                    this.pubRequestEtag = response.getHeader("SIP-ETag");
                }
                else {
                    this.logger.warn("SIP-ETag header missing in a 200-class response to PUBLISH");
                }
                if (response.hasHeader("Expires")) {
                    const expires = Number(response.getHeader("Expires"));
                    if (typeof expires === "number" && expires >= 0 && expires <= this.pubRequestExpires) {
                        this.pubRequestExpires = expires;
                    }
                    else {
                        this.logger.warn("Bad Expires header in a 200-class response to PUBLISH");
                    }
                }
                else {
                    this.logger.warn("Expires header missing in a 200-class response to PUBLISH");
                }
                if (this.pubRequestExpires !== 0) {
                    this.publishRefreshTimer = setTimeout(() => this.refreshRequest(), this.pubRequestExpires * 900);
                    if (this._state !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Published) {
                        this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Published);
                    }
                }
                else {
                    this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished);
                }
                break;
            case /^412$/.test(statusCode.toString()):
                if (this.pubRequestEtag !== undefined && this.pubRequestExpires !== 0) {
                    this.logger.warn("412 response to PUBLISH, recovering");
                    this.pubRequestEtag = undefined;
                    if (this.options.body === undefined) {
                        throw new Error("Body undefined.");
                    }
                    this.publish(this.options.body);
                }
                else {
                    this.logger.warn("412 response to PUBLISH, recovery failed");
                    this.pubRequestExpires = 0;
                    this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished);
                    this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated);
                }
                break;
            case /^423$/.test(statusCode.toString()):
                if (this.pubRequestExpires !== 0 && response.hasHeader("Min-Expires")) {
                    const minExpires = Number(response.getHeader("Min-Expires"));
                    if (typeof minExpires === "number" || minExpires > this.pubRequestExpires) {
                        this.logger.warn("423 code in response to PUBLISH, adjusting the Expires value and trying to recover");
                        this.pubRequestExpires = minExpires;
                        if (this.options.body === undefined) {
                            throw new Error("Body undefined.");
                        }
                        this.publish(this.options.body);
                    }
                    else {
                        this.logger.warn("Bad 423 response Min-Expires header received for PUBLISH");
                        this.pubRequestExpires = 0;
                        this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished);
                        this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated);
                    }
                }
                else {
                    this.logger.warn("423 response to PUBLISH, recovery failed");
                    this.pubRequestExpires = 0;
                    this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished);
                    this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated);
                }
                break;
            default:
                this.pubRequestExpires = 0;
                this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished);
                this.stateTransition(_publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated);
                break;
        }
        if (this.pubRequestExpires === 0) {
            if (this.publishRefreshTimer) {
                clearTimeout(this.publishRefreshTimer);
                this.publishRefreshTimer = undefined;
            }
            this.pubRequestBody = undefined;
            this.pubRequestEtag = undefined;
        }
    }
    /** @internal */
    send() {
        return this.userAgent.userAgentCore.publish(this.request, {
            onAccept: (response) => this.receiveResponse(response.message),
            onProgress: (response) => this.receiveResponse(response.message),
            onRedirect: (response) => this.receiveResponse(response.message),
            onReject: (response) => this.receiveResponse(response.message),
            onTrying: (response) => this.receiveResponse(response.message)
        });
    }
    refreshRequest() {
        if (this.publishRefreshTimer) {
            clearTimeout(this.publishRefreshTimer);
            this.publishRefreshTimer = undefined;
        }
        this.pubRequestBody = undefined;
        if (this.pubRequestEtag === undefined) {
            throw new Error("Etag undefined");
        }
        if (this.pubRequestExpires === 0) {
            throw new Error("Expires zero");
        }
        this.sendPublishRequest();
    }
    sendPublishRequest() {
        const reqOptions = Object.assign({}, this.options);
        reqOptions.extraHeaders = (this.options.extraHeaders || []).slice();
        reqOptions.extraHeaders.push("Event: " + this.event);
        reqOptions.extraHeaders.push("Expires: " + this.pubRequestExpires);
        if (this.pubRequestEtag !== undefined) {
            reqOptions.extraHeaders.push("SIP-If-Match: " + this.pubRequestEtag);
        }
        const ruri = this.target;
        const params = this.options.params || {};
        let bodyAndContentType;
        if (this.pubRequestBody !== undefined) {
            if (this.options.contentType === undefined) {
                throw new Error("Content type undefined.");
            }
            bodyAndContentType = {
                body: this.pubRequestBody,
                contentType: this.options.contentType
            };
        }
        let body;
        if (bodyAndContentType) {
            body = (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_3__.fromBodyLegacy)(bodyAndContentType);
        }
        this.request = this.userAgent.userAgentCore.makeOutgoingRequestMessage(_core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.PUBLISH, ruri, params.fromUri ? params.fromUri : this.userAgent.userAgentCore.configuration.aor, params.toUri ? params.toUri : this.target, params, reqOptions.extraHeaders, body);
        return this.send();
    }
    stateTransition(newState) {
        const invalidTransition = () => {
            throw new Error(`Invalid state transition from ${this._state} to ${newState}`);
        };
        switch (this._state) {
            case _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Initial:
                if (newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Published &&
                    newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished &&
                    newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated) {
                    invalidTransition();
                }
                break;
            case _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Published:
                if (newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished && newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated) {
                    invalidTransition();
                }
                break;
            case _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Unpublished:
                if (newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Published && newState !== _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated) {
                    invalidTransition();
                }
                break;
            case _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated:
                invalidTransition();
                break;
            default:
                throw new Error("Unrecognized state.");
        }
        this._state = newState;
        this.logger.log(`Publication transitioned to state ${this._state}`);
        this._stateEventEmitter.emit(this._state);
        if (newState === _publisher_state_js__WEBPACK_IMPORTED_MODULE_0__.PublisherState.Terminated) {
            this.dispose();
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "RegistererState": () => ( RegistererState)
 });
/**
 * @remarks
 * @public
 */
var RegistererState;
(function (RegistererState) {
    RegistererState["Initial"] = "Initial";
    RegistererState["Registered"] = "Registered";
    RegistererState["Unregistered"] = "Unregistered";
    RegistererState["Terminated"] = "Terminated";
})(RegistererState = RegistererState || (RegistererState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Registerer": () => ( Registerer)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(22);
 var _grammar_uri_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(24);
 var _core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(30);
 var _emitter_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(13);
 var _exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(6);
 var _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(42);






/** @public */
class Registerer {
    /**
     * @param userAgent
     * @param options
     */
    constructor(userAgent, options = {}) {
        this.disposed = false;
        this._contacts = [];
        this._retryAfter = undefined;
        this._state = _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Initial;
        this._waiting = false;
        this._stateEventEmitter = new _emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this._waitingEventEmitter = new _emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this.userAgent = userAgent;
        const defaultUserAgentRegistrar = userAgent.configuration.uri.clone();
        defaultUserAgentRegistrar.user = undefined;
        this.options = Object.assign(Object.assign(Object.assign({}, Registerer.defaultOptions()), { registrar: defaultUserAgentRegistrar }), Registerer.stripUndefinedProperties(options));
        this.options.extraContactHeaderParams = (this.options.extraContactHeaderParams || []).slice();
        this.options.extraHeaders = (this.options.extraHeaders || []).slice();
        if (!this.options.registrar) {
            throw new Error("Registrar undefined.");
        }
        this.options.registrar = this.options.registrar.clone();
        if (this.options.regId && !this.options.instanceId) {
            this.options.instanceId = this.userAgent.instanceId;
        }
        else if (!this.options.regId && this.options.instanceId) {
            this.options.regId = 1;
        }
        if (this.options.instanceId && _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.parse(this.options.instanceId, "uuid") === -1) {
            throw new Error("Invalid instanceId.");
        }
        if (this.options.regId && this.options.regId < 0) {
            throw new Error("Invalid regId.");
        }
        const registrar = this.options.registrar;
        const fromURI = (this.options.params && this.options.params.fromUri) || userAgent.userAgentCore.configuration.aor;
        const toURI = (this.options.params && this.options.params.toUri) || userAgent.configuration.uri;
        const params = this.options.params || {};
        const extraHeaders = (options.extraHeaders || []).slice();
        this.request = userAgent.userAgentCore.makeOutgoingRequestMessage(_core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_3__.C.REGISTER, registrar, fromURI, toURI, params, extraHeaders, undefined);
        this.expires = this.options.expires || Registerer.defaultExpires;
        if (this.expires < 0) {
            throw new Error("Invalid expires.");
        }
        this.refreshFrequency = this.options.refreshFrequency || Registerer.defaultRefreshFrequency;
        if (this.refreshFrequency < 50 || this.refreshFrequency > 99) {
            throw new Error("Invalid refresh frequency. The value represents a percentage of the expiration time and should be between 50 and 99.");
        }
        this.logger = userAgent.getLogger("sip.Registerer");
        if (this.options.logConfiguration) {
            this.logger.log("Configuration:");
            Object.keys(this.options).forEach((key) => {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const value = this.options[key];
                switch (key) {
                    case "registrar":
                        this.logger.log("· " + key + ": " + value);
                        break;
                    default:
                        this.logger.log("· " + key + ": " + JSON.stringify(value));
                }
            });
        }
        this.id = this.request.callId + this.request.from.parameters.tag;
        this.userAgent._registerers[this.id] = this;
    }
    static defaultOptions() {
        return {
            expires: Registerer.defaultExpires,
            extraContactHeaderParams: [],
            extraHeaders: [],
            logConfiguration: true,
            instanceId: "",
            params: {},
            regId: 0,
            registrar: new _grammar_uri_js__WEBPACK_IMPORTED_MODULE_4__.URI("sip", "anonymous", "anonymous.invalid"),
            refreshFrequency: Registerer.defaultRefreshFrequency
        };
    }
    /** @param options */
    static stripUndefinedProperties(options) {
        return Object.keys(options).reduce((object, key) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            if (options[key] !== undefined) {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                object[key] = options[key];
            }
            return object;
        }, {});
    }
    get contacts() {
        return this._contacts.slice();
    }
    get retryAfter() {
        return this._retryAfter;
    }
    get state() {
        return this._state;
    }
    get stateChange() {
        return this._stateEventEmitter;
    }
    dispose() {
        if (this.disposed) {
            return Promise.resolve();
        }
        this.disposed = true;
        this.logger.log(`Registerer ${this.id} in state ${this.state} is being disposed`);
        delete this.userAgent._registerers[this.id];
        return new Promise((resolve) => {
            const doClose = () => {
                if (!this.waiting && this._state === _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered) {
                    this.stateChange.addListener(() => {
                        this.terminated();
                        resolve();
                    }, { once: true });
                    this.unregister();
                    return;
                }
                this.terminated();
                resolve();
            };
            if (this.waiting) {
                this.waitingChange.addListener(() => {
                    doClose();
                }, { once: true });
            }
            else {
                doClose();
            }
        });
    }
    register(options = {}) {
        if (this.state === _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
            this.stateError();
            throw new Error("Registerer terminated. Unable to register.");
        }
        if (this.disposed) {
            this.stateError();
            throw new Error("Registerer disposed. Unable to register.");
        }
        if (this.waiting) {
            this.waitingWarning();
            const error = new _exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_5__.RequestPendingError("REGISTER request already in progress, waiting for final response");
            return Promise.reject(error);
        }
        if (options.requestOptions) {
            this.options = Object.assign(Object.assign({}, this.options), options.requestOptions);
        }
        const extraHeaders = (this.options.extraHeaders || []).slice();
        extraHeaders.push("Contact: " + this.generateContactHeader(this.expires));
        extraHeaders.push("Allow: " + ["ACK", "CANCEL", "INVITE", "MESSAGE", "BYE", "OPTIONS", "INFO", "NOTIFY", "REFER"].toString());
        this.request.cseq++;
        this.request.setHeader("cseq", this.request.cseq + " REGISTER");
        this.request.extraHeaders = extraHeaders;
        this.waitingToggle(true);
        const outgoingRegisterRequest = this.userAgent.userAgentCore.register(this.request, {
            onAccept: (response) => {
                let expires;
                if (response.message.hasHeader("expires")) {
                    expires = Number(response.message.getHeader("expires"));
                }
                this._contacts = response.message.getHeaders("contact");
                let contacts = this._contacts.length;
                if (!contacts) {
                    this.logger.error("No Contact header in response to REGISTER, dropping response.");
                    this.unregistered();
                    return;
                }
                let contact;
                while (contacts--) {
                    contact = response.message.parseHeader("contact", contacts);
                    if (!contact) {
                        throw new Error("Contact undefined");
                    }
                    if (this.userAgent.contact.pubGruu && (0,_grammar_uri_js__WEBPACK_IMPORTED_MODULE_4__.equivalentURI)(contact.uri, this.userAgent.contact.pubGruu)) {
                        expires = Number(contact.getParam("expires"));
                        break;
                    }
                    if (this.userAgent.configuration.contactName === "") {
                        if (contact.uri.user === this.userAgent.contact.uri.user) {
                            expires = Number(contact.getParam("expires"));
                            break;
                        }
                    }
                    else {
                        if ((0,_grammar_uri_js__WEBPACK_IMPORTED_MODULE_4__.equivalentURI)(contact.uri, this.userAgent.contact.uri)) {
                            expires = Number(contact.getParam("expires"));
                            break;
                        }
                    }
                    contact = undefined;
                }
                if (contact === undefined) {
                    this.logger.error("No Contact header pointing to us, dropping response");
                    this.unregistered();
                    this.waitingToggle(false);
                    return;
                }
                if (expires === undefined) {
                    this.logger.error("Contact pointing to us is missing expires parameter, dropping response");
                    this.unregistered();
                    this.waitingToggle(false);
                    return;
                }
                if (contact.hasParam("temp-gruu")) {
                    const gruu = contact.getParam("temp-gruu");
                    if (gruu) {
                        this.userAgent.contact.tempGruu = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.URIParse(gruu.replace(/"/g, ""));
                    }
                }
                if (contact.hasParam("pub-gruu")) {
                    const gruu = contact.getParam("pub-gruu");
                    if (gruu) {
                        this.userAgent.contact.pubGruu = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.URIParse(gruu.replace(/"/g, ""));
                    }
                }
                this.registered(expires);
                if (options.requestDelegate && options.requestDelegate.onAccept) {
                    options.requestDelegate.onAccept(response);
                }
                this.waitingToggle(false);
            },
            onProgress: (response) => {
                if (options.requestDelegate && options.requestDelegate.onProgress) {
                    options.requestDelegate.onProgress(response);
                }
            },
            onRedirect: (response) => {
                this.logger.error("Redirect received. Not supported.");
                this.unregistered();
                if (options.requestDelegate && options.requestDelegate.onRedirect) {
                    options.requestDelegate.onRedirect(response);
                }
                this.waitingToggle(false);
            },
            onReject: (response) => {
                if (response.message.statusCode === 423) {
                    if (!response.message.hasHeader("min-expires")) {
                        this.logger.error("423 response received for REGISTER without Min-Expires, dropping response");
                        this.unregistered();
                        this.waitingToggle(false);
                        return;
                    }
                    this.expires = Number(response.message.getHeader("min-expires"));
                    this.waitingToggle(false);
                    this.register();
                    return;
                }
                this.logger.warn(`Failed to register, status code ${response.message.statusCode}`);
                let retryAfterDuration = NaN;
                if (response.message.statusCode === 500 || response.message.statusCode === 503) {
                    const header = response.message.getHeader("retry-after");
                    if (header) {
                        retryAfterDuration = Number.parseInt(header, undefined);
                    }
                }
                this._retryAfter = isNaN(retryAfterDuration) ? undefined : retryAfterDuration;
                this.unregistered();
                if (options.requestDelegate && options.requestDelegate.onReject) {
                    options.requestDelegate.onReject(response);
                }
                this._retryAfter = undefined;
                this.waitingToggle(false);
            },
            onTrying: (response) => {
                if (options.requestDelegate && options.requestDelegate.onTrying) {
                    options.requestDelegate.onTrying(response);
                }
            }
        });
        return Promise.resolve(outgoingRegisterRequest);
    }
    unregister(options = {}) {
        if (this.state === _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
            this.stateError();
            throw new Error("Registerer terminated. Unable to register.");
        }
        if (this.disposed) {
            if (this.state !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered) {
                this.stateError();
                throw new Error("Registerer disposed. Unable to register.");
            }
        }
        if (this.waiting) {
            this.waitingWarning();
            const error = new _exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_5__.RequestPendingError("REGISTER request already in progress, waiting for final response");
            return Promise.reject(error);
        }
        if (this._state !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered && !options.all) {
            this.logger.warn("Not currently registered, but sending an unregister anyway.");
        }
        const extraHeaders = ((options.requestOptions && options.requestOptions.extraHeaders) || []).slice();
        this.request.extraHeaders = extraHeaders;
        if (options.all) {
            extraHeaders.push("Contact: *");
            extraHeaders.push("Expires: 0");
        }
        else {
            extraHeaders.push("Contact: " + this.generateContactHeader(0));
        }
        this.request.cseq++;
        this.request.setHeader("cseq", this.request.cseq + " REGISTER");
        if (this.registrationTimer !== undefined) {
            clearTimeout(this.registrationTimer);
            this.registrationTimer = undefined;
        }
        this.waitingToggle(true);
        const outgoingRegisterRequest = this.userAgent.userAgentCore.register(this.request, {
            onAccept: (response) => {
                this._contacts = response.message.getHeaders("contact");
                this.unregistered();
                if (options.requestDelegate && options.requestDelegate.onAccept) {
                    options.requestDelegate.onAccept(response);
                }
                this.waitingToggle(false);
            },
            onProgress: (response) => {
                if (options.requestDelegate && options.requestDelegate.onProgress) {
                    options.requestDelegate.onProgress(response);
                }
            },
            onRedirect: (response) => {
                this.logger.error("Unregister redirected. Not currently supported.");
                this.unregistered();
                if (options.requestDelegate && options.requestDelegate.onRedirect) {
                    options.requestDelegate.onRedirect(response);
                }
                this.waitingToggle(false);
            },
            onReject: (response) => {
                this.logger.error(`Unregister rejected with status code ${response.message.statusCode}`);
                this.unregistered();
                if (options.requestDelegate && options.requestDelegate.onReject) {
                    options.requestDelegate.onReject(response);
                }
                this.waitingToggle(false);
            },
            onTrying: (response) => {
                if (options.requestDelegate && options.requestDelegate.onTrying) {
                    options.requestDelegate.onTrying(response);
                }
            }
        });
        return Promise.resolve(outgoingRegisterRequest);
    }
    clearTimers() {
        if (this.registrationTimer !== undefined) {
            clearTimeout(this.registrationTimer);
            this.registrationTimer = undefined;
        }
        if (this.registrationExpiredTimer !== undefined) {
            clearTimeout(this.registrationExpiredTimer);
            this.registrationExpiredTimer = undefined;
        }
    }
    generateContactHeader(expires) {
        let contact = this.userAgent.contact.toString({ register: true });
        if (this.options.regId && this.options.instanceId) {
            contact += ";reg-id=" + this.options.regId;
            contact += ';+sip.instance="<urn:uuid:' + this.options.instanceId + '>"';
        }
        if (this.options.extraContactHeaderParams) {
            this.options.extraContactHeaderParams.forEach((header) => {
                contact += ";" + header;
            });
        }
        contact += ";expires=" + expires;
        return contact;
    }
    registered(expires) {
        this.clearTimers();
        this.registrationTimer = setTimeout(() => {
            this.registrationTimer = undefined;
            this.register();
        }, (this.refreshFrequency / 100) * expires * 1000);
        this.registrationExpiredTimer = setTimeout(() => {
            this.logger.warn("Registration expired");
            this.unregistered();
        }, expires * 1000);
        if (this._state !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered) {
            this.stateTransition(_registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered);
        }
    }
    unregistered() {
        this.clearTimers();
        if (this._state !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Unregistered) {
            this.stateTransition(_registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Unregistered);
        }
    }
    terminated() {
        this.clearTimers();
        if (this._state !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
            this.stateTransition(_registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated);
        }
    }
    stateTransition(newState) {
        const invalidTransition = () => {
            throw new Error(`Invalid state transition from ${this._state} to ${newState}`);
        };
        switch (this._state) {
            case _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Initial:
                if (newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered &&
                    newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Unregistered &&
                    newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
                    invalidTransition();
                }
                break;
            case _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered:
                if (newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Unregistered && newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
                    invalidTransition();
                }
                break;
            case _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Unregistered:
                if (newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Registered && newState !== _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
                    invalidTransition();
                }
                break;
            case _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated:
                invalidTransition();
                break;
            default:
                throw new Error("Unrecognized state.");
        }
        this._state = newState;
        this.logger.log(`Registration transitioned to state ${this._state}`);
        this._stateEventEmitter.emit(this._state);
        if (newState === _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated) {
            this.dispose();
        }
    }
    get waiting() {
        return this._waiting;
    }
    get waitingChange() {
        return this._waitingEventEmitter;
    }
    waitingToggle(waiting) {
        if (this._waiting === waiting) {
            throw new Error(`Invalid waiting transition from ${this._waiting} to ${waiting}`);
        }
        this._waiting = waiting;
        this.logger.log(`Waiting toggled to ${this._waiting}`);
        this._waitingEventEmitter.emit(this._waiting);
    }
    waitingWarning() {
        let message = "An attempt was made to send a REGISTER request while a prior one was still in progress.";
        message += " RFC 3261 requires UAs MUST NOT send a new registration until they have received a final response";
        message += " from the registrar for the previous one or the previous REGISTER request has timed out.";
        message += " Note that if the transport disconnects, you still must wait for the prior request to time out before";
        message +=
            " sending a new REGISTER request or alternatively dispose of the current Registerer and create a new Registerer.";
        this.logger.warn(message);
    }
    stateError() {
        const reason = this.state === _registerer_state_js__WEBPACK_IMPORTED_MODULE_0__.RegistererState.Terminated ? "is in 'Terminated' state" : "has been disposed";
        let message = `An attempt was made to send a REGISTER request when the Registerer ${reason}.`;
        message += " The Registerer transitions to 'Terminated' when Registerer.dispose() is called.";
        message += " Perhaps you called UserAgent.stop() which dipsoses of all Registerers?";
        this.logger.error(message);
    }
}
Registerer.defaultExpires = 600;
Registerer.defaultRefreshFrequency = 99;


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Subscriber": () => ( Subscriber)
 });
 var _core_messages_body_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(18);
 var _core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(30);
 var _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(47);
 var _core_user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(29);
 var _notification_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(33);
 var _subscription_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(45);
 var _subscription_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(46);







/**
 * @remarks
 * @public
 */
class Subscriber extends _subscription_js__WEBPACK_IMPORTED_MODULE_0__.Subscription {
    /**
     * @param userAgent
     * @param targetURI
     * @param eventType
     * @param options
     */
    constructor(userAgent, targetURI, eventType, options = {}) {
        super(userAgent, options);
        this.body = undefined;
        this.logger = userAgent.getLogger("sip.Subscriber");
        if (options.body) {
            this.body = {
                body: options.body,
                contentType: options.contentType ? options.contentType : "application/sdp"
            };
        }
        this.targetURI = targetURI;
        this.event = eventType;
        if (options.expires === undefined) {
            this.expires = 3600;
        }
        else if (typeof options.expires !== "number") {
            this.logger.warn(`Option "expires" must be a number. Using default of 3600.`);
            this.expires = 3600;
        }
        else {
            this.expires = options.expires;
        }
        this.extraHeaders = (options.extraHeaders || []).slice();
        this.subscriberRequest = this.initSubscriberRequest();
        this.outgoingRequestMessage = this.subscriberRequest.message;
        this.id = this.outgoingRequestMessage.callId + this.outgoingRequestMessage.from.parameters.tag + this.event;
        this._userAgent._subscriptions[this.id] = this;
    }
    /** @internal */
    dispose() {
        if (this.disposed) {
            return Promise.resolve();
        }
        this.logger.log(`Subscription ${this.id} in state ${this.state} is being disposed`);
        delete this._userAgent._subscriptions[this.id];
        if (this.retryAfterTimer) {
            clearTimeout(this.retryAfterTimer);
            this.retryAfterTimer = undefined;
        }
        this.subscriberRequest.dispose();
        return super.dispose().then(() => {
            if (this.state !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Subscribed) {
                return;
            }
            if (!this._dialog) {
                throw new Error("Dialog undefined.");
            }
            if (this._dialog.subscriptionState === _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Pending ||
                this._dialog.subscriptionState === _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Active) {
                const dialog = this._dialog;
                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                return new Promise((resolve, reject) => {
                    dialog.delegate = {
                        onTerminated: () => resolve()
                    };
                    dialog.unsubscribe();
                });
            }
        });
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    subscribe(options = {}) {
        switch (this.subscriberRequest.state) {
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Initial:
                if (this.state === _subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Initial) {
                    this.stateTransition(_subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.NotifyWait);
                }
                this.subscriberRequest.subscribe().then((result) => {
                    if (result.success) {
                        if (result.success.subscription) {
                            this._dialog = result.success.subscription;
                            this._dialog.delegate = {
                                onNotify: (request) => this.onNotify(request),
                                onRefresh: (request) => this.onRefresh(request),
                                onTerminated: () => {
                                    if (this.state !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Terminated) {
                                        this.stateTransition(_subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Terminated);
                                    }
                                }
                            };
                        }
                        this.onNotify(result.success.request);
                    }
                    else if (result.failure) {
                        this.unsubscribe();
                    }
                });
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.NotifyWait:
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Pending:
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Active:
                if (this._dialog) {
                    const request = this._dialog.refresh();
                    request.delegate = {
                        onAccept: (response) => this.onAccepted(response),
                        // eslint-disable-next-line @typescript-eslint/no-unused-vars
                        onRedirect: (response) => this.unsubscribe(),
                        // eslint-disable-next-line @typescript-eslint/no-unused-vars
                        onReject: (response) => this.unsubscribe()
                    };
                }
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Terminated:
                break;
            default:
                break;
        }
        return Promise.resolve();
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    unsubscribe(options = {}) {
        if (this.disposed) {
            return Promise.resolve();
        }
        switch (this.subscriberRequest.state) {
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Initial:
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.NotifyWait:
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Pending:
                if (this._dialog) {
                    this._dialog.unsubscribe();
                }
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Active:
                if (this._dialog) {
                    this._dialog.unsubscribe();
                }
                break;
            case _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Terminated:
                break;
            default:
                throw new Error("Unknown state.");
        }
        this.stateTransition(_subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Terminated);
        return Promise.resolve();
    }
    /**
     * @deprecated
     * @internal
     */
    _refresh() {
        if (this.subscriberRequest.state === _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Active) {
            return this.subscribe();
        }
        return Promise.resolve();
    }
    /** @internal */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    onAccepted(response) {
    }
    /** @internal */
    onNotify(request) {
        if (this.disposed) {
            request.accept();
            return;
        }
        if (this.state !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Subscribed) {
            this.stateTransition(_subscription_state_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState.Subscribed);
        }
        if (this.delegate && this.delegate.onNotify) {
            const notification = new _notification_js__WEBPACK_IMPORTED_MODULE_3__.Notification(request);
            this.delegate.onNotify(notification);
        }
        else {
            request.accept();
        }
        const subscriptionState = request.message.parseHeader("Subscription-State");
        if (subscriptionState && subscriptionState.state) {
            switch (subscriptionState.state) {
                case "terminated":
                    if (subscriptionState.reason) {
                        this.logger.log(`Terminated subscription with reason ${subscriptionState.reason}`);
                        switch (subscriptionState.reason) {
                            case "deactivated":
                            case "timeout":
                                this.initSubscriberRequest();
                                this.subscribe();
                                return;
                            case "probation":
                            case "giveup":
                                this.initSubscriberRequest();
                                if (subscriptionState.params && subscriptionState.params["retry-after"]) {
                                    this.retryAfterTimer = setTimeout(() => {
                                        this.subscribe();
                                    }, subscriptionState.params["retry-after"]);
                                }
                                else {
                                    this.subscribe();
                                }
                                return;
                            case "rejected":
                            case "noresource":
                            case "invariant":
                                break;
                        }
                    }
                    this.unsubscribe();
                    break;
                default:
                    break;
            }
        }
    }
    /** @internal */
    onRefresh(request) {
        request.delegate = {
            onAccept: (response) => this.onAccepted(response)
        };
    }
    initSubscriberRequest() {
        const options = {
            extraHeaders: this.extraHeaders,
            body: this.body ? (0,_core_messages_body_js__WEBPACK_IMPORTED_MODULE_4__.fromBodyLegacy)(this.body) : undefined
        };
        // eslint-disable-next-line @typescript-eslint/no-use-before-define
        this.subscriberRequest = new SubscriberRequest(this._userAgent.userAgentCore, this.targetURI, this.event, this.expires, options);
        this.subscriberRequest.delegate = {
            onAccept: (response) => this.onAccepted(response)
        };
        return this.subscriberRequest;
    }
}
class SubscriberRequest {
    constructor(core, target, event, expires, options, delegate) {
        this.core = core;
        this.target = target;
        this.event = event;
        this.expires = expires;
        this.subscribed = false;
        this.logger = core.loggerFactory.getLogger("sip.Subscriber");
        this.delegate = delegate;
        const allowHeader = "Allow: " + _core_user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_5__.AllowedMethods.toString();
        const extraHeaders = ((options && options.extraHeaders) || []).slice();
        extraHeaders.push(allowHeader);
        extraHeaders.push("Event: " + this.event);
        extraHeaders.push("Expires: " + this.expires);
        extraHeaders.push("Contact: " + this.core.configuration.contact.toString());
        const body = options && options.body;
        this.message = core.makeOutgoingRequestMessage(_core_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_6__.C.SUBSCRIBE, this.target, this.core.configuration.aor, this.target, {}, extraHeaders, body);
    }
    dispose() {
        if (this.request) {
            this.request.waitNotifyStop();
            this.request.dispose();
            this.request = undefined;
        }
    }
    get state() {
        if (this.subscription) {
            return this.subscription.subscriptionState;
        }
        else if (this.subscribed) {
            return _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.NotifyWait;
        }
        else {
            return _core_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Initial;
        }
    }
    /** @param options */
    subscribe() {
        if (this.subscribed) {
            return Promise.reject(new Error("Not in initial state. Did you call subscribe more than once?"));
        }
        this.subscribed = true;
        return new Promise((resolve) => {
            if (!this.message) {
                throw new Error("Message undefined.");
            }
            this.request = this.core.subscribe(this.message, {
                onAccept: (response) => {
                    if (this.delegate && this.delegate.onAccept) {
                        this.delegate.onAccept(response);
                    }
                },
                onNotify: (requestWithSubscription) => {
                    this.subscription = requestWithSubscription.subscription;
                    if (this.subscription) {
                        this.subscription.autoRefresh = true;
                    }
                    resolve({ success: requestWithSubscription });
                },
                onNotifyTimeout: () => {
                    resolve({ failure: {} });
                },
                onRedirect: (response) => {
                    resolve({ failure: { response } });
                },
                onReject: (response) => {
                    resolve({ failure: { response } });
                }
            });
        });
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Subscription": () => ( Subscription)
 });
 var _emitter_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(13);
 var _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(46);


/**
 * @remarks
 * @public
 */
class Subscription {
    /**
     * @param userAgent
     * @internal
     */
    constructor(userAgent, options = {}) {
        this._disposed = false;
        this._state = _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Initial;
        this._logger = userAgent.getLogger("sip.Subscription");
        this._stateEventEmitter = new _emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this._userAgent = userAgent;
        this.delegate = options.delegate;
    }
    dispose() {
        if (this._disposed) {
            return Promise.resolve();
        }
        this._disposed = true;
        this._stateEventEmitter.removeAllListeners();
        return Promise.resolve();
    }
    get dialog() {
        return this._dialog;
    }
    /** @internal */
    get disposed() {
        return this._disposed;
    }
    get state() {
        return this._state;
    }
    get stateChange() {
        return this._stateEventEmitter;
    }
    /** @internal */
    stateTransition(newState) {
        const invalidTransition = () => {
            throw new Error(`Invalid state transition from ${this._state} to ${newState}`);
        };
        switch (this._state) {
            case _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Initial:
                if (newState !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.NotifyWait && newState !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.NotifyWait:
                if (newState !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Subscribed && newState !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Subscribed:
                if (newState !== _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Terminated) {
                    invalidTransition();
                }
                break;
            case _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Terminated:
                invalidTransition();
                break;
            default:
                throw new Error("Unrecognized state.");
        }
        if (this._state === newState) {
            return;
        }
        this._state = newState;
        this._logger.log(`Subscription ${this._dialog ? this._dialog.id : undefined} transitioned to ${this._state}`);
        this._stateEventEmitter.emit(this._state);
        if (newState === _subscription_state_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState.Terminated) {
            this.dispose();
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SubscriptionState": () => ( SubscriptionState)
 });
/**
 * @remarks
 * @public
 */
var SubscriptionState;
(function (SubscriptionState) {
    SubscriptionState["Initial"] = "Initial";
    SubscriptionState["NotifyWait"] = "NotifyWait";
    SubscriptionState["Subscribed"] = "Subscribed";
    SubscriptionState["Terminated"] = "Terminated";
})(SubscriptionState = SubscriptionState || (SubscriptionState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SubscriptionState": () => ( SubscriptionState)
 });
/**
 * @remarks
 * @public
 */
var SubscriptionState;
(function (SubscriptionState) {
    SubscriptionState["Initial"] = "Initial";
    SubscriptionState["NotifyWait"] = "NotifyWait";
    SubscriptionState["Pending"] = "Pending";
    SubscriptionState["Active"] = "Active";
    SubscriptionState["Terminated"] = "Terminated";
})(SubscriptionState = SubscriptionState || (SubscriptionState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "TransportState": () => ( TransportState)
 });
/**
 * @remarks
 * @public
 */
var TransportState;
(function (TransportState) {
    TransportState["Connecting"] = "Connecting";
    TransportState["Connected"] = "Connected";
    TransportState["Disconnecting"] = "Disconnecting";
    TransportState["Disconnected"] = "Disconnected";
})(TransportState = TransportState || (TransportState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "UserAgentState": () => ( UserAgentState)
 });
/**
 * @remarks
 * @public
 */
var UserAgentState;
(function (UserAgentState) {
    UserAgentState["Started"] = "Started";
    UserAgentState["Stopped"] = "Stopped";
})(UserAgentState = UserAgentState || (UserAgentState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "UserAgent": () => ( UserAgent)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(22);
 var _grammar_uri_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(24);
 var _core_messages_digest_authentication_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(59);
 var _core_messages_incoming_request_message_js__WEBPACK_IMPORTED_MODULE_18__ = __webpack_require__(19);
 var _core_messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_19__ = __webpack_require__(27);
 var _core_log_levels_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(52);
 var _core_log_logger_factory_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(51);
 var _core_messages_parser_js__WEBPACK_IMPORTED_MODULE_17__ = __webpack_require__(99);
 var _core_user_agent_core_user_agent_core_js__WEBPACK_IMPORTED_MODULE_16__ = __webpack_require__(61);
 var _core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(21);
 var _platform_web_session_description_handler_session_description_handler_factory_default_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(54);
 var _platform_web_transport_transport_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(58);
 var _version_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(1);
 var _emitter_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(13);
 var _invitation_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(15);
 var _inviter_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(38);
 var _message_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(32);
 var _notification_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(33);
 var _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(35);
 var _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(49);




















/**
 * @remarks
 * @public
 */
class UserAgent {
    /** @param options */
    constructor(options = {}) {
        /** @internal */
        this._publishers = {};
        /** @internal */
        this._registerers = {};
        /** @internal */
        this._sessions = {};
        /** @internal */
        this._subscriptions = {};
        this._state = _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped;
        this._stateEventEmitter = new _emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this.delegate = options.delegate;
        this.options = Object.assign(Object.assign(Object.assign(Object.assign(Object.assign({}, UserAgent.defaultOptions()), { sipjsId: (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__.createRandomToken)(5) }), { uri: new _grammar_uri_js__WEBPACK_IMPORTED_MODULE_3__.URI("sip", "anonymous." + (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__.createRandomToken)(6), "anonymous.invalid") }), { viaHost: (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__.createRandomToken)(12) + ".invalid" }), UserAgent.stripUndefinedProperties(options));
        if (this.options.hackIpInContact) {
            if (typeof this.options.hackIpInContact === "boolean" && this.options.hackIpInContact) {
                const from = 1;
                const to = 254;
                const octet = Math.floor(Math.random() * (to - from + 1) + from);
                this.options.viaHost = "192.0.2." + octet;
            }
            else if (this.options.hackIpInContact) {
                this.options.viaHost = this.options.hackIpInContact;
            }
        }
        this.loggerFactory = new _core_log_logger_factory_js__WEBPACK_IMPORTED_MODULE_4__.LoggerFactory();
        this.logger = this.loggerFactory.getLogger("sip.UserAgent");
        this.loggerFactory.builtinEnabled = this.options.logBuiltinEnabled;
        this.loggerFactory.connector = this.options.logConnector;
        switch (this.options.logLevel) {
            case "error":
                this.loggerFactory.level = _core_log_levels_js__WEBPACK_IMPORTED_MODULE_5__.Levels.error;
                break;
            case "warn":
                this.loggerFactory.level = _core_log_levels_js__WEBPACK_IMPORTED_MODULE_5__.Levels.warn;
                break;
            case "log":
                this.loggerFactory.level = _core_log_levels_js__WEBPACK_IMPORTED_MODULE_5__.Levels.log;
                break;
            case "debug":
                this.loggerFactory.level = _core_log_levels_js__WEBPACK_IMPORTED_MODULE_5__.Levels.debug;
                break;
            default:
                break;
        }
        if (this.options.logConfiguration) {
            this.logger.log("Configuration:");
            Object.keys(this.options).forEach((key) => {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const value = this.options[key];
                switch (key) {
                    case "uri":
                    case "sessionDescriptionHandlerFactory":
                        this.logger.log("· " + key + ": " + value);
                        break;
                    case "authorizationPassword":
                        this.logger.log("· " + key + ": " + "NOT SHOWN");
                        break;
                    case "transportConstructor":
                        this.logger.log("· " + key + ": " + value.name);
                        break;
                    default:
                        this.logger.log("· " + key + ": " + JSON.stringify(value));
                }
            });
        }
        if (this.options.transportOptions) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const optionsDeprecated = this.options.transportOptions;
            const maxReconnectionAttemptsDeprecated = optionsDeprecated.maxReconnectionAttempts;
            const reconnectionTimeoutDeprecated = optionsDeprecated.reconnectionTimeout;
            if (maxReconnectionAttemptsDeprecated !== undefined) {
                const deprecatedMessage = `The transport option "maxReconnectionAttempts" as has apparently been specified and has been deprecated. ` +
                    "It will no longer be available starting with SIP.js release 0.16.0. Please update accordingly.";
                this.logger.warn(deprecatedMessage);
            }
            if (reconnectionTimeoutDeprecated !== undefined) {
                const deprecatedMessage = `The transport option "reconnectionTimeout" as has apparently been specified and has been deprecated. ` +
                    "It will no longer be available starting with SIP.js release 0.16.0. Please update accordingly.";
                this.logger.warn(deprecatedMessage);
            }
            if (options.reconnectionDelay === undefined && reconnectionTimeoutDeprecated !== undefined) {
                this.options.reconnectionDelay = reconnectionTimeoutDeprecated;
            }
            if (options.reconnectionAttempts === undefined && maxReconnectionAttemptsDeprecated !== undefined) {
                this.options.reconnectionAttempts = maxReconnectionAttemptsDeprecated;
            }
        }
        if (options.reconnectionDelay !== undefined) {
            const deprecatedMessage = `The user agent option "reconnectionDelay" as has apparently been specified and has been deprecated. ` +
                "It will no longer be available starting with SIP.js release 0.16.0. Please update accordingly.";
            this.logger.warn(deprecatedMessage);
        }
        if (options.reconnectionAttempts !== undefined) {
            const deprecatedMessage = `The user agent option "reconnectionAttempts" as has apparently been specified and has been deprecated. ` +
                "It will no longer be available starting with SIP.js release 0.16.0. Please update accordingly.";
            this.logger.warn(deprecatedMessage);
        }
        this._transport = new this.options.transportConstructor(this.getLogger("sip.Transport"), this.options.transportOptions);
        this.initTransportCallbacks();
        this._contact = this.initContact();
        this._instanceId = this.options.instanceId ? this.options.instanceId : UserAgent.newUUID();
        if (_grammar_grammar_js__WEBPACK_IMPORTED_MODULE_6__.Grammar.parse(this._instanceId, "uuid") === -1) {
            throw new Error("Invalid instanceId.");
        }
        this._userAgentCore = this.initCore();
    }
    /**
     * @param uri
     * @remarks
     */
    static makeURI(uri) {
        return _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_6__.Grammar.URIParse(uri);
    }
    static defaultOptions() {
        return {
            allowLegacyNotifications: false,
            authorizationHa1: "",
            authorizationPassword: "",
            authorizationUsername: "",
            delegate: {},
            contactName: "",
            contactParams: { transport: "ws" },
            displayName: "",
            forceRport: false,
            gracefulShutdown: true,
            hackAllowUnregisteredOptionTags: false,
            hackIpInContact: false,
            hackViaTcp: false,
            instanceId: "",
            instanceIdAlwaysAdded: false,
            logBuiltinEnabled: true,
            logConfiguration: true,
            logConnector: () => {
            },
            logLevel: "log",
            noAnswerTimeout: 60,
            preloadedRouteSet: [],
            reconnectionAttempts: 0,
            reconnectionDelay: 4,
            sendInitialProvisionalResponse: true,
            sessionDescriptionHandlerFactory: (0,_platform_web_session_description_handler_session_description_handler_factory_default_js__WEBPACK_IMPORTED_MODULE_7__.defaultSessionDescriptionHandlerFactory)(),
            sessionDescriptionHandlerFactoryOptions: {},
            sipExtension100rel: _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__.SIPExtension.Unsupported,
            sipExtensionReplaces: _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__.SIPExtension.Unsupported,
            sipExtensionExtraSupported: [],
            sipjsId: "",
            transportConstructor: _platform_web_transport_transport_js__WEBPACK_IMPORTED_MODULE_9__.Transport,
            transportOptions: {},
            uri: new _grammar_uri_js__WEBPACK_IMPORTED_MODULE_3__.URI("sip", "anonymous", "anonymous.invalid"),
            userAgentString: "SIP.js/" + _version_js__WEBPACK_IMPORTED_MODULE_10__.LIBRARY_VERSION,
            viaHost: ""
        };
    }
    static newUUID() {
        const UUID = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
            const r = Math.floor(Math.random() * 16);
            const v = c === "x" ? r : (r % 4) + 8;
            return v.toString(16);
        });
        return UUID;
    }
    /** @param options */
    static stripUndefinedProperties(options) {
        return Object.keys(options).reduce((object, key) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            if (options[key] !== undefined) {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                object[key] = options[key];
            }
            return object;
        }, {});
    }
    get configuration() {
        return this.options;
    }
    get contact() {
        return this._contact;
    }
    get instanceId() {
        return this._instanceId;
    }
    get state() {
        return this._state;
    }
    get stateChange() {
        return this._stateEventEmitter;
    }
    get transport() {
        return this._transport;
    }
    get userAgentCore() {
        return this._userAgentCore;
    }
    getLogger(category, label) {
        return this.loggerFactory.getLogger(category, label);
    }
    getLoggerFactory() {
        return this.loggerFactory;
    }
    isConnected() {
        return this.transport.isConnected();
    }
    reconnect() {
        if (this.state === _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped) {
            return Promise.reject(new Error("User agent stopped."));
        }
        return Promise.resolve().then(() => this.transport.connect());
    }
    start() {
        if (this.state === _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Started) {
            this.logger.warn(`User agent already started`);
            return Promise.resolve();
        }
        this.logger.log(`Starting ${this.configuration.uri}`);
        this.transitionState(_user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Started);
        return this.transport.connect();
    }
    async stop() {
        if (this.state === _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped) {
            this.logger.warn(`User agent already stopped`);
            return Promise.resolve();
        }
        this.logger.log(`Stopping ${this.configuration.uri}`);
        if (!this.options.gracefulShutdown) {
            this.logger.log(`Dispose of transport`);
            this.transport.dispose().catch((error) => {
                this.logger.error(error.message);
                throw error;
            });
            this.logger.log(`Dispose of core`);
            this.userAgentCore.dispose();
            this._publishers = {};
            this._registerers = {};
            this._sessions = {};
            this._subscriptions = {};
            this.transitionState(_user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped);
            return Promise.resolve();
        }
        const publishers = Object.assign({}, this._publishers);
        const registerers = Object.assign({}, this._registerers);
        const sessions = Object.assign({}, this._sessions);
        const subscriptions = Object.assign({}, this._subscriptions);
        const transport = this.transport;
        const userAgentCore = this.userAgentCore;
        this.logger.log(`Dispose of registerers`);
        for (const id in registerers) {
            if (registerers[id]) {
                await registerers[id].dispose().catch((error) => {
                    this.logger.error(error.message);
                    delete this._registerers[id];
                    throw error;
                });
            }
        }
        this.logger.log(`Dispose of sessions`);
        for (const id in sessions) {
            if (sessions[id]) {
                await sessions[id].dispose().catch((error) => {
                    this.logger.error(error.message);
                    delete this._sessions[id];
                    throw error;
                });
            }
        }
        this.logger.log(`Dispose of subscriptions`);
        for (const id in subscriptions) {
            if (subscriptions[id]) {
                await subscriptions[id].dispose().catch((error) => {
                    this.logger.error(error.message);
                    delete this._subscriptions[id];
                    throw error;
                });
            }
        }
        this.logger.log(`Dispose of publishers`);
        for (const id in publishers) {
            if (publishers[id]) {
                await publishers[id].dispose().catch((error) => {
                    this.logger.error(error.message);
                    delete this._publishers[id];
                    throw error;
                });
            }
        }
        this.logger.log(`Dispose of transport`);
        await transport.dispose().catch((error) => {
            this.logger.error(error.message);
            throw error;
        });
        this.logger.log(`Dispose of core`);
        userAgentCore.dispose();
        this.transitionState(_user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped);
    }
    /** @internal */
    _makeInviter(targetURI, options) {
        return new _inviter_js__WEBPACK_IMPORTED_MODULE_11__.Inviter(this, targetURI, options);
    }
    /** @param reconnectionAttempt */
    attemptReconnection(reconnectionAttempt = 1) {
        const reconnectionAttempts = this.options.reconnectionAttempts;
        const reconnectionDelay = this.options.reconnectionDelay;
        if (reconnectionAttempt > reconnectionAttempts) {
            this.logger.log(`Maximum reconnection attempts reached`);
            return;
        }
        this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - trying`);
        setTimeout(() => {
            this.reconnect()
                .then(() => {
                this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - succeeded`);
            })
                .catch((error) => {
                this.logger.error(error.message);
                this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - failed`);
                this.attemptReconnection(++reconnectionAttempt);
            });
        }, reconnectionAttempt === 1 ? 0 : reconnectionDelay * 1000);
    }
    initContact() {
        const contactName = this.options.contactName !== "" ? this.options.contactName : (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__.createRandomToken)(8);
        const contactParams = this.options.contactParams;
        const contact = {
            pubGruu: undefined,
            tempGruu: undefined,
            uri: new _grammar_uri_js__WEBPACK_IMPORTED_MODULE_3__.URI("sip", contactName, this.options.viaHost, undefined, contactParams),
            toString: (contactToStringOptions = {}) => {
                const anonymous = contactToStringOptions.anonymous || false;
                const outbound = contactToStringOptions.outbound || false;
                const register = contactToStringOptions.register || false;
                let contactString = "<";
                if (anonymous) {
                    contactString +=
                        this.contact.tempGruu ||
                            `sip:anonymous@anonymous.invalid;transport=${contactParams.transport ? contactParams.transport : "ws"}`;
                }
                else if (register) {
                    contactString += this.contact.uri;
                }
                else {
                    contactString += this.contact.pubGruu || this.contact.uri;
                }
                if (outbound) {
                    contactString += ";ob";
                }
                contactString += ">";
                if (this.options.instanceIdAlwaysAdded) {
                    contactString += ';+sip.instance="<urn:uuid:' + this._instanceId + '>"';
                }
                return contactString;
            }
        };
        return contact;
    }
    initCore() {
        let supportedOptionTags = [];
        supportedOptionTags.push("outbound");
        if (this.options.sipExtension100rel === _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__.SIPExtension.Supported) {
            supportedOptionTags.push("100rel");
        }
        if (this.options.sipExtensionReplaces === _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__.SIPExtension.Supported) {
            supportedOptionTags.push("replaces");
        }
        if (this.options.sipExtensionExtraSupported) {
            supportedOptionTags.push(...this.options.sipExtensionExtraSupported);
        }
        if (!this.options.hackAllowUnregisteredOptionTags) {
            supportedOptionTags = supportedOptionTags.filter((optionTag) => _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__.UserAgentRegisteredOptionTags[optionTag]);
        }
        supportedOptionTags = Array.from(new Set(supportedOptionTags));
        const supportedOptionTagsResponse = supportedOptionTags.slice();
        if (this.contact.pubGruu || this.contact.tempGruu) {
            supportedOptionTagsResponse.push("gruu");
        }
        const userAgentCoreConfiguration = {
            aor: this.options.uri,
            contact: this.contact,
            displayName: this.options.displayName,
            loggerFactory: this.loggerFactory,
            hackViaTcp: this.options.hackViaTcp,
            routeSet: this.options.preloadedRouteSet,
            supportedOptionTags,
            supportedOptionTagsResponse,
            sipjsId: this.options.sipjsId,
            userAgentHeaderFieldValue: this.options.userAgentString,
            viaForceRport: this.options.forceRport,
            viaHost: this.options.viaHost,
            authenticationFactory: () => {
                const username = this.options.authorizationUsername
                    ? this.options.authorizationUsername
                    : this.options.uri.user;
                const password = this.options.authorizationPassword ? this.options.authorizationPassword : undefined;
                const ha1 = this.options.authorizationHa1 ? this.options.authorizationHa1 : undefined;
                return new _core_messages_digest_authentication_js__WEBPACK_IMPORTED_MODULE_12__.DigestAuthentication(this.getLoggerFactory(), ha1, username, password);
            },
            transportAccessor: () => this.transport
        };
        const userAgentCoreDelegate = {
            onInvite: (incomingInviteRequest) => {
                var _a;
                const invitation = new _invitation_js__WEBPACK_IMPORTED_MODULE_13__.Invitation(this, incomingInviteRequest);
                incomingInviteRequest.delegate = {
                    onCancel: (cancel) => {
                        invitation._onCancel(cancel);
                    },
                    // eslint-disable-next-line @typescript-eslint/no-unused-vars
                    onTransportError: (error) => {
                        this.logger.error("A transport error has occurred while handling an incoming INVITE request.");
                    }
                };
                incomingInviteRequest.trying();
                if (this.options.sipExtensionReplaces !== _user_agent_options_js__WEBPACK_IMPORTED_MODULE_8__.SIPExtension.Unsupported) {
                    const message = incomingInviteRequest.message;
                    const replaces = message.parseHeader("replaces");
                    if (replaces) {
                        const callId = replaces.call_id;
                        if (typeof callId !== "string") {
                            throw new Error("Type of call id is not string");
                        }
                        const toTag = replaces.replaces_to_tag;
                        if (typeof toTag !== "string") {
                            throw new Error("Type of to tag is not string");
                        }
                        const fromTag = replaces.replaces_from_tag;
                        if (typeof fromTag !== "string") {
                            throw new Error("type of from tag is not string");
                        }
                        const targetDialogId = callId + toTag + fromTag;
                        const targetDialog = this.userAgentCore.dialogs.get(targetDialogId);
                        if (!targetDialog) {
                            invitation.reject({ statusCode: 481 });
                            return;
                        }
                        if (!targetDialog.early && replaces.early_only === true) {
                            invitation.reject({ statusCode: 486 });
                            return;
                        }
                        const targetSession = this._sessions[callId + fromTag] || this._sessions[callId + toTag] || undefined;
                        if (!targetSession) {
                            throw new Error("Session does not exist.");
                        }
                        invitation._replacee = targetSession;
                    }
                }
                if ((_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onInvite) {
                    if (invitation.autoSendAnInitialProvisionalResponse) {
                        invitation.progress().then(() => {
                            var _a;
                            if (((_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onInvite) === undefined) {
                                throw new Error("onInvite undefined.");
                            }
                            this.delegate.onInvite(invitation);
                        });
                        return;
                    }
                    this.delegate.onInvite(invitation);
                    return;
                }
                invitation.reject({ statusCode: 486 });
            },
            onMessage: (incomingMessageRequest) => {
                if (this.delegate && this.delegate.onMessage) {
                    const message = new _message_js__WEBPACK_IMPORTED_MODULE_14__.Message(incomingMessageRequest);
                    this.delegate.onMessage(message);
                }
                else {
                    incomingMessageRequest.accept();
                }
            },
            onNotify: (incomingNotifyRequest) => {
                if (this.delegate && this.delegate.onNotify) {
                    const notification = new _notification_js__WEBPACK_IMPORTED_MODULE_15__.Notification(incomingNotifyRequest);
                    this.delegate.onNotify(notification);
                }
                else {
                    if (this.options.allowLegacyNotifications) {
                        incomingNotifyRequest.accept();
                    }
                    else {
                        incomingNotifyRequest.reject({ statusCode: 481 });
                    }
                }
            },
            onRefer: (incomingReferRequest) => {
                this.logger.warn("Received an out of dialog REFER request");
                if (this.delegate && this.delegate.onReferRequest) {
                    this.delegate.onReferRequest(incomingReferRequest);
                }
                else {
                    incomingReferRequest.reject({ statusCode: 405 });
                }
            },
            onRegister: (incomingRegisterRequest) => {
                this.logger.warn("Received an out of dialog REGISTER request");
                if (this.delegate && this.delegate.onRegisterRequest) {
                    this.delegate.onRegisterRequest(incomingRegisterRequest);
                }
                else {
                    incomingRegisterRequest.reject({ statusCode: 405 });
                }
            },
            onSubscribe: (incomingSubscribeRequest) => {
                this.logger.warn("Received an out of dialog SUBSCRIBE request");
                if (this.delegate && this.delegate.onSubscribeRequest) {
                    this.delegate.onSubscribeRequest(incomingSubscribeRequest);
                }
                else {
                    incomingSubscribeRequest.reject({ statusCode: 405 });
                }
            }
        };
        return new _core_user_agent_core_user_agent_core_js__WEBPACK_IMPORTED_MODULE_16__.UserAgentCore(userAgentCoreConfiguration, userAgentCoreDelegate);
    }
    initTransportCallbacks() {
        this.transport.onConnect = () => this.onTransportConnect();
        this.transport.onDisconnect = (error) => this.onTransportDisconnect(error);
        this.transport.onMessage = (message) => this.onTransportMessage(message);
    }
    onTransportConnect() {
        if (this.state === _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped) {
            return;
        }
        if (this.delegate && this.delegate.onConnect) {
            this.delegate.onConnect();
        }
    }
    onTransportDisconnect(error) {
        if (this.state === _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped) {
            return;
        }
        if (this.delegate && this.delegate.onDisconnect) {
            this.delegate.onDisconnect(error);
        }
        if (error && this.options.reconnectionAttempts > 0) {
            this.attemptReconnection();
        }
    }
    onTransportMessage(messageString) {
        const message = _core_messages_parser_js__WEBPACK_IMPORTED_MODULE_17__.Parser.parseMessage(messageString, this.getLogger("sip.Parser"));
        if (!message) {
            this.logger.warn("Failed to parse incoming message. Dropping.");
            return;
        }
        if (this.state === _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped && message instanceof _core_messages_incoming_request_message_js__WEBPACK_IMPORTED_MODULE_18__.IncomingRequestMessage) {
            this.logger.warn(`Received ${message.method} request while stopped. Dropping.`);
            return;
        }
        const hasMinimumHeaders = () => {
            const mandatoryHeaders = ["from", "to", "call_id", "cseq", "via"];
            for (const header of mandatoryHeaders) {
                if (!message.hasHeader(header)) {
                    this.logger.warn(`Missing mandatory header field : ${header}.`);
                    return false;
                }
            }
            return true;
        };
        if (message instanceof _core_messages_incoming_request_message_js__WEBPACK_IMPORTED_MODULE_18__.IncomingRequestMessage) {
            if (!hasMinimumHeaders()) {
                this.logger.warn(`Request missing mandatory header field. Dropping.`);
                return;
            }
            if (!message.toTag && message.callId.substr(0, 5) === this.options.sipjsId) {
                this.userAgentCore.replyStateless(message, { statusCode: 482 });
                return;
            }
            const len = (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__.utf8Length)(message.body);
            const contentLength = message.getHeader("content-length");
            if (contentLength && len < Number(contentLength)) {
                this.userAgentCore.replyStateless(message, { statusCode: 400 });
                return;
            }
        }
        if (message instanceof _core_messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_19__.IncomingResponseMessage) {
            if (!hasMinimumHeaders()) {
                this.logger.warn(`Response missing mandatory header field. Dropping.`);
                return;
            }
            if (message.getHeaders("via").length > 1) {
                this.logger.warn("More than one Via header field present in the response. Dropping.");
                return;
            }
            if (message.via.host !== this.options.viaHost || message.via.port !== undefined) {
                this.logger.warn("Via sent-by in the response does not match UA Via host value. Dropping.");
                return;
            }
            const len = (0,_core_messages_utils_js__WEBPACK_IMPORTED_MODULE_2__.utf8Length)(message.body);
            const contentLength = message.getHeader("content-length");
            if (contentLength && len < Number(contentLength)) {
                this.logger.warn("Message body length is lower than the value in Content-Length header field. Dropping.");
                return;
            }
        }
        if (message instanceof _core_messages_incoming_request_message_js__WEBPACK_IMPORTED_MODULE_18__.IncomingRequestMessage) {
            this.userAgentCore.receiveIncomingRequestFromTransport(message);
            return;
        }
        if (message instanceof _core_messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_19__.IncomingResponseMessage) {
            this.userAgentCore.receiveIncomingResponseFromTransport(message);
            return;
        }
        throw new Error("Invalid message type.");
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    transitionState(newState, error) {
        const invalidTransition = () => {
            throw new Error(`Invalid state transition from ${this._state} to ${newState}`);
        };
        switch (this._state) {
            case _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Started:
                if (newState !== _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped) {
                    invalidTransition();
                }
                break;
            case _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Stopped:
                if (newState !== _user_agent_state_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentState.Started) {
                    invalidTransition();
                }
                break;
            default:
                throw new Error("Unknown state.");
        }
        this.logger.log(`Transitioned from ${this._state} to ${newState}`);
        this._state = newState;
        this._stateEventEmitter.emit(this._state);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "LoggerFactory": () => ( LoggerFactory)
 });
 var _levels_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(52);
 var _logger_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(53);


/** @public */
class LoggerFactory {
    constructor() {
        this.builtinEnabled = true;
        this._level = _levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.log;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        this.loggers = {};
        this.logger = this.getLogger("sip:loggerfactory");
    }
    get level() {
        return this._level;
    }
    set level(newLevel) {
        if (newLevel >= 0 && newLevel <= 3) {
            this._level = newLevel;
        }
        else if (newLevel > 3) {
            this._level = 3;
            // eslint-disable-next-line no-prototype-builtins
        }
        else if (_levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.hasOwnProperty(newLevel)) {
            this._level = newLevel;
        }
        else {
            this.logger.error("invalid 'level' parameter value: " + JSON.stringify(newLevel));
        }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    get connector() {
        return this._connector;
    }
    set connector(value) {
        if (!value) {
            this._connector = undefined;
        }
        else if (typeof value === "function") {
            this._connector = value;
        }
        else {
            this.logger.error("invalid 'connector' parameter value: " + JSON.stringify(value));
        }
    }
    getLogger(category, label) {
        if (label && this.level === 3) {
            return new _logger_js__WEBPACK_IMPORTED_MODULE_1__.Logger(this, category, label);
        }
        else if (this.loggers[category]) {
            return this.loggers[category];
        }
        else {
            const logger = new _logger_js__WEBPACK_IMPORTED_MODULE_1__.Logger(this, category);
            this.loggers[category] = logger;
            return logger;
        }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    genericLog(levelToLog, category, label, content) {
        if (this.level >= levelToLog) {
            if (this.builtinEnabled) {
                this.print(levelToLog, category, label, content);
            }
        }
        if (this.connector) {
            this.connector(_levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels[levelToLog], category, label, content);
        }
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    print(levelToLog, category, label, content) {
        if (typeof content === "string") {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const prefix = [new Date(), category];
            if (label) {
                prefix.push(label);
            }
            content = prefix.concat(content).join(" | ");
        }
        switch (levelToLog) {
            case _levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.error:
                // eslint-disable-next-line no-console
                console.error(content);
                break;
            case _levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.warn:
                // eslint-disable-next-line no-console
                console.warn(content);
                break;
            case _levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.log:
                // eslint-disable-next-line no-console
                console.log(content);
                break;
            case _levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.debug:
                // eslint-disable-next-line no-console
                console.debug(content);
                break;
            default:
                break;
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Levels": () => ( Levels)
 });
/** @public */
var Levels;
(function (Levels) {
    Levels[Levels["error"] = 0] = "error";
    Levels[Levels["warn"] = 1] = "warn";
    Levels[Levels["log"] = 2] = "log";
    Levels[Levels["debug"] = 3] = "debug";
})(Levels = Levels || (Levels = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Logger": () => ( Logger)
 });
 var _levels_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(52);

/** @public */
class Logger {
    constructor(logger, category, label) {
        this.logger = logger;
        this.category = category;
        this.label = label;
    }
    error(content) {
        this.genericLog(_levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.error, content);
    }
    warn(content) {
        this.genericLog(_levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.warn, content);
    }
    log(content) {
        this.genericLog(_levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.log, content);
    }
    debug(content) {
        this.genericLog(_levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels.debug, content);
    }
    genericLog(level, content) {
        this.logger.genericLog(level, this.category, this.label, content);
    }
    get level() {
        return this.logger.level;
    }
    set level(newLevel) {
        this.logger.level = newLevel;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "defaultSessionDescriptionHandlerFactory": () => ( defaultSessionDescriptionHandlerFactory)
 });
 var _media_stream_factory_default_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(55);
 var _peer_connection_configuration_default_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(56);
 var _session_description_handler_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(57);



/**
 * @remarks
 * @param mediaStreamFactory
 * @public
 */
function defaultSessionDescriptionHandlerFactory(mediaStreamFactory) {
    return (session, options) => {
        if (mediaStreamFactory === undefined) {
            mediaStreamFactory = (0,_media_stream_factory_default_js__WEBPACK_IMPORTED_MODULE_0__.defaultMediaStreamFactory)();
        }
        const iceGatheringTimeout = (options === null || options === void 0 ? void 0 : options.iceGatheringTimeout) !== undefined ? options === null || options === void 0 ? void 0 : options.iceGatheringTimeout : 5000;
        const sessionDescriptionHandlerConfiguration = {
            iceGatheringTimeout,
            peerConnectionConfiguration: Object.assign(Object.assign({}, (0,_peer_connection_configuration_default_js__WEBPACK_IMPORTED_MODULE_1__.defaultPeerConnectionConfiguration)()), options === null || options === void 0 ? void 0 : options.peerConnectionConfiguration)
        };
        const logger = session.userAgent.getLogger("sip.SessionDescriptionHandler");
        return new _session_description_handler_js__WEBPACK_IMPORTED_MODULE_2__.SessionDescriptionHandler(logger, mediaStreamFactory, sessionDescriptionHandlerConfiguration);
    };
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "defaultMediaStreamFactory": () => ( defaultMediaStreamFactory)
 });
/** @public */
function defaultMediaStreamFactory() {
    return (constraints) => {
        if (!constraints.audio && !constraints.video) {
            return Promise.resolve(new MediaStream());
        }
        if (navigator.mediaDevices === undefined) {
            return Promise.reject(new Error("Media devices not available in insecure contexts."));
        }
        return navigator.mediaDevices.getUserMedia.call(navigator.mediaDevices, constraints);
    };
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "defaultPeerConnectionConfiguration": () => ( defaultPeerConnectionConfiguration)
 });
/** @public */
function defaultPeerConnectionConfiguration() {
    const configuration = {
        bundlePolicy: "balanced",
        certificates: undefined,
        iceCandidatePoolSize: 0,
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
        iceTransportPolicy: "all",
        rtcpMuxPolicy: "require"
    };
    return configuration;
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionDescriptionHandler": () => ( SessionDescriptionHandler)
 });
/**
 * @remarks
 * @privateRemarks
 * @public
 */
class SessionDescriptionHandler {
    /**
     * @param logger
     * @param mediaStreamFactory
     * @param options
     */
    constructor(logger, mediaStreamFactory, sessionDescriptionHandlerConfiguration) {
        logger.debug("SessionDescriptionHandler.constructor");
        this.logger = logger;
        this.mediaStreamFactory = mediaStreamFactory;
        this.sessionDescriptionHandlerConfiguration = sessionDescriptionHandlerConfiguration;
        this._localMediaStream = new MediaStream();
        this._remoteMediaStream = new MediaStream();
        this._peerConnection = new RTCPeerConnection(sessionDescriptionHandlerConfiguration === null || sessionDescriptionHandlerConfiguration === void 0 ? void 0 : sessionDescriptionHandlerConfiguration.peerConnectionConfiguration);
        this.initPeerConnectionEventHandlers();
    }
    get localMediaStream() {
        return this._localMediaStream;
    }
    get remoteMediaStream() {
        return this._remoteMediaStream;
    }
    get dataChannel() {
        return this._dataChannel;
    }
    get peerConnection() {
        return this._peerConnection;
    }
    get peerConnectionDelegate() {
        return this._peerConnectionDelegate;
    }
    set peerConnectionDelegate(delegate) {
        this._peerConnectionDelegate = delegate;
    }
    static dispatchAddTrackEvent(stream, track) {
        stream.dispatchEvent(new MediaStreamTrackEvent("addtrack", { track }));
    }
    static dispatchRemoveTrackEvent(stream, track) {
        stream.dispatchEvent(new MediaStreamTrackEvent("removetrack", { track }));
    }
    close() {
        this.logger.debug("SessionDescriptionHandler.close");
        if (this._peerConnection === undefined) {
            return;
        }
        this._peerConnection.getReceivers().forEach((receiver) => {
            receiver.track && receiver.track.stop();
        });
        this._peerConnection.getSenders().forEach((sender) => {
            sender.track && sender.track.stop();
        });
        if (this._dataChannel) {
            this._dataChannel.close();
        }
        this._peerConnection.close();
        this._peerConnection = undefined;
    }
    /** @param enable */
    enableReceiverTracks(enable) {
        const peerConnection = this.peerConnection;
        if (!peerConnection) {
            throw new Error("Peer connection closed.");
        }
        peerConnection.getReceivers().forEach((receiver) => {
            if (receiver.track) {
                receiver.track.enabled = enable;
            }
        });
    }
    /** @param enable */
    enableSenderTracks(enable) {
        const peerConnection = this.peerConnection;
        if (!peerConnection) {
            throw new Error("Peer connection closed.");
        }
        peerConnection.getSenders().forEach((sender) => {
            if (sender.track) {
                sender.track.enabled = enable;
            }
        });
    }
    /**
     * @param options
     * @param modifiers
     */
    getDescription(options, modifiers) {
        var _a, _b;
        this.logger.debug("SessionDescriptionHandler.getDescription");
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        this.onDataChannel = options === null || options === void 0 ? void 0 : options.onDataChannel;
        const iceRestart = (_a = options === null || options === void 0 ? void 0 : options.offerOptions) === null || _a === void 0 ? void 0 : _a.iceRestart;
        const iceTimeout = (options === null || options === void 0 ? void 0 : options.iceGatheringTimeout) === undefined
            ? (_b = this.sessionDescriptionHandlerConfiguration) === null || _b === void 0 ? void 0 : _b.iceGatheringTimeout
            : options === null || options === void 0 ? void 0 : options.iceGatheringTimeout;
        return this.getLocalMediaStream(options)
            .then(() => this.updateDirection(options))
            .then(() => this.createDataChannel(options))
            .then(() => this.createLocalOfferOrAnswer(options))
            .then((sessionDescription) => this.applyModifiers(sessionDescription, modifiers))
            .then((sessionDescription) => this.setLocalSessionDescription(sessionDescription))
            .then(() => this.waitForIceGatheringComplete(iceRestart, iceTimeout))
            .then(() => this.getLocalSessionDescription())
            .then((sessionDescription) => {
            return {
                body: sessionDescription.sdp,
                contentType: "application/sdp"
            };
        })
            .catch((error) => {
            this.logger.error("SessionDescriptionHandler.getDescription failed - " + error);
            throw error;
        });
    }
    /** @param contentType */
    hasDescription(contentType) {
        this.logger.debug("SessionDescriptionHandler.hasDescription");
        return contentType === "application/sdp";
    }
    iceGatheringComplete() {
        this.logger.debug("SessionDescriptionHandler.iceGatheringComplete");
        if (this.iceGatheringCompleteTimeoutId !== undefined) {
            this.logger.debug("SessionDescriptionHandler.iceGatheringComplete - clearing timeout");
            clearTimeout(this.iceGatheringCompleteTimeoutId);
            this.iceGatheringCompleteTimeoutId = undefined;
        }
        if (this.iceGatheringCompletePromise !== undefined) {
            this.logger.debug("SessionDescriptionHandler.iceGatheringComplete - resolving promise");
            this.iceGatheringCompleteResolve && this.iceGatheringCompleteResolve();
            this.iceGatheringCompletePromise = undefined;
            this.iceGatheringCompleteResolve = undefined;
            this.iceGatheringCompleteReject = undefined;
        }
    }
    /**
     * @param tones
     * @param options
     */
    sendDtmf(tones, options) {
        this.logger.debug("SessionDescriptionHandler.sendDtmf");
        if (this._peerConnection === undefined) {
            this.logger.error("SessionDescriptionHandler.sendDtmf failed - peer connection closed");
            return false;
        }
        const senders = this._peerConnection.getSenders();
        if (senders.length === 0) {
            this.logger.error("SessionDescriptionHandler.sendDtmf failed - no senders");
            return false;
        }
        const dtmfSender = senders[0].dtmf;
        if (!dtmfSender) {
            this.logger.error("SessionDescriptionHandler.sendDtmf failed - no DTMF sender");
            return false;
        }
        const duration = options === null || options === void 0 ? void 0 : options.duration;
        const interToneGap = options === null || options === void 0 ? void 0 : options.interToneGap;
        try {
            dtmfSender.insertDTMF(tones, duration, interToneGap);
        }
        catch (e) {
            this.logger.error(e.toString());
            return false;
        }
        this.logger.log("SessionDescriptionHandler.sendDtmf sent via RTP: " + tones.toString());
        return true;
    }
    /**
     * @param sdp
     * @param options
     * @param modifiers
     */
    setDescription(sdp, options, modifiers) {
        this.logger.debug("SessionDescriptionHandler.setDescription");
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        this.onDataChannel = options === null || options === void 0 ? void 0 : options.onDataChannel;
        const type = this._peerConnection.signalingState === "have-local-offer" ? "answer" : "offer";
        return this.getLocalMediaStream(options)
            .then(() => this.applyModifiers({ sdp, type }, modifiers))
            .then((sessionDescription) => this.setRemoteSessionDescription(sessionDescription))
            .catch((error) => {
            this.logger.error("SessionDescriptionHandler.setDescription failed - " + error);
            throw error;
        });
    }
    /**
     * @param sdp
     * @param modifiers
     */
    applyModifiers(sdp, modifiers) {
        this.logger.debug("SessionDescriptionHandler.applyModifiers");
        if (!modifiers || modifiers.length === 0) {
            return Promise.resolve(sdp);
        }
        return modifiers
            .reduce((cur, next) => cur.then(next), Promise.resolve(sdp))
            .then((modified) => {
            this.logger.debug("SessionDescriptionHandler.applyModifiers - modified sdp");
            if (!modified.sdp || !modified.type) {
                throw new Error("Invalid SDP.");
            }
            return { sdp: modified.sdp, type: modified.type };
        });
    }
    /**
     * @remarks
     * @param options
     */
    createDataChannel(options) {
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        if ((options === null || options === void 0 ? void 0 : options.dataChannel) !== true) {
            return Promise.resolve();
        }
        if (this._dataChannel) {
            return Promise.resolve();
        }
        switch (this._peerConnection.signalingState) {
            case "stable":
                this.logger.debug("SessionDescriptionHandler.createDataChannel - creating data channel");
                try {
                    this._dataChannel = this._peerConnection.createDataChannel((options === null || options === void 0 ? void 0 : options.dataChannelLabel) || "", options === null || options === void 0 ? void 0 : options.dataChannelOptions);
                    if (this.onDataChannel) {
                        this.onDataChannel(this._dataChannel);
                    }
                    return Promise.resolve();
                }
                catch (error) {
                    return Promise.reject(error);
                }
            case "have-remote-offer":
                return Promise.resolve();
            case "have-local-offer":
            case "have-local-pranswer":
            case "have-remote-pranswer":
            case "closed":
            default:
                return Promise.reject(new Error("Invalid signaling state " + this._peerConnection.signalingState));
        }
    }
    /** @param options */
    createLocalOfferOrAnswer(options) {
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        switch (this._peerConnection.signalingState) {
            case "stable":
                this.logger.debug("SessionDescriptionHandler.createLocalOfferOrAnswer - creating SDP offer");
                return this._peerConnection.createOffer(options === null || options === void 0 ? void 0 : options.offerOptions);
            case "have-remote-offer":
                this.logger.debug("SessionDescriptionHandler.createLocalOfferOrAnswer - creating SDP answer");
                return this._peerConnection.createAnswer(options === null || options === void 0 ? void 0 : options.answerOptions);
            case "have-local-offer":
            case "have-local-pranswer":
            case "have-remote-pranswer":
            case "closed":
            default:
                return Promise.reject(new Error("Invalid signaling state " + this._peerConnection.signalingState));
        }
    }
    /** @param options */
    getLocalMediaStream(options) {
        this.logger.debug("SessionDescriptionHandler.getLocalMediaStream");
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        let constraints = Object.assign({}, options === null || options === void 0 ? void 0 : options.constraints);
        if (this.localMediaStreamConstraints) {
            constraints.audio = constraints.audio || this.localMediaStreamConstraints.audio;
            constraints.video = constraints.video || this.localMediaStreamConstraints.video;
            if (JSON.stringify(this.localMediaStreamConstraints.audio) === JSON.stringify(constraints.audio) &&
                JSON.stringify(this.localMediaStreamConstraints.video) === JSON.stringify(constraints.video)) {
                return Promise.resolve();
            }
        }
        else {
            if (constraints.audio === undefined && constraints.video === undefined) {
                constraints = { audio: true };
            }
        }
        this.localMediaStreamConstraints = constraints;
        return this.mediaStreamFactory(constraints, this, options).then((mediaStream) => this.setLocalMediaStream(mediaStream));
    }
    /**
     * @remarks
     * @param stream
     */
    setLocalMediaStream(stream) {
        this.logger.debug("SessionDescriptionHandler.setLocalMediaStream");
        if (!this._peerConnection) {
            throw new Error("Peer connection undefined.");
        }
        const pc = this._peerConnection;
        const localStream = this._localMediaStream;
        const trackUpdates = [];
        const updateTrack = (newTrack) => {
            const kind = newTrack.kind;
            if (kind !== "audio" && kind !== "video") {
                throw new Error(`Unknown new track kind ${kind}.`);
            }
            const sender = pc.getSenders().find((sender) => sender.track && sender.track.kind === kind);
            if (sender) {
                trackUpdates.push(new Promise((resolve) => {
                    this.logger.debug(`SessionDescriptionHandler.setLocalMediaStream - replacing sender ${kind} track`);
                    resolve();
                }).then(() => sender
                    .replaceTrack(newTrack)
                    .then(() => {
                    const oldTrack = localStream.getTracks().find((localTrack) => localTrack.kind === kind);
                    if (oldTrack) {
                        oldTrack.stop();
                        localStream.removeTrack(oldTrack);
                        SessionDescriptionHandler.dispatchRemoveTrackEvent(localStream, oldTrack);
                    }
                    localStream.addTrack(newTrack);
                    SessionDescriptionHandler.dispatchAddTrackEvent(localStream, newTrack);
                })
                    .catch((error) => {
                    this.logger.error(`SessionDescriptionHandler.setLocalMediaStream - failed to replace sender ${kind} track`);
                    throw error;
                })));
            }
            else {
                trackUpdates.push(new Promise((resolve) => {
                    this.logger.debug(`SessionDescriptionHandler.setLocalMediaStream - adding sender ${kind} track`);
                    resolve();
                }).then(() => {
                    try {
                        pc.addTrack(newTrack, localStream);
                    }
                    catch (error) {
                        this.logger.error(`SessionDescriptionHandler.setLocalMediaStream - failed to add sender ${kind} track`);
                        throw error;
                    }
                    localStream.addTrack(newTrack);
                    SessionDescriptionHandler.dispatchAddTrackEvent(localStream, newTrack);
                }));
            }
        };
        const audioTracks = stream.getAudioTracks();
        if (audioTracks.length) {
            updateTrack(audioTracks[0]);
        }
        const videoTracks = stream.getVideoTracks();
        if (videoTracks.length) {
            updateTrack(videoTracks[0]);
        }
        return trackUpdates.reduce((p, x) => p.then(() => x), Promise.resolve());
    }
    getLocalSessionDescription() {
        this.logger.debug("SessionDescriptionHandler.getLocalSessionDescription");
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        const sdp = this._peerConnection.localDescription;
        if (!sdp) {
            return Promise.reject(new Error("Failed to get local session description"));
        }
        return Promise.resolve(sdp);
    }
    /** @param sessionDescription */
    setLocalSessionDescription(sessionDescription) {
        this.logger.debug("SessionDescriptionHandler.setLocalSessionDescription");
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        return this._peerConnection.setLocalDescription(sessionDescription);
    }
    /** @param sessionDescription */
    setRemoteSessionDescription(sessionDescription) {
        this.logger.debug("SessionDescriptionHandler.setRemoteSessionDescription");
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        const sdp = sessionDescription.sdp;
        let type;
        switch (this._peerConnection.signalingState) {
            case "stable":
                type = "offer";
                break;
            case "have-local-offer":
                type = "answer";
                break;
            case "have-local-pranswer":
            case "have-remote-offer":
            case "have-remote-pranswer":
            case "closed":
            default:
                return Promise.reject(new Error("Invalid signaling state " + this._peerConnection.signalingState));
        }
        if (!sdp) {
            this.logger.error("SessionDescriptionHandler.setRemoteSessionDescription failed - cannot set null sdp");
            return Promise.reject(new Error("SDP is undefined"));
        }
        return this._peerConnection.setRemoteDescription({ sdp, type });
    }
    /**
     * @remarks
     * @param track
     */
    setRemoteTrack(track) {
        this.logger.debug("SessionDescriptionHandler.setRemoteTrack");
        const remoteStream = this._remoteMediaStream;
        if (remoteStream.getTrackById(track.id)) {
            this.logger.debug(`SessionDescriptionHandler.setRemoteTrack - have remote ${track.kind} track`);
        }
        else if (track.kind === "audio") {
            this.logger.debug(`SessionDescriptionHandler.setRemoteTrack - adding remote ${track.kind} track`);
            remoteStream.getAudioTracks().forEach((track) => {
                track.stop();
                remoteStream.removeTrack(track);
                SessionDescriptionHandler.dispatchRemoveTrackEvent(remoteStream, track);
            });
            remoteStream.addTrack(track);
            SessionDescriptionHandler.dispatchAddTrackEvent(remoteStream, track);
        }
        else if (track.kind === "video") {
            this.logger.debug(`SessionDescriptionHandler.setRemoteTrack - adding remote ${track.kind} track`);
            remoteStream.getVideoTracks().forEach((track) => {
                track.stop();
                remoteStream.removeTrack(track);
                SessionDescriptionHandler.dispatchRemoveTrackEvent(remoteStream, track);
            });
            remoteStream.addTrack(track);
            SessionDescriptionHandler.dispatchAddTrackEvent(remoteStream, track);
        }
    }
    /** @param options */
    updateDirection(options) {
        if (this._peerConnection === undefined) {
            return Promise.reject(new Error("Peer connection closed."));
        }
        switch (this._peerConnection.signalingState) {
            case "stable":
                this.logger.debug("SessionDescriptionHandler.updateDirection - setting offer direction");
                {
                    const directionToOffer = (currentDirection) => {
                        switch (currentDirection) {
                            case "inactive":
                                return (options === null || options === void 0 ? void 0 : options.hold) ? "inactive" : "recvonly";
                            case "recvonly":
                                return (options === null || options === void 0 ? void 0 : options.hold) ? "inactive" : "recvonly";
                            case "sendonly":
                                return (options === null || options === void 0 ? void 0 : options.hold) ? "sendonly" : "sendrecv";
                            case "sendrecv":
                                return (options === null || options === void 0 ? void 0 : options.hold) ? "sendonly" : "sendrecv";
                            case "stopped":
                                return "stopped";
                            default:
                                throw new Error("Should never happen");
                        }
                    };
                    this._peerConnection.getTransceivers().forEach((transceiver) => {
                        if (transceiver.direction ) {
                            const offerDirection = directionToOffer(transceiver.direction);
                            if (transceiver.direction !== offerDirection) {
                                transceiver.direction = offerDirection;
                            }
                        }
                    });
                }
                break;
            case "have-remote-offer":
                this.logger.debug("SessionDescriptionHandler.updateDirection - setting answer direction");
                {
                    const offeredDirection = (() => {
                        const description = this._peerConnection.remoteDescription;
                        if (!description) {
                            throw new Error("Failed to read remote offer");
                        }
                        const searchResult = /a=sendrecv\r\n|a=sendonly\r\n|a=recvonly\r\n|a=inactive\r\n/.exec(description.sdp);
                        if (searchResult) {
                            switch (searchResult[0]) {
                                case "a=inactive\r\n":
                                    return "inactive";
                                case "a=recvonly\r\n":
                                    return "recvonly";
                                case "a=sendonly\r\n":
                                    return "sendonly";
                                case "a=sendrecv\r\n":
                                    return "sendrecv";
                                default:
                                    throw new Error("Should never happen");
                            }
                        }
                        return "sendrecv";
                    })();
                    const answerDirection = (() => {
                        switch (offeredDirection) {
                            case "inactive":
                                return "inactive";
                            case "recvonly":
                                return "sendonly";
                            case "sendonly":
                                return (options === null || options === void 0 ? void 0 : options.hold) ? "inactive" : "recvonly";
                            case "sendrecv":
                                return (options === null || options === void 0 ? void 0 : options.hold) ? "sendonly" : "sendrecv";
                            default:
                                throw new Error("Should never happen");
                        }
                    })();
                    this._peerConnection.getTransceivers().forEach((transceiver) => {
                        if (transceiver.direction ) {
                            if (transceiver.direction !== "stopped" && transceiver.direction !== answerDirection) {
                                transceiver.direction = answerDirection;
                            }
                        }
                    });
                }
                break;
            case "have-local-offer":
            case "have-local-pranswer":
            case "have-remote-pranswer":
            case "closed":
            default:
                return Promise.reject(new Error("Invalid signaling state " + this._peerConnection.signalingState));
        }
        return Promise.resolve();
    }
    /**
     * @param restart
     * @param timeout
     */
    waitForIceGatheringComplete(restart = false, timeout = 0) {
        this.logger.debug("SessionDescriptionHandler.waitForIceGatheringToComplete");
        if (this._peerConnection === undefined) {
            return Promise.reject("Peer connection closed.");
        }
        if (!restart && this._peerConnection.iceGatheringState === "complete") {
            this.logger.debug("SessionDescriptionHandler.waitForIceGatheringToComplete - already complete");
            return Promise.resolve();
        }
        if (this.iceGatheringCompletePromise !== undefined) {
            this.logger.debug("SessionDescriptionHandler.waitForIceGatheringToComplete - rejecting prior waiting promise");
            this.iceGatheringCompleteReject && this.iceGatheringCompleteReject(new Error("Promise superseded."));
            this.iceGatheringCompletePromise = undefined;
            this.iceGatheringCompleteResolve = undefined;
            this.iceGatheringCompleteReject = undefined;
        }
        this.iceGatheringCompletePromise = new Promise((resolve, reject) => {
            this.iceGatheringCompleteResolve = resolve;
            this.iceGatheringCompleteReject = reject;
            if (timeout > 0) {
                this.logger.debug("SessionDescriptionHandler.waitForIceGatheringToComplete - timeout in " + timeout);
                this.iceGatheringCompleteTimeoutId = setTimeout(() => {
                    this.logger.debug("SessionDescriptionHandler.waitForIceGatheringToComplete - timeout");
                    this.iceGatheringComplete();
                }, timeout);
            }
        });
        return this.iceGatheringCompletePromise;
    }
    initPeerConnectionEventHandlers() {
        this.logger.debug("SessionDescriptionHandler.initPeerConnectionEventHandlers");
        if (!this._peerConnection)
            throw new Error("Peer connection undefined.");
        const peerConnection = this._peerConnection;
        peerConnection.onconnectionstatechange = (event) => {
            var _a;
            const newState = peerConnection.connectionState;
            this.logger.debug(`SessionDescriptionHandler.onconnectionstatechange ${newState}`);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.onconnectionstatechange) {
                this._peerConnectionDelegate.onconnectionstatechange(event);
            }
        };
        peerConnection.ondatachannel = (event) => {
            var _a;
            this.logger.debug(`SessionDescriptionHandler.ondatachannel`);
            this._dataChannel = event.channel;
            if (this.onDataChannel) {
                this.onDataChannel(this._dataChannel);
            }
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.ondatachannel) {
                this._peerConnectionDelegate.ondatachannel(event);
            }
        };
        peerConnection.onicecandidate = (event) => {
            var _a;
            this.logger.debug(`SessionDescriptionHandler.onicecandidate`);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.onicecandidate) {
                this._peerConnectionDelegate.onicecandidate(event);
            }
        };
        peerConnection.onicecandidateerror = (event) => {
            var _a;
            this.logger.debug(`SessionDescriptionHandler.onicecandidateerror`);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.onicecandidateerror) {
                this._peerConnectionDelegate.onicecandidateerror(event);
            }
        };
        peerConnection.oniceconnectionstatechange = (event) => {
            var _a;
            const newState = peerConnection.iceConnectionState;
            this.logger.debug(`SessionDescriptionHandler.oniceconnectionstatechange ${newState}`);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.oniceconnectionstatechange) {
                this._peerConnectionDelegate.oniceconnectionstatechange(event);
            }
        };
        peerConnection.onicegatheringstatechange = (event) => {
            var _a;
            const newState = peerConnection.iceGatheringState;
            this.logger.debug(`SessionDescriptionHandler.onicegatheringstatechange ${newState}`);
            if (newState === "complete") {
                this.iceGatheringComplete();
            }
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.onicegatheringstatechange) {
                this._peerConnectionDelegate.onicegatheringstatechange(event);
            }
        };
        peerConnection.onnegotiationneeded = (event) => {
            var _a;
            this.logger.debug(`SessionDescriptionHandler.onnegotiationneeded`);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.onnegotiationneeded) {
                this._peerConnectionDelegate.onnegotiationneeded(event);
            }
        };
        peerConnection.onsignalingstatechange = (event) => {
            var _a;
            const newState = peerConnection.signalingState;
            this.logger.debug(`SessionDescriptionHandler.onsignalingstatechange ${newState}`);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.onsignalingstatechange) {
                this._peerConnectionDelegate.onsignalingstatechange(event);
            }
        };
        peerConnection.ontrack = (event) => {
            var _a;
            const kind = event.track.kind;
            const enabled = event.track.enabled ? "enabled" : "disabled";
            this.logger.debug(`SessionDescriptionHandler.ontrack ${kind} ${enabled}`);
            this.setRemoteTrack(event.track);
            if ((_a = this._peerConnectionDelegate) === null || _a === void 0 ? void 0 : _a.ontrack) {
                this._peerConnectionDelegate.ontrack(event);
            }
        };
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Transport": () => ( Transport)
 });
 var _api_emitter_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(13);
 var _api_exceptions_state_transition_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(9);
 var _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(48);
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(22);




/** @public */
class Transport {
    constructor(logger, options) {
        this._state = _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected;
        this.transitioningState = false;
        this._stateEventEmitter = new _api_emitter_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl();
        this.logger = logger;
        if (options) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const optionsDeprecated = options;
            const wsServersDeprecated = optionsDeprecated === null || optionsDeprecated === void 0 ? void 0 : optionsDeprecated.wsServers;
            const maxReconnectionAttemptsDeprecated = optionsDeprecated === null || optionsDeprecated === void 0 ? void 0 : optionsDeprecated.maxReconnectionAttempts;
            if (wsServersDeprecated !== undefined) {
                const deprecatedMessage = `The transport option "wsServers" as has apparently been specified and has been deprecated. ` +
                    "It will no longer be available starting with SIP.js release 0.16.0. Please update accordingly.";
                this.logger.warn(deprecatedMessage);
            }
            if (maxReconnectionAttemptsDeprecated !== undefined) {
                const deprecatedMessage = `The transport option "maxReconnectionAttempts" as has apparently been specified and has been deprecated. ` +
                    "It will no longer be available starting with SIP.js release 0.16.0. Please update accordingly.";
                this.logger.warn(deprecatedMessage);
            }
            if (wsServersDeprecated && !options.server) {
                if (typeof wsServersDeprecated === "string") {
                    options.server = wsServersDeprecated;
                }
                if (wsServersDeprecated instanceof Array) {
                    options.server = wsServersDeprecated[0];
                }
            }
        }
        this.configuration = Object.assign(Object.assign({}, Transport.defaultOptions), options);
        const url = this.configuration.server;
        const parsed = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_2__.Grammar.parse(url, "absoluteURI");
        if (parsed === -1) {
            this.logger.error(`Invalid WebSocket Server URL "${url}"`);
            throw new Error("Invalid WebSocket Server URL");
        }
        if (!["wss", "ws", "udp"].includes(parsed.scheme)) {
            this.logger.error(`Invalid scheme in WebSocket Server URL "${url}"`);
            throw new Error("Invalid scheme in WebSocket Server URL");
        }
        this._protocol = parsed.scheme.toUpperCase();
    }
    dispose() {
        return this.disconnect();
    }
    get protocol() {
        return this._protocol;
    }
    get server() {
        return this.configuration.server;
    }
    get state() {
        return this._state;
    }
    get stateChange() {
        return this._stateEventEmitter;
    }
    get ws() {
        return this._ws;
    }
    connect() {
        return this._connect();
    }
    disconnect() {
        return this._disconnect();
    }
    isConnected() {
        return this.state === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected;
    }
    /** @param message */
    send(message) {
        return this._send(message);
    }
    _connect() {
        this.logger.log(`Connecting ${this.server}`);
        switch (this.state) {
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting:
                if (this.transitioningState) {
                    return Promise.reject(this.transitionLoopDetectedError(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting));
                }
                if (!this.connectPromise) {
                    throw new Error("Connect promise must be defined.");
                }
                return this.connectPromise;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected:
                if (this.transitioningState) {
                    return Promise.reject(this.transitionLoopDetectedError(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting));
                }
                if (this.connectPromise) {
                    throw new Error("Connect promise must not be defined.");
                }
                return Promise.resolve();
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting:
                if (this.connectPromise) {
                    throw new Error("Connect promise must not be defined.");
                }
                try {
                    this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting);
                }
                catch (e) {
                    if (e instanceof _api_exceptions_state_transition_js__WEBPACK_IMPORTED_MODULE_3__.StateTransitionError) {
                        return Promise.reject(e);
                    }
                    throw e;
                }
                break;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected:
                if (this.connectPromise) {
                    throw new Error("Connect promise must not be defined.");
                }
                try {
                    this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting);
                }
                catch (e) {
                    if (e instanceof _api_exceptions_state_transition_js__WEBPACK_IMPORTED_MODULE_3__.StateTransitionError) {
                        return Promise.reject(e);
                    }
                    throw e;
                }
                break;
            default:
                throw new Error("Unknown state");
        }
        let ws;
        try {
            ws = new WebSocket(this.server, "sip");
            ws.binaryType = "arraybuffer";
            ws.addEventListener("close", (ev) => this.onWebSocketClose(ev, ws));
            ws.addEventListener("error", (ev) => this.onWebSocketError(ev, ws));
            ws.addEventListener("open", (ev) => this.onWebSocketOpen(ev, ws));
            ws.addEventListener("message", (ev) => this.onWebSocketMessage(ev, ws));
            this._ws = ws;
        }
        catch (error) {
            this._ws = undefined;
            this.logger.error("WebSocket construction failed.");
            this.logger.error(error.toString());
            return new Promise((resolve, reject) => {
                this.connectResolve = resolve;
                this.connectReject = reject;
                this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected, error);
            });
        }
        this.connectPromise = new Promise((resolve, reject) => {
            this.connectResolve = resolve;
            this.connectReject = reject;
            this.connectTimeout = setTimeout(() => {
                this.logger.warn("Connect timed out. " +
                    "Exceeded time set in configuration.connectionTimeout: " +
                    this.configuration.connectionTimeout +
                    "s.");
                ws.close(1000);
            }, this.configuration.connectionTimeout * 1000);
        });
        return this.connectPromise;
    }
    _disconnect() {
        this.logger.log(`Disconnecting ${this.server}`);
        switch (this.state) {
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting:
                if (this.disconnectPromise) {
                    throw new Error("Disconnect promise must not be defined.");
                }
                try {
                    this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting);
                }
                catch (e) {
                    if (e instanceof _api_exceptions_state_transition_js__WEBPACK_IMPORTED_MODULE_3__.StateTransitionError) {
                        return Promise.reject(e);
                    }
                    throw e;
                }
                break;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected:
                if (this.disconnectPromise) {
                    throw new Error("Disconnect promise must not be defined.");
                }
                try {
                    this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting);
                }
                catch (e) {
                    if (e instanceof _api_exceptions_state_transition_js__WEBPACK_IMPORTED_MODULE_3__.StateTransitionError) {
                        return Promise.reject(e);
                    }
                    throw e;
                }
                break;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting:
                if (this.transitioningState) {
                    return Promise.reject(this.transitionLoopDetectedError(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting));
                }
                if (!this.disconnectPromise) {
                    throw new Error("Disconnect promise must be defined.");
                }
                return this.disconnectPromise;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected:
                if (this.transitioningState) {
                    return Promise.reject(this.transitionLoopDetectedError(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting));
                }
                if (this.disconnectPromise) {
                    throw new Error("Disconnect promise must not be defined.");
                }
                return Promise.resolve();
            default:
                throw new Error("Unknown state");
        }
        if (!this._ws) {
            throw new Error("WebSocket must be defined.");
        }
        const ws = this._ws;
        this.disconnectPromise = new Promise((resolve, reject) => {
            this.disconnectResolve = resolve;
            this.disconnectReject = reject;
            try {
                ws.close(1000);
            }
            catch (error) {
                this.logger.error("WebSocket close failed.");
                this.logger.error(error.toString());
                throw error;
            }
        });
        return this.disconnectPromise;
    }
    _send(message) {
        if (this.configuration.traceSip === true) {
            this.logger.log("Sending WebSocket message:\n\n" + message + "\n");
        }
        if (this._state !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected) {
            return Promise.reject(new Error("Not connected."));
        }
        if (!this._ws) {
            throw new Error("WebSocket undefined.");
        }
        try {
            this._ws.send(message);
        }
        catch (error) {
            if (error instanceof Error) {
                return Promise.reject(error);
            }
            return Promise.reject(new Error("WebSocket send failed."));
        }
        return Promise.resolve();
    }
    /** @param ev */
    onWebSocketClose(ev, ws) {
        if (ws !== this._ws) {
            return;
        }
        const message = `WebSocket closed ${this.server} (code: ${ev.code})`;
        const error = !this.disconnectPromise ? new Error(message) : undefined;
        if (error) {
            this.logger.warn("WebSocket closed unexpectedly");
        }
        this.logger.log(message);
        this._ws = undefined;
        this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected, error);
    }
    /** @param ev */
    onWebSocketError(ev, ws) {
        if (ws !== this._ws) {
            return;
        }
        this.logger.error("WebSocket error occurred.");
    }
    /** @param ev */
    onWebSocketMessage(ev, ws) {
        if (ws !== this._ws) {
            return;
        }
        const data = ev.data;
        let finishedData;
        if (/^(\r\n)+$/.test(data)) {
            this.clearKeepAliveTimeout();
            if (this.configuration.traceSip === true) {
                this.logger.log("Received WebSocket message with CRLF Keep Alive response");
            }
            return;
        }
        if (!data) {
            this.logger.warn("Received empty message, discarding...");
            return;
        }
        if (typeof data !== "string") {
            try {
                finishedData = new TextDecoder().decode(new Uint8Array(data));
            }
            catch (err) {
                this.logger.error(err.toString());
                this.logger.error("Received WebSocket binary message failed to be converted into string, message discarded");
                return;
            }
            if (this.configuration.traceSip === true) {
                this.logger.log("Received WebSocket binary message:\n\n" + finishedData + "\n");
            }
        }
        else {
            finishedData = data;
            if (this.configuration.traceSip === true) {
                this.logger.log("Received WebSocket text message:\n\n" + finishedData + "\n");
            }
        }
        if (this.state !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected) {
            this.logger.warn("Received message while not connected, discarding...");
            return;
        }
        if (this.onMessage) {
            try {
                this.onMessage(finishedData);
            }
            catch (e) {
                this.logger.error(e.toString());
                this.logger.error("Exception thrown by onMessage callback");
                throw e;
            }
        }
    }
    /** @param ev */
    onWebSocketOpen(ev, ws) {
        if (ws !== this._ws) {
            return;
        }
        if (this._state === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting) {
            this.logger.log(`WebSocket opened ${this.server}`);
            this.transitionState(_api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected);
        }
    }
    /** @param state */
    transitionLoopDetectedError(state) {
        let message = `A state transition loop has been detected.`;
        message += ` An attempt to transition from ${this._state} to ${state} before the prior transition completed.`;
        message += ` Perhaps you are synchronously calling connect() or disconnect() from a callback or state change handler?`;
        this.logger.error(message);
        return new _api_exceptions_state_transition_js__WEBPACK_IMPORTED_MODULE_3__.StateTransitionError("Loop detected.");
    }
    /** @internal */
    transitionState(newState, error) {
        const invalidTransition = () => {
            throw new Error(`Invalid state transition from ${this._state} to ${newState}`);
        };
        if (this.transitioningState) {
            throw this.transitionLoopDetectedError(newState);
        }
        this.transitioningState = true;
        switch (this._state) {
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting:
                if (newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected &&
                    newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting &&
                    newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected) {
                    invalidTransition();
                }
                break;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected:
                if (newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting && newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected) {
                    invalidTransition();
                }
                break;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting:
                if (newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting && newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected) {
                    invalidTransition();
                }
                break;
            case _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected:
                if (newState !== _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting) {
                    invalidTransition();
                }
                break;
            default:
                throw new Error("Unknown state.");
        }
        const oldState = this._state;
        this._state = newState;
        const connectResolve = this.connectResolve;
        const connectReject = this.connectReject;
        if (oldState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting) {
            this.connectPromise = undefined;
            this.connectResolve = undefined;
            this.connectReject = undefined;
        }
        const disconnectResolve = this.disconnectResolve;
        const disconnectReject = this.disconnectReject;
        if (oldState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting) {
            this.disconnectPromise = undefined;
            this.disconnectResolve = undefined;
            this.disconnectReject = undefined;
        }
        if (this.connectTimeout) {
            clearTimeout(this.connectTimeout);
            this.connectTimeout = undefined;
        }
        this.logger.log(`Transitioned from ${oldState} to ${this._state}`);
        this._stateEventEmitter.emit(this._state);
        if (newState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected) {
            this.startSendingKeepAlives();
            if (this.onConnect) {
                try {
                    this.onConnect();
                }
                catch (e) {
                    this.logger.error(e.toString());
                    this.logger.error("Exception thrown by onConnect callback");
                    throw e;
                }
            }
        }
        if (oldState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected) {
            this.stopSendingKeepAlives();
            if (this.onDisconnect) {
                try {
                    if (error) {
                        this.onDisconnect(error);
                    }
                    else {
                        this.onDisconnect();
                    }
                }
                catch (e) {
                    this.logger.error(e.toString());
                    this.logger.error("Exception thrown by onDisconnect callback");
                    throw e;
                }
            }
        }
        if (oldState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connecting) {
            if (!connectResolve) {
                throw new Error("Connect resolve undefined.");
            }
            if (!connectReject) {
                throw new Error("Connect reject undefined.");
            }
            newState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Connected ? connectResolve() : connectReject(error || new Error("Connect aborted."));
        }
        if (oldState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnecting) {
            if (!disconnectResolve) {
                throw new Error("Disconnect resolve undefined.");
            }
            if (!disconnectReject) {
                throw new Error("Disconnect reject undefined.");
            }
            newState === _api_transport_state_js__WEBPACK_IMPORTED_MODULE_0__.TransportState.Disconnected
                ? disconnectResolve()
                : disconnectReject(error || new Error("Disconnect aborted."));
        }
        this.transitioningState = false;
    }
    clearKeepAliveTimeout() {
        if (this.keepAliveDebounceTimeout) {
            clearTimeout(this.keepAliveDebounceTimeout);
        }
        this.keepAliveDebounceTimeout = undefined;
    }
    sendKeepAlive() {
        if (this.keepAliveDebounceTimeout) {
            return Promise.resolve();
        }
        this.keepAliveDebounceTimeout = setTimeout(() => {
            this.clearKeepAliveTimeout();
        }, this.configuration.keepAliveDebounce * 1000);
        return this.send("\r\n\r\n");
    }
    startSendingKeepAlives() {
        const computeKeepAliveTimeout = (upperBound) => {
            const lowerBound = upperBound * 0.8;
            return 1000 * (Math.random() * (upperBound - lowerBound) + lowerBound);
        };
        if (this.configuration.keepAliveInterval && !this.keepAliveInterval) {
            this.keepAliveInterval = setInterval(() => {
                this.sendKeepAlive();
                this.startSendingKeepAlives();
            }, computeKeepAliveTimeout(this.configuration.keepAliveInterval));
        }
    }
    stopSendingKeepAlives() {
        if (this.keepAliveInterval) {
            clearInterval(this.keepAliveInterval);
        }
        if (this.keepAliveDebounceTimeout) {
            clearTimeout(this.keepAliveDebounceTimeout);
        }
        this.keepAliveInterval = undefined;
        this.keepAliveDebounceTimeout = undefined;
    }
}
Transport.defaultOptions = {
    server: "",
    connectionTimeout: 5,
    keepAliveInterval: 0,
    keepAliveDebounce: 10,
    traceSip: true
};


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "DigestAuthentication": () => ( DigestAuthentication)
 });
 var _md5_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(60);
 var _utils_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(21);


function MD5(s) {
    return _md5_js__WEBPACK_IMPORTED_MODULE_0__.Md5.hashStr(s);
}
/** @internal */
class DigestAuthentication {
    /**
     * @param loggerFactory
     * @param username
     * @param password
     */
    constructor(loggerFactory, ha1, username, password) {
        this.logger = loggerFactory.getLogger("sipjs.digestauthentication");
        this.username = username;
        this.password = password;
        this.ha1 = ha1;
        this.nc = 0;
        this.ncHex = "00000000";
    }
    /**
     * @param request
     * @param challenge
     * @returns
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    authenticate(request, challenge, body) {
        this.algorithm = challenge.algorithm;
        this.realm = challenge.realm;
        this.nonce = challenge.nonce;
        this.opaque = challenge.opaque;
        this.stale = challenge.stale;
        if (this.algorithm) {
            if (this.algorithm !== "MD5") {
                this.logger.warn("challenge with Digest algorithm different than 'MD5', authentication aborted");
                return false;
            }
        }
        else {
            this.algorithm = "MD5";
        }
        if (!this.realm) {
            this.logger.warn("challenge without Digest realm, authentication aborted");
            return false;
        }
        if (!this.nonce) {
            this.logger.warn("challenge without Digest nonce, authentication aborted");
            return false;
        }
        if (challenge.qop) {
            if (challenge.qop.indexOf("auth") > -1) {
                this.qop = "auth";
            }
            else if (challenge.qop.indexOf("auth-int") > -1) {
                this.qop = "auth-int";
            }
            else {
                this.logger.warn("challenge without Digest qop different than 'auth' or 'auth-int', authentication aborted");
                return false;
            }
        }
        else {
            this.qop = undefined;
        }
        this.method = request.method;
        this.uri = request.ruri;
        this.cnonce = (0,_utils_js__WEBPACK_IMPORTED_MODULE_1__.createRandomToken)(12);
        this.nc += 1;
        this.updateNcHex();
        if (this.nc === 4294967296) {
            this.nc = 1;
            this.ncHex = "00000001";
        }
        this.calculateResponse(body);
        return true;
    }
    toString() {
        const authParams = [];
        if (!this.response) {
            throw new Error("response field does not exist, cannot generate Authorization header");
        }
        authParams.push("algorithm=" + this.algorithm);
        authParams.push('username="' + this.username + '"');
        authParams.push('realm="' + this.realm + '"');
        authParams.push('nonce="' + this.nonce + '"');
        authParams.push('uri="' + this.uri + '"');
        authParams.push('response="' + this.response + '"');
        if (this.opaque) {
            authParams.push('opaque="' + this.opaque + '"');
        }
        if (this.qop) {
            authParams.push("qop=" + this.qop);
            authParams.push('cnonce="' + this.cnonce + '"');
            authParams.push("nc=" + this.ncHex);
        }
        return "Digest " + authParams.join(", ");
    }
    updateNcHex() {
        const hex = Number(this.nc).toString(16);
        this.ncHex = "00000000".substr(0, 8 - hex.length) + hex;
    }
    calculateResponse(body) {
        let ha1, ha2;
        ha1 = this.ha1;
        if (ha1 === "" || ha1 === undefined) {
            ha1 = MD5(this.username + ":" + this.realm + ":" + this.password);
        }
        if (this.qop === "auth") {
            ha2 = MD5(this.method + ":" + this.uri);
            this.response = MD5(ha1 + ":" + this.nonce + ":" + this.ncHex + ":" + this.cnonce + ":auth:" + ha2);
        }
        else if (this.qop === "auth-int") {
            ha2 = MD5(this.method + ":" + this.uri + ":" + MD5(body ? body : ""));
            this.response = MD5(ha1 + ":" + this.nonce + ":" + this.ncHex + ":" + this.cnonce + ":auth-int:" + ha2);
        }
        else if (this.qop === undefined) {
            ha2 = MD5(this.method + ":" + this.uri);
            this.response = MD5(ha1 + ":" + this.nonce + ":" + ha2);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Md5": () => ( Md5)
 });
/* eslint-disable */
/*

TypeScript Md5
==============

Based on work by
* Joseph Myers: http://www.myersdaily.org/joseph/javascript/md5-text.html
* André Cruz: https://github.com/satazor/SparkMD5
* Raymond Hill: https://github.com/gorhill/yamd5.js

Effectively a TypeScrypt re-write of Raymond Hill JS Library

The MIT License (MIT)

Copyright (C) 2014 Raymond Hill

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.



            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
                    Version 2, December 2004

 Copyright (C) 2015 André Cruz <amdfcruz@gmail.com>

 Everyone is permitted to copy and distribute verbatim or modified
 copies of this license document, and changing it is allowed as long
 as the name is changed.

            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

  0. You just DO WHAT THE FUCK YOU WANT TO.


*/
class Md5 {
    constructor() {
        this._dataLength = 0;
        this._bufferLength = 0;
        this._state = new Int32Array(4);
        this._buffer = new ArrayBuffer(68);
        this._buffer8 = new Uint8Array(this._buffer, 0, 68);
        this._buffer32 = new Uint32Array(this._buffer, 0, 17);
        this.start();
    }
    static hashStr(str, raw = false) {
        return this.onePassHasher
            .start()
            .appendStr(str)
            .end(raw);
    }
    static hashAsciiStr(str, raw = false) {
        return this.onePassHasher
            .start()
            .appendAsciiStr(str)
            .end(raw);
    }
    static _hex(x) {
        const hc = Md5.hexChars;
        const ho = Md5.hexOut;
        let n;
        let offset;
        let j;
        let i;
        for (i = 0; i < 4; i += 1) {
            offset = i * 8;
            n = x[i];
            for (j = 0; j < 8; j += 2) {
                ho[offset + 1 + j] = hc.charAt(n & 0x0F);
                n >>>= 4;
                ho[offset + 0 + j] = hc.charAt(n & 0x0F);
                n >>>= 4;
            }
        }
        return ho.join('');
    }
    static _md5cycle(x, k) {
        let a = x[0];
        let b = x[1];
        let c = x[2];
        let d = x[3];
        a += (b & c | ~b & d) + k[0] - 680876936 | 0;
        a = (a << 7 | a >>> 25) + b | 0;
        d += (a & b | ~a & c) + k[1] - 389564586 | 0;
        d = (d << 12 | d >>> 20) + a | 0;
        c += (d & a | ~d & b) + k[2] + 606105819 | 0;
        c = (c << 17 | c >>> 15) + d | 0;
        b += (c & d | ~c & a) + k[3] - 1044525330 | 0;
        b = (b << 22 | b >>> 10) + c | 0;
        a += (b & c | ~b & d) + k[4] - 176418897 | 0;
        a = (a << 7 | a >>> 25) + b | 0;
        d += (a & b | ~a & c) + k[5] + 1200080426 | 0;
        d = (d << 12 | d >>> 20) + a | 0;
        c += (d & a | ~d & b) + k[6] - 1473231341 | 0;
        c = (c << 17 | c >>> 15) + d | 0;
        b += (c & d | ~c & a) + k[7] - 45705983 | 0;
        b = (b << 22 | b >>> 10) + c | 0;
        a += (b & c | ~b & d) + k[8] + 1770035416 | 0;
        a = (a << 7 | a >>> 25) + b | 0;
        d += (a & b | ~a & c) + k[9] - 1958414417 | 0;
        d = (d << 12 | d >>> 20) + a | 0;
        c += (d & a | ~d & b) + k[10] - 42063 | 0;
        c = (c << 17 | c >>> 15) + d | 0;
        b += (c & d | ~c & a) + k[11] - 1990404162 | 0;
        b = (b << 22 | b >>> 10) + c | 0;
        a += (b & c | ~b & d) + k[12] + 1804603682 | 0;
        a = (a << 7 | a >>> 25) + b | 0;
        d += (a & b | ~a & c) + k[13] - 40341101 | 0;
        d = (d << 12 | d >>> 20) + a | 0;
        c += (d & a | ~d & b) + k[14] - 1502002290 | 0;
        c = (c << 17 | c >>> 15) + d | 0;
        b += (c & d | ~c & a) + k[15] + 1236535329 | 0;
        b = (b << 22 | b >>> 10) + c | 0;
        a += (b & d | c & ~d) + k[1] - 165796510 | 0;
        a = (a << 5 | a >>> 27) + b | 0;
        d += (a & c | b & ~c) + k[6] - 1069501632 | 0;
        d = (d << 9 | d >>> 23) + a | 0;
        c += (d & b | a & ~b) + k[11] + 643717713 | 0;
        c = (c << 14 | c >>> 18) + d | 0;
        b += (c & a | d & ~a) + k[0] - 373897302 | 0;
        b = (b << 20 | b >>> 12) + c | 0;
        a += (b & d | c & ~d) + k[5] - 701558691 | 0;
        a = (a << 5 | a >>> 27) + b | 0;
        d += (a & c | b & ~c) + k[10] + 38016083 | 0;
        d = (d << 9 | d >>> 23) + a | 0;
        c += (d & b | a & ~b) + k[15] - 660478335 | 0;
        c = (c << 14 | c >>> 18) + d | 0;
        b += (c & a | d & ~a) + k[4] - 405537848 | 0;
        b = (b << 20 | b >>> 12) + c | 0;
        a += (b & d | c & ~d) + k[9] + 568446438 | 0;
        a = (a << 5 | a >>> 27) + b | 0;
        d += (a & c | b & ~c) + k[14] - 1019803690 | 0;
        d = (d << 9 | d >>> 23) + a | 0;
        c += (d & b | a & ~b) + k[3] - 187363961 | 0;
        c = (c << 14 | c >>> 18) + d | 0;
        b += (c & a | d & ~a) + k[8] + 1163531501 | 0;
        b = (b << 20 | b >>> 12) + c | 0;
        a += (b & d | c & ~d) + k[13] - 1444681467 | 0;
        a = (a << 5 | a >>> 27) + b | 0;
        d += (a & c | b & ~c) + k[2] - 51403784 | 0;
        d = (d << 9 | d >>> 23) + a | 0;
        c += (d & b | a & ~b) + k[7] + 1735328473 | 0;
        c = (c << 14 | c >>> 18) + d | 0;
        b += (c & a | d & ~a) + k[12] - 1926607734 | 0;
        b = (b << 20 | b >>> 12) + c | 0;
        a += (b ^ c ^ d) + k[5] - 378558 | 0;
        a = (a << 4 | a >>> 28) + b | 0;
        d += (a ^ b ^ c) + k[8] - 2022574463 | 0;
        d = (d << 11 | d >>> 21) + a | 0;
        c += (d ^ a ^ b) + k[11] + 1839030562 | 0;
        c = (c << 16 | c >>> 16) + d | 0;
        b += (c ^ d ^ a) + k[14] - 35309556 | 0;
        b = (b << 23 | b >>> 9) + c | 0;
        a += (b ^ c ^ d) + k[1] - 1530992060 | 0;
        a = (a << 4 | a >>> 28) + b | 0;
        d += (a ^ b ^ c) + k[4] + 1272893353 | 0;
        d = (d << 11 | d >>> 21) + a | 0;
        c += (d ^ a ^ b) + k[7] - 155497632 | 0;
        c = (c << 16 | c >>> 16) + d | 0;
        b += (c ^ d ^ a) + k[10] - 1094730640 | 0;
        b = (b << 23 | b >>> 9) + c | 0;
        a += (b ^ c ^ d) + k[13] + 681279174 | 0;
        a = (a << 4 | a >>> 28) + b | 0;
        d += (a ^ b ^ c) + k[0] - 358537222 | 0;
        d = (d << 11 | d >>> 21) + a | 0;
        c += (d ^ a ^ b) + k[3] - 722521979 | 0;
        c = (c << 16 | c >>> 16) + d | 0;
        b += (c ^ d ^ a) + k[6] + 76029189 | 0;
        b = (b << 23 | b >>> 9) + c | 0;
        a += (b ^ c ^ d) + k[9] - 640364487 | 0;
        a = (a << 4 | a >>> 28) + b | 0;
        d += (a ^ b ^ c) + k[12] - 421815835 | 0;
        d = (d << 11 | d >>> 21) + a | 0;
        c += (d ^ a ^ b) + k[15] + 530742520 | 0;
        c = (c << 16 | c >>> 16) + d | 0;
        b += (c ^ d ^ a) + k[2] - 995338651 | 0;
        b = (b << 23 | b >>> 9) + c | 0;
        a += (c ^ (b | ~d)) + k[0] - 198630844 | 0;
        a = (a << 6 | a >>> 26) + b | 0;
        d += (b ^ (a | ~c)) + k[7] + 1126891415 | 0;
        d = (d << 10 | d >>> 22) + a | 0;
        c += (a ^ (d | ~b)) + k[14] - 1416354905 | 0;
        c = (c << 15 | c >>> 17) + d | 0;
        b += (d ^ (c | ~a)) + k[5] - 57434055 | 0;
        b = (b << 21 | b >>> 11) + c | 0;
        a += (c ^ (b | ~d)) + k[12] + 1700485571 | 0;
        a = (a << 6 | a >>> 26) + b | 0;
        d += (b ^ (a | ~c)) + k[3] - 1894986606 | 0;
        d = (d << 10 | d >>> 22) + a | 0;
        c += (a ^ (d | ~b)) + k[10] - 1051523 | 0;
        c = (c << 15 | c >>> 17) + d | 0;
        b += (d ^ (c | ~a)) + k[1] - 2054922799 | 0;
        b = (b << 21 | b >>> 11) + c | 0;
        a += (c ^ (b | ~d)) + k[8] + 1873313359 | 0;
        a = (a << 6 | a >>> 26) + b | 0;
        d += (b ^ (a | ~c)) + k[15] - 30611744 | 0;
        d = (d << 10 | d >>> 22) + a | 0;
        c += (a ^ (d | ~b)) + k[6] - 1560198380 | 0;
        c = (c << 15 | c >>> 17) + d | 0;
        b += (d ^ (c | ~a)) + k[13] + 1309151649 | 0;
        b = (b << 21 | b >>> 11) + c | 0;
        a += (c ^ (b | ~d)) + k[4] - 145523070 | 0;
        a = (a << 6 | a >>> 26) + b | 0;
        d += (b ^ (a | ~c)) + k[11] - 1120210379 | 0;
        d = (d << 10 | d >>> 22) + a | 0;
        c += (a ^ (d | ~b)) + k[2] + 718787259 | 0;
        c = (c << 15 | c >>> 17) + d | 0;
        b += (d ^ (c | ~a)) + k[9] - 343485551 | 0;
        b = (b << 21 | b >>> 11) + c | 0;
        x[0] = a + x[0] | 0;
        x[1] = b + x[1] | 0;
        x[2] = c + x[2] | 0;
        x[3] = d + x[3] | 0;
    }
    start() {
        this._dataLength = 0;
        this._bufferLength = 0;
        this._state.set(Md5.stateIdentity);
        return this;
    }
    appendStr(str) {
        const buf8 = this._buffer8;
        const buf32 = this._buffer32;
        let bufLen = this._bufferLength;
        let code;
        let i;
        for (i = 0; i < str.length; i += 1) {
            code = str.charCodeAt(i);
            if (code < 128) {
                buf8[bufLen++] = code;
            }
            else if (code < 0x800) {
                buf8[bufLen++] = (code >>> 6) + 0xC0;
                buf8[bufLen++] = code & 0x3F | 0x80;
            }
            else if (code < 0xD800 || code > 0xDBFF) {
                buf8[bufLen++] = (code >>> 12) + 0xE0;
                buf8[bufLen++] = (code >>> 6 & 0x3F) | 0x80;
                buf8[bufLen++] = (code & 0x3F) | 0x80;
            }
            else {
                code = ((code - 0xD800) * 0x400) + (str.charCodeAt(++i) - 0xDC00) + 0x10000;
                if (code > 0x10FFFF) {
                    throw new Error('Unicode standard supports code points up to U+10FFFF');
                }
                buf8[bufLen++] = (code >>> 18) + 0xF0;
                buf8[bufLen++] = (code >>> 12 & 0x3F) | 0x80;
                buf8[bufLen++] = (code >>> 6 & 0x3F) | 0x80;
                buf8[bufLen++] = (code & 0x3F) | 0x80;
            }
            if (bufLen >= 64) {
                this._dataLength += 64;
                Md5._md5cycle(this._state, buf32);
                bufLen -= 64;
                buf32[0] = buf32[16];
            }
        }
        this._bufferLength = bufLen;
        return this;
    }
    appendAsciiStr(str) {
        const buf8 = this._buffer8;
        const buf32 = this._buffer32;
        let bufLen = this._bufferLength;
        let i;
        let j = 0;
        for (;;) {
            i = Math.min(str.length - j, 64 - bufLen);
            while (i--) {
                buf8[bufLen++] = str.charCodeAt(j++);
            }
            if (bufLen < 64) {
                break;
            }
            this._dataLength += 64;
            Md5._md5cycle(this._state, buf32);
            bufLen = 0;
        }
        this._bufferLength = bufLen;
        return this;
    }
    appendByteArray(input) {
        const buf8 = this._buffer8;
        const buf32 = this._buffer32;
        let bufLen = this._bufferLength;
        let i;
        let j = 0;
        for (;;) {
            i = Math.min(input.length - j, 64 - bufLen);
            while (i--) {
                buf8[bufLen++] = input[j++];
            }
            if (bufLen < 64) {
                break;
            }
            this._dataLength += 64;
            Md5._md5cycle(this._state, buf32);
            bufLen = 0;
        }
        this._bufferLength = bufLen;
        return this;
    }
    getState() {
        const self = this;
        const s = self._state;
        return {
            buffer: String.fromCharCode.apply(null, self._buffer8),
            buflen: self._bufferLength,
            length: self._dataLength,
            state: [s[0], s[1], s[2], s[3]]
        };
    }
    setState(state) {
        const buf = state.buffer;
        const x = state.state;
        const s = this._state;
        let i;
        this._dataLength = state.length;
        this._bufferLength = state.buflen;
        s[0] = x[0];
        s[1] = x[1];
        s[2] = x[2];
        s[3] = x[3];
        for (i = 0; i < buf.length; i += 1) {
            this._buffer8[i] = buf.charCodeAt(i);
        }
    }
    end(raw = false) {
        const bufLen = this._bufferLength;
        const buf8 = this._buffer8;
        const buf32 = this._buffer32;
        const i = (bufLen >> 2) + 1;
        let dataBitsLen;
        this._dataLength += bufLen;
        buf8[bufLen] = 0x80;
        buf8[bufLen + 1] = buf8[bufLen + 2] = buf8[bufLen + 3] = 0;
        buf32.set(Md5.buffer32Identity.subarray(i), i);
        if (bufLen > 55) {
            Md5._md5cycle(this._state, buf32);
            buf32.set(Md5.buffer32Identity);
        }
        dataBitsLen = this._dataLength * 8;
        if (dataBitsLen <= 0xFFFFFFFF) {
            buf32[14] = dataBitsLen;
        }
        else {
            const matches = dataBitsLen.toString(16).match(/(.*?)(.{0,8})$/);
            if (matches === null) {
                return;
            }
            const lo = parseInt(matches[2], 16);
            const hi = parseInt(matches[1], 16) || 0;
            buf32[14] = lo;
            buf32[15] = hi;
        }
        Md5._md5cycle(this._state, buf32);
        return raw ? this._state : Md5._hex(this._state);
    }
}
Md5.stateIdentity = new Int32Array([1732584193, -271733879, -1732584194, 271733878]);
Md5.buffer32Identity = new Int32Array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
Md5.hexChars = '0123456789abcdef';
Md5.hexOut = [];
Md5.onePassHasher = new Md5();
if (Md5.hashStr('hello') !== '5d41402abc4b2a76b9719d911017c592') {
    console.error('Md5 self test failed.');
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "UserAgentCore": () => ( UserAgentCore)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(30);
 var _messages_outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(28);
 var _messages_outgoing_response_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(84);
 var _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(72);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(65);
 var _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(64);
 var _user_agents_invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(62);
 var _user_agents_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(96);
 var _user_agents_message_user_agent_client_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(77);
 var _user_agents_message_user_agent_server_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(87);
 var _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(88);
 var _user_agents_publish_user_agent_client_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(91);
 var _user_agents_refer_user_agent_server_js__WEBPACK_IMPORTED_MODULE_16__ = __webpack_require__(90);
 var _user_agents_register_user_agent_client_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(92);
 var _user_agents_register_user_agent_server_js__WEBPACK_IMPORTED_MODULE_17__ = __webpack_require__(97);
 var _user_agents_subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(93);
 var _user_agents_subscribe_user_agent_server_js__WEBPACK_IMPORTED_MODULE_18__ = __webpack_require__(98);
 var _user_agents_user_agent_client_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(63);
 var _allowed_methods_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(29);



















const acceptedBodyTypes = ["application/sdp", "application/dtmf-relay"];
/**
 * @remarks
 * @public
 */
class UserAgentCore {
    /**
     * @param configuration
     * @param delegate
     */
    constructor(configuration, delegate = {}) {
        this.userAgentClients = new Map();
        this.userAgentServers = new Map();
        this.configuration = configuration;
        this.delegate = delegate;
        this.dialogs = new Map();
        this.subscribers = new Map();
        this.logger = configuration.loggerFactory.getLogger("sip.user-agent-core");
    }
    dispose() {
        this.reset();
    }
    reset() {
        this.dialogs.forEach((dialog) => dialog.dispose());
        this.dialogs.clear();
        this.subscribers.forEach((subscriber) => subscriber.dispose());
        this.subscribers.clear();
        this.userAgentClients.forEach((uac) => uac.dispose());
        this.userAgentClients.clear();
        this.userAgentServers.forEach((uac) => uac.dispose());
        this.userAgentServers.clear();
    }
    get loggerFactory() {
        return this.configuration.loggerFactory;
    }
    get transport() {
        const transport = this.configuration.transportAccessor();
        if (!transport) {
            throw new Error("Transport undefined.");
        }
        return transport;
    }
    /**
     * @param request
     * @param delegate
     */
    invite(request, delegate) {
        return new _user_agents_invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.InviteUserAgentClient(this, request, delegate);
    }
    /**
     * @param request
     * @param delegate
     */
    message(request, delegate) {
        return new _user_agents_message_user_agent_client_js__WEBPACK_IMPORTED_MODULE_1__.MessageUserAgentClient(this, request, delegate);
    }
    /**
     * @param request
     * @param delegate
     */
    publish(request, delegate) {
        return new _user_agents_publish_user_agent_client_js__WEBPACK_IMPORTED_MODULE_2__.PublishUserAgentClient(this, request, delegate);
    }
    /**
     * @param request
     * @param delegate
     */
    register(request, delegate) {
        return new _user_agents_register_user_agent_client_js__WEBPACK_IMPORTED_MODULE_3__.RegisterUserAgentClient(this, request, delegate);
    }
    /**
     * @param request
     * @param delegate
     */
    subscribe(request, delegate) {
        return new _user_agents_subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_4__.SubscribeUserAgentClient(this, request, delegate);
    }
    /**
     * @param request
     * @param delegate
     */
    request(request, delegate) {
        return new _user_agents_user_agent_client_js__WEBPACK_IMPORTED_MODULE_5__.UserAgentClient(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_6__.NonInviteClientTransaction, this, request, delegate);
    }
    /**
     * @param method
     * @param requestURI
     * @param fromURI
     * @param toURI
     * @param options
     * @param extraHeaders
     * @param body
     */
    makeOutgoingRequestMessage(method, requestURI, fromURI, toURI, options, extraHeaders, body) {
        const callIdPrefix = this.configuration.sipjsId;
        const fromDisplayName = this.configuration.displayName;
        const forceRport = this.configuration.viaForceRport;
        const hackViaTcp = this.configuration.hackViaTcp;
        const optionTags = this.configuration.supportedOptionTags.slice();
        if (method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.REGISTER) {
            optionTags.push("path", "gruu");
        }
        if (method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.INVITE && (this.configuration.contact.pubGruu || this.configuration.contact.tempGruu)) {
            optionTags.push("gruu");
        }
        const routeSet = this.configuration.routeSet;
        const userAgentString = this.configuration.userAgentHeaderFieldValue;
        const viaHost = this.configuration.viaHost;
        const defaultOptions = {
            callIdPrefix,
            forceRport,
            fromDisplayName,
            hackViaTcp,
            optionTags,
            routeSet,
            userAgentString,
            viaHost
        };
        const requestOptions = Object.assign(Object.assign({}, defaultOptions), options);
        return new _messages_outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_8__.OutgoingRequestMessage(method, requestURI, fromURI, toURI, requestOptions, extraHeaders, body);
    }
    /** @param message */
    receiveIncomingRequestFromTransport(message) {
        this.receiveRequestFromTransport(message);
    }
    /** @param message */
    receiveIncomingResponseFromTransport(message) {
        this.receiveResponseFromTransport(message);
    }
    /**
     * @param message
     * @param statusCode
     */
    replyStateless(message, options) {
        const userAgent = this.configuration.userAgentHeaderFieldValue;
        const supported = this.configuration.supportedOptionTagsResponse;
        options = Object.assign(Object.assign({}, options), { userAgent, supported });
        const response = (0,_messages_outgoing_response_js__WEBPACK_IMPORTED_MODULE_9__.constructOutgoingResponse)(message, options);
        this.transport.send(response.message).catch((error) => {
            if (error instanceof Error) {
                this.logger.error(error.message);
            }
            this.logger.error(`Transport error occurred sending stateless reply to ${message.method} request.`);
        });
        return response;
    }
    /** @param message */
    receiveRequestFromTransport(message) {
        const transactionId = message.viaBranch;
        const uas = this.userAgentServers.get(transactionId);
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.ACK) {
            if (uas && uas.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_10__.TransactionState.Accepted) {
                if (uas instanceof _user_agents_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_11__.InviteUserAgentServer) {
                    this.logger.warn(`Discarding out of dialog ACK after 2xx response sent on transaction ${transactionId}.`);
                    return;
                }
            }
        }
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.CANCEL) {
            if (uas) {
                this.replyStateless(message, { statusCode: 200 });
                if (uas.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_12__.InviteServerTransaction &&
                    uas.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_10__.TransactionState.Proceeding) {
                    if (uas instanceof _user_agents_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_11__.InviteUserAgentServer) {
                        uas.receiveCancel(message);
                    }
                }
            }
            else {
                this.replyStateless(message, { statusCode: 481 });
            }
            return;
        }
        if (uas) {
            uas.transaction.receiveRequest(message);
            return;
        }
        this.receiveRequest(message);
        return;
    }
    /** @param message */
    receiveRequest(message) {
        if (!_allowed_methods_js__WEBPACK_IMPORTED_MODULE_13__.AllowedMethods.includes(message.method)) {
            const allowHeader = "Allow: " + _allowed_methods_js__WEBPACK_IMPORTED_MODULE_13__.AllowedMethods.toString();
            this.replyStateless(message, {
                statusCode: 405,
                extraHeaders: [allowHeader]
            });
            return;
        }
        if (!message.ruri) {
            throw new Error("Request-URI undefined.");
        }
        if (message.ruri.scheme !== "sip") {
            this.replyStateless(message, { statusCode: 416 });
            return;
        }
        const ruri = message.ruri;
        const ruriMatches = (uri) => {
            return !!uri && uri.user === ruri.user;
        };
        if (!ruriMatches(this.configuration.aor) &&
            !(ruriMatches(this.configuration.contact.uri) ||
                ruriMatches(this.configuration.contact.pubGruu) ||
                ruriMatches(this.configuration.contact.tempGruu))) {
            this.logger.warn("Request-URI does not point to us.");
            if (message.method !== _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.ACK) {
                this.replyStateless(message, { statusCode: 404 });
            }
            return;
        }
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.INVITE) {
            if (!message.hasHeader("Contact")) {
                this.replyStateless(message, {
                    statusCode: 400,
                    reasonPhrase: "Missing Contact Header"
                });
                return;
            }
        }
        if (!message.toTag) {
            const transactionId = message.viaBranch;
            if (!this.userAgentServers.has(transactionId)) {
                const mergedRequest = Array.from(this.userAgentServers.values()).some((uas) => uas.transaction.request.fromTag === message.fromTag &&
                    uas.transaction.request.callId === message.callId &&
                    uas.transaction.request.cseq === message.cseq);
                if (mergedRequest) {
                    this.replyStateless(message, { statusCode: 482 });
                    return;
                }
            }
        }
        if (message.toTag) {
            this.receiveInsideDialogRequest(message);
        }
        else {
            this.receiveOutsideDialogRequest(message);
        }
        return;
    }
    /** @param message */
    receiveInsideDialogRequest(message) {
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.NOTIFY) {
            const event = message.parseHeader("Event");
            if (!event || !event.event) {
                this.replyStateless(message, { statusCode: 489 });
                return;
            }
            const subscriberId = message.callId + message.toTag + event.event;
            const subscriber = this.subscribers.get(subscriberId);
            if (subscriber) {
                const uas = new _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_14__.NotifyUserAgentServer(this, message);
                subscriber.onNotify(uas);
                return;
            }
        }
        const dialogId = message.callId + message.toTag + message.fromTag;
        const dialog = this.dialogs.get(dialogId);
        if (dialog) {
            if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.OPTIONS) {
                const allowHeader = "Allow: " + _allowed_methods_js__WEBPACK_IMPORTED_MODULE_13__.AllowedMethods.toString();
                const acceptHeader = "Accept: " + acceptedBodyTypes.toString();
                this.replyStateless(message, {
                    statusCode: 200,
                    extraHeaders: [allowHeader, acceptHeader]
                });
                return;
            }
            dialog.receiveRequest(message);
            return;
        }
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.ACK) {
            return;
        }
        this.replyStateless(message, { statusCode: 481 });
        return;
    }
    /** @param message */
    receiveOutsideDialogRequest(message) {
        switch (message.method) {
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.ACK:
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.BYE:
                this.replyStateless(message, { statusCode: 481 });
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.CANCEL:
                throw new Error(`Unexpected out of dialog request method ${message.method}.`);
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.INFO:
                this.replyStateless(message, { statusCode: 405 });
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.INVITE:
                {
                    const uas = new _user_agents_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_11__.InviteUserAgentServer(this, message);
                    this.delegate.onInvite ? this.delegate.onInvite(uas) : uas.reject();
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.MESSAGE:
                {
                    const uas = new _user_agents_message_user_agent_server_js__WEBPACK_IMPORTED_MODULE_15__.MessageUserAgentServer(this, message);
                    this.delegate.onMessage ? this.delegate.onMessage(uas) : uas.accept();
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.NOTIFY:
                {
                    const uas = new _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_14__.NotifyUserAgentServer(this, message);
                    this.delegate.onNotify ? this.delegate.onNotify(uas) : uas.reject({ statusCode: 405 });
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.OPTIONS:
                {
                    const allowHeader = "Allow: " + _allowed_methods_js__WEBPACK_IMPORTED_MODULE_13__.AllowedMethods.toString();
                    const acceptHeader = "Accept: " + acceptedBodyTypes.toString();
                    this.replyStateless(message, {
                        statusCode: 200,
                        extraHeaders: [allowHeader, acceptHeader]
                    });
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.REFER:
                {
                    const uas = new _user_agents_refer_user_agent_server_js__WEBPACK_IMPORTED_MODULE_16__.ReferUserAgentServer(this, message);
                    this.delegate.onRefer ? this.delegate.onRefer(uas) : uas.reject({ statusCode: 405 });
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.REGISTER:
                {
                    const uas = new _user_agents_register_user_agent_server_js__WEBPACK_IMPORTED_MODULE_17__.RegisterUserAgentServer(this, message);
                    this.delegate.onRegister ? this.delegate.onRegister(uas) : uas.reject({ statusCode: 405 });
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_7__.C.SUBSCRIBE:
                {
                    const uas = new _user_agents_subscribe_user_agent_server_js__WEBPACK_IMPORTED_MODULE_18__.SubscribeUserAgentServer(this, message);
                    this.delegate.onSubscribe ? this.delegate.onSubscribe(uas) : uas.reject({ statusCode: 480 });
                }
                break;
            default:
                throw new Error(`Unexpected out of dialog request method ${message.method}.`);
        }
        return;
    }
    /** @param message */
    receiveResponseFromTransport(message) {
        if (message.getHeaders("via").length > 1) {
            this.logger.warn("More than one Via header field present in the response, dropping");
            return;
        }
        const userAgentClientId = message.viaBranch + message.method;
        const userAgentClient = this.userAgentClients.get(userAgentClientId);
        if (userAgentClient) {
            userAgentClient.transaction.receiveResponse(message);
        }
        else {
            this.logger.warn(`Discarding unmatched ${message.statusCode} response to ${message.method} ${userAgentClientId}.`);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "InviteUserAgentClient": () => ( InviteUserAgentClient)
 });
 var _dialogs_dialog_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(70);
 var _dialogs_session_dialog_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(71);
 var _session_session_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(31);
 var _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(69);
 var _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(64);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);






/**
 * @remarks
 * @public
 */
class InviteUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(core, message, delegate) {
        super(_transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteClientTransaction, core, message, delegate);
        this.confirmedDialogAcks = new Map();
        this.confirmedDialogs = new Map();
        this.earlyDialogs = new Map();
        this.delegate = delegate;
    }
    dispose() {
        this.earlyDialogs.forEach((earlyDialog) => earlyDialog.dispose());
        this.earlyDialogs.clear();
        super.dispose();
    }
    /** @param error */
    onTransportError(error) {
        if (this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_2__.TransactionState.Calling) {
            return super.onTransportError(error);
        }
        this.logger.error(error.message);
        this.logger.error("User agent client request transport error while sending ACK.");
    }
    /** @param incomingResponse */
    receiveResponse(message) {
        if (!this.authenticationGuard(message)) {
            return;
        }
        const statusCode = message.statusCode ? message.statusCode.toString() : "";
        if (!statusCode) {
            throw new Error("Response status code undefined.");
        }
        switch (true) {
            case /^100$/.test(statusCode):
                if (this.delegate && this.delegate.onTrying) {
                    this.delegate.onTrying({ message });
                }
                return;
            case /^1[0-9]{2}$/.test(statusCode):
                {
                    if (!message.toTag) {
                        this.logger.warn("Non-100 1xx INVITE response received without a to tag, dropping.");
                        return;
                    }
                    const contact = message.parseHeader("contact");
                    if (!contact) {
                        this.logger.error("Non-100 1xx INVITE response received without a Contact header field, dropping.");
                        return;
                    }
                    const dialogState = _dialogs_dialog_js__WEBPACK_IMPORTED_MODULE_3__.Dialog.initialDialogStateForUserAgentClient(this.message, message);
                    let earlyDialog = this.earlyDialogs.get(dialogState.id);
                    if (!earlyDialog) {
                        const transaction = this.transaction;
                        if (!(transaction instanceof _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteClientTransaction)) {
                            throw new Error("Transaction not instance of InviteClientTransaction.");
                        }
                        earlyDialog = new _dialogs_session_dialog_js__WEBPACK_IMPORTED_MODULE_4__.SessionDialog(transaction, this.core, dialogState);
                        this.earlyDialogs.set(earlyDialog.id, earlyDialog);
                    }
                    if (!earlyDialog.reliableSequenceGuard(message)) {
                        this.logger.warn("1xx INVITE reliable response received out of order or is a retransmission, dropping.");
                        return;
                    }
                    if (earlyDialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Initial ||
                        earlyDialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.HaveLocalOffer) {
                        earlyDialog.signalingStateTransition(message);
                    }
                    const session = earlyDialog;
                    if (this.delegate && this.delegate.onProgress) {
                        this.delegate.onProgress({
                            message,
                            session,
                            prack: (options) => {
                                const outgoingPrackRequest = session.prack(undefined, options);
                                return outgoingPrackRequest;
                            }
                        });
                    }
                }
                return;
            case /^2[0-9]{2}$/.test(statusCode):
                {
                    if (!message.toTag) {
                        this.logger.error("2xx INVITE response received without a to tag, dropping.");
                        return;
                    }
                    const contact = message.parseHeader("contact");
                    if (!contact) {
                        this.logger.error("2xx INVITE response received without a Contact header field, dropping.");
                        return;
                    }
                    const dialogState = _dialogs_dialog_js__WEBPACK_IMPORTED_MODULE_3__.Dialog.initialDialogStateForUserAgentClient(this.message, message);
                    let dialog = this.confirmedDialogs.get(dialogState.id);
                    if (dialog) {
                        const outgoingAckRequest = this.confirmedDialogAcks.get(dialogState.id);
                        if (outgoingAckRequest) {
                            const transaction = this.transaction;
                            if (!(transaction instanceof _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteClientTransaction)) {
                                throw new Error("Client transaction not instance of InviteClientTransaction.");
                            }
                            transaction.ackResponse(outgoingAckRequest.message);
                        }
                        else {
                        }
                        return;
                    }
                    dialog = this.earlyDialogs.get(dialogState.id);
                    if (dialog) {
                        dialog.confirm();
                        dialog.recomputeRouteSet(message);
                        this.earlyDialogs.delete(dialog.id);
                        this.confirmedDialogs.set(dialog.id, dialog);
                    }
                    else {
                        const transaction = this.transaction;
                        if (!(transaction instanceof _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteClientTransaction)) {
                            throw new Error("Transaction not instance of InviteClientTransaction.");
                        }
                        dialog = new _dialogs_session_dialog_js__WEBPACK_IMPORTED_MODULE_4__.SessionDialog(transaction, this.core, dialogState);
                        this.confirmedDialogs.set(dialog.id, dialog);
                    }
                    if (dialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.Initial ||
                        dialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_5__.SignalingState.HaveLocalOffer) {
                        dialog.signalingStateTransition(message);
                    }
                    const session = dialog;
                    if (this.delegate && this.delegate.onAccept) {
                        this.delegate.onAccept({
                            message,
                            session,
                            ack: (options) => {
                                const outgoingAckRequest = session.ack(options);
                                this.confirmedDialogAcks.set(session.id, outgoingAckRequest);
                                return outgoingAckRequest;
                            }
                        });
                    }
                    else {
                        const outgoingAckRequest = session.ack();
                        this.confirmedDialogAcks.set(session.id, outgoingAckRequest);
                    }
                }
                return;
            case /^3[0-9]{2}$/.test(statusCode):
                this.earlyDialogs.forEach((earlyDialog) => earlyDialog.dispose());
                this.earlyDialogs.clear();
                if (this.delegate && this.delegate.onRedirect) {
                    this.delegate.onRedirect({ message });
                }
                return;
            case /^[4-6][0-9]{2}$/.test(statusCode):
                this.earlyDialogs.forEach((earlyDialog) => earlyDialog.dispose());
                this.earlyDialogs.clear();
                if (this.delegate && this.delegate.onReject) {
                    this.delegate.onReject({ message });
                }
                return;
            default:
                throw new Error(`Invalid status code ${statusCode}`);
        }
        throw new Error(`Executing what should be an unreachable code path receiving ${statusCode} response.`);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "UserAgentClient": () => ( UserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(30);
 var _messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(27);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(64);




/**
 * @remarks
 * @public
 */
class UserAgentClient {
    constructor(transactionConstructor, core, message, delegate) {
        this.transactionConstructor = transactionConstructor;
        this.core = core;
        this.message = message;
        this.delegate = delegate;
        this.challenged = false;
        this.stale = false;
        this.logger = this.loggerFactory.getLogger("sip.user-agent-client");
        this.init();
    }
    dispose() {
        this.transaction.dispose();
    }
    get loggerFactory() {
        return this.core.loggerFactory;
    }
    get transaction() {
        if (!this._transaction) {
            throw new Error("Transaction undefined.");
        }
        return this._transaction;
    }
    /** @param options */
    cancel(reason, options = {}) {
        if (!this.transaction) {
            throw new Error("Transaction undefined.");
        }
        if (!this.message.to) {
            throw new Error("To undefined.");
        }
        if (!this.message.from) {
            throw new Error("From undefined.");
        }
        const message = this.core.makeOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_0__.C.CANCEL, this.message.ruri, this.message.from.uri, this.message.to.uri, {
            toTag: this.message.toTag,
            fromTag: this.message.fromTag,
            callId: this.message.callId,
            cseq: this.message.cseq
        }, options.extraHeaders);
        message.branch = this.message.branch;
        if (this.message.headers.Route) {
            message.headers.Route = this.message.headers.Route;
        }
        if (reason) {
            message.setHeader("Reason", reason);
        }
        if (this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
            new UserAgentClient(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, this.core, message);
        }
        else {
            this.transaction.addStateChangeListener(() => {
                if (this.transaction && this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
                    new UserAgentClient(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, this.core, message);
                }
            }, { once: true });
        }
        return message;
    }
    /**
     * @param response
     * @param dialog
     * @returns
     */
    authenticationGuard(message, dialog) {
        const statusCode = message.statusCode;
        if (!statusCode) {
            throw new Error("Response status code undefined.");
        }
        if (statusCode !== 401 && statusCode !== 407) {
            return true;
        }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let challenge;
        let authorizationHeaderName;
        if (statusCode === 401) {
            challenge = message.parseHeader("www-authenticate");
            authorizationHeaderName = "authorization";
        }
        else {
            challenge = message.parseHeader("proxy-authenticate");
            authorizationHeaderName = "proxy-authorization";
        }
        if (!challenge) {
            this.logger.warn(statusCode + " with wrong or missing challenge, cannot authenticate");
            return true;
        }
        if (this.challenged && (this.stale || challenge.stale !== true)) {
            this.logger.warn(statusCode + " apparently in authentication loop, cannot authenticate");
            return true;
        }
        if (!this.credentials) {
            this.credentials = this.core.configuration.authenticationFactory();
            if (!this.credentials) {
                this.logger.warn("Unable to obtain credentials, cannot authenticate");
                return true;
            }
        }
        if (!this.credentials.authenticate(this.message, challenge)) {
            return true;
        }
        this.challenged = true;
        if (challenge.stale) {
            this.stale = true;
        }
        let cseq = (this.message.cseq += 1);
        if (dialog && dialog.localSequenceNumber) {
            dialog.incrementLocalSequenceNumber();
            cseq = this.message.cseq = dialog.localSequenceNumber;
        }
        this.message.setHeader("cseq", cseq + " " + this.message.method);
        this.message.setHeader(authorizationHeaderName, this.credentials.toString());
        this.init();
        return false;
    }
    onRequestTimeout() {
        this.logger.warn("User agent client request timed out. Generating internal 408 Request Timeout.");
        const message = new _messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_3__.IncomingResponseMessage();
        message.statusCode = 408;
        message.reasonPhrase = "Request Timeout";
        this.receiveResponse(message);
        return;
    }
    /** @param error */
    onTransportError(error) {
        this.logger.error(error.message);
        this.logger.error("User agent client request transport error. Generating internal 503 Service Unavailable.");
        const message = new _messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_3__.IncomingResponseMessage();
        message.statusCode = 503;
        message.reasonPhrase = "Service Unavailable";
        this.receiveResponse(message);
    }
    /** @param message */
    receiveResponse(message) {
        if (!this.authenticationGuard(message)) {
            return;
        }
        const statusCode = message.statusCode ? message.statusCode.toString() : "";
        if (!statusCode) {
            throw new Error("Response status code undefined.");
        }
        switch (true) {
            case /^100$/.test(statusCode):
                if (this.delegate && this.delegate.onTrying) {
                    this.delegate.onTrying({ message });
                }
                break;
            case /^1[0-9]{2}$/.test(statusCode):
                if (this.delegate && this.delegate.onProgress) {
                    this.delegate.onProgress({ message });
                }
                break;
            case /^2[0-9]{2}$/.test(statusCode):
                if (this.delegate && this.delegate.onAccept) {
                    this.delegate.onAccept({ message });
                }
                break;
            case /^3[0-9]{2}$/.test(statusCode):
                if (this.delegate && this.delegate.onRedirect) {
                    this.delegate.onRedirect({ message });
                }
                break;
            case /^[4-6][0-9]{2}$/.test(statusCode):
                if (this.delegate && this.delegate.onReject) {
                    this.delegate.onReject({ message });
                }
                break;
            default:
                throw new Error(`Invalid status code ${statusCode}`);
        }
    }
    init() {
        const user = {
            loggerFactory: this.loggerFactory,
            onRequestTimeout: () => this.onRequestTimeout(),
            onStateChange: (newState) => {
                if (newState === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated) {
                    // eslint-disable-next-line @typescript-eslint/no-use-before-define
                    this.core.userAgentClients.delete(userAgentClientId);
                    // eslint-disable-next-line @typescript-eslint/no-use-before-define
                    if (transaction === this._transaction) {
                        this.dispose();
                    }
                }
            },
            onTransportError: (error) => this.onTransportError(error),
            receiveResponse: (message) => this.receiveResponse(message)
        };
        const transaction = new this.transactionConstructor(this.message, this.core.transport, user);
        this._transaction = transaction;
        const userAgentClientId = transaction.id + transaction.request.method;
        this.core.userAgentClients.set(userAgentClientId, this);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "TransactionState": () => ( TransactionState)
 });
/** @public */
var TransactionState;
(function (TransactionState) {
    TransactionState["Accepted"] = "Accepted";
    TransactionState["Calling"] = "Calling";
    TransactionState["Completed"] = "Completed";
    TransactionState["Confirmed"] = "Confirmed";
    TransactionState["Proceeding"] = "Proceeding";
    TransactionState["Terminated"] = "Terminated";
    TransactionState["Trying"] = "Trying";
})(TransactionState = TransactionState || (TransactionState = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "NonInviteClientTransaction": () => ( NonInviteClientTransaction)
 });
 var _timers_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(37);
 var _client_transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(66);
 var _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(64);



/**
 * @remarks
 * @public
 */
class NonInviteClientTransaction extends _client_transaction_js__WEBPACK_IMPORTED_MODULE_0__.ClientTransaction {
    /**
     * @param request
     * @param transport
     * @param user
     */
    constructor(request, transport, user) {
        super(request, transport, user, _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying, "sip.transaction.nict");
        this.F = setTimeout(() => this.timerF(), _timers_js__WEBPACK_IMPORTED_MODULE_2__.Timers.TIMER_F);
        this.send(request.toString()).catch((error) => {
            this.logTransportError(error, "Failed to send initial outgoing request.");
        });
    }
    dispose() {
        if (this.F) {
            clearTimeout(this.F);
            this.F = undefined;
        }
        if (this.K) {
            clearTimeout(this.K);
            this.K = undefined;
        }
        super.dispose();
    }
    get kind() {
        return "nict";
    }
    /** @param response */
    receiveResponse(response) {
        const statusCode = response.statusCode;
        if (!statusCode || statusCode < 100 || statusCode > 699) {
            throw new Error(`Invalid status code ${statusCode}`);
        }
        switch (this.state) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying:
                if (statusCode >= 100 && statusCode <= 199) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding);
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                if (statusCode >= 200 && statusCode <= 699) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    if (statusCode === 408) {
                        this.onRequestTimeout();
                        return;
                    }
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (statusCode >= 100 && statusCode <= 199) {
                    if (this.user.receiveResponse) {
                        return this.user.receiveResponse(response);
                    }
                }
                if (statusCode >= 200 && statusCode <= 699) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    if (statusCode === 408) {
                        this.onRequestTimeout();
                        return;
                    }
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                return;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                return;
            default:
                throw new Error(`Invalid state ${this.state}`);
        }
        const message = `Non-INVITE client transaction received unexpected ${statusCode} response while in state ${this.state}.`;
        this.logger.warn(message);
        return;
    }
    /** @param error */
    onTransportError(error) {
        if (this.user.onTransportError) {
            this.user.onTransportError(error);
        }
        this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated, true);
    }
    typeToString() {
        return "non-INVITE client transaction";
    }
    /** @param newState */
    stateTransition(newState, dueToTransportError = false) {
        const invalidStateTransition = () => {
            throw new Error(`Invalid state transition from ${this.state} to ${newState}`);
        };
        switch (newState) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying:
                invalidStateTransition();
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying && this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying &&
                    this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding &&
                    this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
                    if (!dueToTransportError) {
                        invalidStateTransition();
                    }
                }
                break;
            default:
                invalidStateTransition();
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            if (this.F) {
                clearTimeout(this.F);
                this.F = undefined;
            }
            this.K = setTimeout(() => this.timerK(), _timers_js__WEBPACK_IMPORTED_MODULE_2__.Timers.TIMER_K);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated) {
            this.dispose();
        }
        this.setState(newState);
    }
    timerF() {
        this.logger.debug(`Timer F expired for non-INVITE client transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying || this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
            this.onRequestTimeout();
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
    timerK() {
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ClientTransaction": () => ( ClientTransaction)
 });
 var _transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(67);

/**
 * @remarks
 * @public
 */
class ClientTransaction extends _transaction_js__WEBPACK_IMPORTED_MODULE_0__.Transaction {
    constructor(_request, transport, user, state, loggerCategory) {
        super(transport, user, ClientTransaction.makeId(_request), state, loggerCategory);
        this._request = _request;
        this.user = user;
        _request.setViaHeader(this.id, transport.protocol);
    }
    static makeId(request) {
        if (request.method === "CANCEL") {
            if (!request.branch) {
                throw new Error("Outgoing CANCEL request without a branch.");
            }
            return request.branch;
        }
        else {
            return "z9hG4bK" + Math.floor(Math.random() * 10000000);
        }
    }
    get request() {
        return this._request;
    }
    onRequestTimeout() {
        if (this.user.onRequestTimeout) {
            this.user.onRequestTimeout();
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Transaction": () => ( Transaction)
 });
 var _exceptions_transport_error_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(68);

/**
 * @remarks
 * @public
 */
class Transaction {
    constructor(_transport, _user, _id, _state, loggerCategory) {
        this._transport = _transport;
        this._user = _user;
        this._id = _id;
        this._state = _state;
        this.listeners = new Array();
        this.logger = _user.loggerFactory.getLogger(loggerCategory, _id);
        this.logger.debug(`Constructing ${this.typeToString()} with id ${this.id}.`);
    }
    dispose() {
        this.logger.debug(`Destroyed ${this.typeToString()} with id ${this.id}.`);
    }
    get id() {
        return this._id;
    }
    get kind() {
        throw new Error("Invalid kind.");
    }
    get state() {
        return this._state;
    }
    get transport() {
        return this._transport;
    }
    /**
     * @param listener
     * @param options
     */
    addStateChangeListener(listener, options) {
        const onceWrapper = () => {
            this.removeStateChangeListener(onceWrapper);
            listener();
        };
        (options === null || options === void 0 ? void 0 : options.once) === true ? this.listeners.push(onceWrapper) : this.listeners.push(listener);
    }
    /** @internal */
    notifyStateChangeListeners() {
        this.listeners.slice().forEach((listener) => listener());
    }
    /** @param listener */
    removeStateChangeListener(listener) {
        this.listeners = this.listeners.filter((l) => l !== listener);
    }
    logTransportError(error, message) {
        this.logger.error(error.message);
        this.logger.error(`Transport error occurred in ${this.typeToString()} with id ${this.id}.`);
        this.logger.error(message);
    }
    /** @returns */
    send(message) {
        return this.transport.send(message).catch((error) => {
            if (error instanceof _exceptions_transport_error_js__WEBPACK_IMPORTED_MODULE_0__.TransportError) {
                this.onTransportError(error);
                throw error;
            }
            let transportError;
            if (error && typeof error.message === "string") {
                transportError = new _exceptions_transport_error_js__WEBPACK_IMPORTED_MODULE_0__.TransportError(error.message);
            }
            else {
                transportError = new _exceptions_transport_error_js__WEBPACK_IMPORTED_MODULE_0__.TransportError();
            }
            this.onTransportError(transportError);
            throw transportError;
        });
    }
    setState(state) {
        this.logger.debug(`State change to "${state}" on ${this.typeToString()} with id ${this.id}.`);
        this._state = state;
        if (this._user.onStateChange) {
            this._user.onStateChange(state);
        }
        this.notifyStateChangeListeners();
    }
    typeToString() {
        return "UnknownType";
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "TransportError": () => ( TransportError)
 });
 var _exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);

/** @public */
class TransportError extends _exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception {
    constructor(message) {
        super(message ? message : "Unspecified transport error.");
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "InviteClientTransaction": () => ( InviteClientTransaction)
 });
 var _timers_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(37);
 var _client_transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(66);
 var _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(64);



/**
 * @remarks
 * @public
 */
class InviteClientTransaction extends _client_transaction_js__WEBPACK_IMPORTED_MODULE_0__.ClientTransaction {
    /**
     * @param request
     * @param transport
     * @param user
     */
    constructor(request, transport, user) {
        super(request, transport, user, _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling, "sip.transaction.ict");
        this.ackRetransmissionCache = new Map();
        this.B = setTimeout(() => this.timerB(), _timers_js__WEBPACK_IMPORTED_MODULE_2__.Timers.TIMER_B);
        this.send(request.toString()).catch((error) => {
            this.logTransportError(error, "Failed to send initial outgoing request.");
        });
    }
    dispose() {
        if (this.B) {
            clearTimeout(this.B);
            this.B = undefined;
        }
        if (this.D) {
            clearTimeout(this.D);
            this.D = undefined;
        }
        if (this.M) {
            clearTimeout(this.M);
            this.M = undefined;
        }
        super.dispose();
    }
    get kind() {
        return "ict";
    }
    /** @param ack */
    ackResponse(ack) {
        const toTag = ack.toTag;
        if (!toTag) {
            throw new Error("To tag undefined.");
        }
        const id = "z9hG4bK" + Math.floor(Math.random() * 10000000);
        ack.setViaHeader(id, this.transport.protocol);
        this.ackRetransmissionCache.set(toTag, ack);
        this.send(ack.toString()).catch((error) => {
            this.logTransportError(error, "Failed to send ACK to 2xx response.");
        });
    }
    /** @param response */
    receiveResponse(response) {
        const statusCode = response.statusCode;
        if (!statusCode || statusCode < 100 || statusCode > 699) {
            throw new Error(`Invalid status code ${statusCode}`);
        }
        switch (this.state) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling:
                if (statusCode >= 100 && statusCode <= 199) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding);
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                if (statusCode >= 200 && statusCode <= 299) {
                    this.ackRetransmissionCache.set(response.toTag, undefined);
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted);
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                if (statusCode >= 300 && statusCode <= 699) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    this.ack(response);
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (statusCode >= 100 && statusCode <= 199) {
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                if (statusCode >= 200 && statusCode <= 299) {
                    this.ackRetransmissionCache.set(response.toTag, undefined);
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted);
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                if (statusCode >= 300 && statusCode <= 699) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    this.ack(response);
                    if (this.user.receiveResponse) {
                        this.user.receiveResponse(response);
                    }
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted:
                if (statusCode >= 200 && statusCode <= 299) {
                    if (!this.ackRetransmissionCache.has(response.toTag)) {
                        this.ackRetransmissionCache.set(response.toTag, undefined);
                        if (this.user.receiveResponse) {
                            this.user.receiveResponse(response);
                        }
                        return;
                    }
                    const ack = this.ackRetransmissionCache.get(response.toTag);
                    if (ack) {
                        this.send(ack.toString()).catch((error) => {
                            this.logTransportError(error, "Failed to send retransmission of ACK to 2xx response.");
                        });
                        return;
                    }
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (statusCode >= 300 && statusCode <= 699) {
                    this.ack(response);
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                break;
            default:
                throw new Error(`Invalid state ${this.state}`);
        }
        const message = `Received unexpected ${statusCode} response while in state ${this.state}.`;
        this.logger.warn(message);
        return;
    }
    /** @param error */
    onTransportError(error) {
        if (this.user.onTransportError) {
            this.user.onTransportError(error);
        }
        this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated, true);
    }
    typeToString() {
        return "INVITE client transaction";
    }
    ack(response) {
        const ruri = this.request.ruri;
        const callId = this.request.callId;
        const cseq = this.request.cseq;
        const from = this.request.getHeader("from");
        const to = response.getHeader("to");
        const via = this.request.getHeader("via");
        const route = this.request.getHeader("route");
        if (!from) {
            throw new Error("From undefined.");
        }
        if (!to) {
            throw new Error("To undefined.");
        }
        if (!via) {
            throw new Error("Via undefined.");
        }
        let ack = `ACK ${ruri} SIP/2.0\r\n`;
        if (route) {
            ack += `Route: ${route}\r\n`;
        }
        ack += `Via: ${via}\r\n`;
        ack += `To: ${to}\r\n`;
        ack += `From: ${from}\r\n`;
        ack += `Call-ID: ${callId}\r\n`;
        ack += `CSeq: ${cseq} ACK\r\n`;
        ack += `Max-Forwards: 70\r\n`;
        ack += `Content-Length: 0\r\n\r\n`;
        this.send(ack).catch((error) => {
            this.logTransportError(error, "Failed to send ACK to non-2xx response.");
        });
        return;
    }
    /** @param newState */
    stateTransition(newState, dueToTransportError = false) {
        const invalidStateTransition = () => {
            throw new Error(`Invalid state transition from ${this.state} to ${newState}`);
        };
        switch (newState) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling:
                invalidStateTransition();
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted:
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling && this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling &&
                    this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted &&
                    this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
                    if (!dueToTransportError) {
                        invalidStateTransition();
                    }
                }
                break;
            default:
                invalidStateTransition();
        }
        if (this.B) {
            clearTimeout(this.B);
            this.B = undefined;
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.D = setTimeout(() => this.timerD(), _timers_js__WEBPACK_IMPORTED_MODULE_2__.Timers.TIMER_D);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted) {
            this.M = setTimeout(() => this.timerM(), _timers_js__WEBPACK_IMPORTED_MODULE_2__.Timers.TIMER_M);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated) {
            this.dispose();
        }
        this.setState(newState);
    }
    timerA() {
    }
    timerB() {
        this.logger.debug(`Timer B expired for INVITE client transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Calling) {
            this.onRequestTimeout();
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
    timerD() {
        this.logger.debug(`Timer D expired for INVITE client transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
    timerM() {
        this.logger.debug(`Timer M expired for INVITE client transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted) {
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Dialog": () => ( Dialog)
 });
 var _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(26);
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);


/**
 * @remarks
 * @public
 */
class Dialog {
    /**
     * @param core
     * @param dialogState
     */
    constructor(core, dialogState) {
        this.core = core;
        this.dialogState = dialogState;
        this.core.dialogs.set(this.id, this);
    }
    /**
     * @param outgoingRequestMessage
     * @param incomingResponseMessage
     */
    static initialDialogStateForUserAgentClient(outgoingRequestMessage, incomingResponseMessage) {
        const secure = false;
        const routeSet = incomingResponseMessage.getHeaders("record-route").reverse();
        const contact = incomingResponseMessage.parseHeader("contact");
        if (!contact) {
            throw new Error("Contact undefined.");
        }
        if (!(contact instanceof _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_0__.NameAddrHeader)) {
            throw new Error("Contact not instance of NameAddrHeader.");
        }
        const remoteTarget = contact.uri;
        const localSequenceNumber = outgoingRequestMessage.cseq;
        const remoteSequenceNumber = undefined;
        const callId = outgoingRequestMessage.callId;
        const localTag = outgoingRequestMessage.fromTag;
        const remoteTag = incomingResponseMessage.toTag;
        if (!callId) {
            throw new Error("Call id undefined.");
        }
        if (!localTag) {
            throw new Error("From tag undefined.");
        }
        if (!remoteTag) {
            throw new Error("To tag undefined.");
        }
        if (!outgoingRequestMessage.from) {
            throw new Error("From undefined.");
        }
        if (!outgoingRequestMessage.to) {
            throw new Error("To undefined.");
        }
        const localURI = outgoingRequestMessage.from.uri;
        const remoteURI = outgoingRequestMessage.to.uri;
        if (!incomingResponseMessage.statusCode) {
            throw new Error("Incoming response status code undefined.");
        }
        const early = incomingResponseMessage.statusCode < 200 ? true : false;
        const dialogState = {
            id: callId + localTag + remoteTag,
            early,
            callId,
            localTag,
            remoteTag,
            localSequenceNumber,
            remoteSequenceNumber,
            localURI,
            remoteURI,
            remoteTarget,
            routeSet,
            secure
        };
        return dialogState;
    }
    /**
     * @param incomingRequestMessage
     * @param toTag
     */
    static initialDialogStateForUserAgentServer(incomingRequestMessage, toTag, early = false) {
        const secure = false;
        const routeSet = incomingRequestMessage.getHeaders("record-route");
        const contact = incomingRequestMessage.parseHeader("contact");
        if (!contact) {
            throw new Error("Contact undefined.");
        }
        if (!(contact instanceof _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_0__.NameAddrHeader)) {
            throw new Error("Contact not instance of NameAddrHeader.");
        }
        const remoteTarget = contact.uri;
        const remoteSequenceNumber = incomingRequestMessage.cseq;
        const localSequenceNumber = undefined;
        const callId = incomingRequestMessage.callId;
        const localTag = toTag;
        const remoteTag = incomingRequestMessage.fromTag;
        const remoteURI = incomingRequestMessage.from.uri;
        const localURI = incomingRequestMessage.to.uri;
        const dialogState = {
            id: callId + localTag + remoteTag,
            early,
            callId,
            localTag,
            remoteTag,
            localSequenceNumber,
            remoteSequenceNumber,
            localURI,
            remoteURI,
            remoteTarget,
            routeSet,
            secure
        };
        return dialogState;
    }
    dispose() {
        this.core.dialogs.delete(this.id);
    }
    get id() {
        return this.dialogState.id;
    }
    get early() {
        return this.dialogState.early;
    }
    get callId() {
        return this.dialogState.callId;
    }
    get localTag() {
        return this.dialogState.localTag;
    }
    get remoteTag() {
        return this.dialogState.remoteTag;
    }
    get localSequenceNumber() {
        return this.dialogState.localSequenceNumber;
    }
    get remoteSequenceNumber() {
        return this.dialogState.remoteSequenceNumber;
    }
    get localURI() {
        return this.dialogState.localURI;
    }
    get remoteURI() {
        return this.dialogState.remoteURI;
    }
    get remoteTarget() {
        return this.dialogState.remoteTarget;
    }
    get routeSet() {
        return this.dialogState.routeSet;
    }
    get secure() {
        return this.dialogState.secure;
    }
    get userAgentCore() {
        return this.core;
    }
    confirm() {
        this.dialogState.early = false;
    }
    /** @param message */
    receiveRequest(message) {
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.ACK) {
            return;
        }
        if (this.remoteSequenceNumber) {
            if (message.cseq <= this.remoteSequenceNumber) {
                throw new Error("Out of sequence in dialog request. Did you forget to call sequenceGuard()?");
            }
            this.dialogState.remoteSequenceNumber = message.cseq;
        }
        if (!this.remoteSequenceNumber) {
            this.dialogState.remoteSequenceNumber = message.cseq;
        }
    }
    recomputeRouteSet(message) {
        this.dialogState.routeSet = message.getHeaders("record-route").reverse();
    }
    /** @param method */
    createOutgoingRequestMessage(method, options) {
        const toUri = this.remoteURI;
        const toTag = this.remoteTag;
        const fromUri = this.localURI;
        const fromTag = this.localTag;
        const callId = this.callId;
        let cseq;
        if (options && options.cseq) {
            cseq = options.cseq;
        }
        else if (!this.dialogState.localSequenceNumber) {
            cseq = this.dialogState.localSequenceNumber = 1;
        }
        else {
            cseq = this.dialogState.localSequenceNumber += 1;
        }
        const ruri = this.remoteTarget;
        const routeSet = this.routeSet;
        const extraHeaders = options && options.extraHeaders;
        const body = options && options.body;
        const message = this.userAgentCore.makeOutgoingRequestMessage(method, ruri, fromUri, toUri, {
            callId,
            cseq,
            fromTag,
            toTag,
            routeSet
        }, extraHeaders, body);
        return message;
    }
    /** @internal */
    incrementLocalSequenceNumber() {
        if (!this.dialogState.localSequenceNumber) {
            throw new Error("Local sequence number undefined.");
        }
        this.dialogState.localSequenceNumber += 1;
    }
    /**
     * @param request
     * @returns
     */
    sequenceGuard(message) {
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.ACK) {
            return true;
        }
        if (this.remoteSequenceNumber && message.cseq <= this.remoteSequenceNumber) {
            this.core.replyStateless(message, { statusCode: 500 });
            return false;
        }
        return true;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionDialog": () => ( SessionDialog)
 });
 var _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(26);
 var _messages_body_js__WEBPACK_IMPORTED_MODULE_21__ = __webpack_require__(18);
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(30);
 var _messages_incoming_request_message_js__WEBPACK_IMPORTED_MODULE_22__ = __webpack_require__(19);
 var _messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_23__ = __webpack_require__(27);
 var _messages_outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_24__ = __webpack_require__(28);
 var _session_session_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(31);
 var _timers_js__WEBPACK_IMPORTED_MODULE_25__ = __webpack_require__(37);
 var _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(69);
 var _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(72);
 var _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(64);
 var _user_agents_bye_user_agent_client_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(74);
 var _user_agents_bye_user_agent_server_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(81);
 var _user_agents_info_user_agent_client_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(75);
 var _user_agents_info_user_agent_server_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(85);
 var _user_agents_message_user_agent_client_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(77);
 var _user_agents_message_user_agent_server_js__WEBPACK_IMPORTED_MODULE_17__ = __webpack_require__(87);
 var _user_agents_notify_user_agent_client_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(78);
 var _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_18__ = __webpack_require__(88);
 var _user_agents_prack_user_agent_client_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(79);
 var _user_agents_prack_user_agent_server_js__WEBPACK_IMPORTED_MODULE_19__ = __webpack_require__(89);
 var _user_agents_re_invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(76);
 var _user_agents_re_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_16__ = __webpack_require__(86);
 var _user_agents_refer_user_agent_client_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(80);
 var _user_agents_refer_user_agent_server_js__WEBPACK_IMPORTED_MODULE_20__ = __webpack_require__(90);
 var _dialog_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(70);



























/** @public */
class SessionDialog extends _dialog_js__WEBPACK_IMPORTED_MODULE_0__.Dialog {
    constructor(initialTransaction, core, state, delegate) {
        super(core, state);
        this.initialTransaction = initialTransaction;
        this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Initial;
        this.ackWait = false;
        this.ackProcessing = false;
        this.delegate = delegate;
        if (initialTransaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            this.ackWait = true;
        }
        if (!this.early) {
            this.start2xxRetransmissionTimer();
        }
        this.signalingStateTransition(initialTransaction.request);
        this.logger = core.loggerFactory.getLogger("sip.invite-dialog");
        this.logger.log(`INVITE dialog ${this.id} constructed`);
    }
    dispose() {
        super.dispose();
        this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Closed;
        this._offer = undefined;
        this._answer = undefined;
        if (this.invite2xxTimer) {
            clearTimeout(this.invite2xxTimer);
            this.invite2xxTimer = undefined;
        }
        this.logger.log(`INVITE dialog ${this.id} destroyed`);
    }
    get sessionState() {
        if (this.early) {
            return _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Early;
        }
        else if (this.ackWait) {
            return _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.AckWait;
        }
        else if (this._signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Closed) {
            return _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Terminated;
        }
        else {
            return _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SessionState.Confirmed;
        }
    }
    get signalingState() {
        return this._signalingState;
    }
    get offer() {
        return this._offer;
    }
    get answer() {
        return this._answer;
    }
    confirm() {
        if (this.early) {
            this.start2xxRetransmissionTimer();
        }
        super.confirm();
    }
    reConfirm() {
        if (this.reinviteUserAgentServer) {
            this.startReInvite2xxRetransmissionTimer();
        }
    }
    /** @param options */
    ack(options = {}) {
        this.logger.log(`INVITE dialog ${this.id} sending ACK request`);
        let transaction;
        if (this.reinviteUserAgentClient) {
            if (!(this.reinviteUserAgentClient.transaction instanceof _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_3__.InviteClientTransaction)) {
                throw new Error("Transaction not instance of InviteClientTransaction.");
            }
            transaction = this.reinviteUserAgentClient.transaction;
            this.reinviteUserAgentClient = undefined;
        }
        else {
            if (!(this.initialTransaction instanceof _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_3__.InviteClientTransaction)) {
                throw new Error("Initial transaction not instance of InviteClientTransaction.");
            }
            transaction = this.initialTransaction;
        }
        const message = this.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.ACK, {
            cseq: transaction.request.cseq,
            extraHeaders: options.extraHeaders,
            body: options.body
        });
        transaction.ackResponse(message);
        this.signalingStateTransition(message);
        return { message };
    }
    /**
     * @param options
     * @returns
     */
    bye(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending BYE request`);
        if (this.initialTransaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            if (this.early) {
                throw new Error("UAS MUST NOT send a BYE on early dialogs.");
            }
            if (this.ackWait && this.initialTransaction.state !== _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_5__.TransactionState.Terminated) {
                throw new Error("UAS MUST NOT send a BYE on a confirmed dialog " +
                    "until it has received an ACK for its 2xx response " +
                    "or until the server transaction times out.");
            }
        }
        return new _user_agents_bye_user_agent_client_js__WEBPACK_IMPORTED_MODULE_6__.ByeUserAgentClient(this, delegate, options);
    }
    /** @param options */
    info(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending INFO request`);
        if (this.early) {
            throw new Error("Dialog not confirmed.");
        }
        return new _user_agents_info_user_agent_client_js__WEBPACK_IMPORTED_MODULE_7__.InfoUserAgentClient(this, delegate, options);
    }
    /** @param options */
    invite(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending INVITE request`);
        if (this.early) {
            throw new Error("Dialog not confirmed.");
        }
        if (this.reinviteUserAgentClient) {
            throw new Error("There is an ongoing re-INVITE client transaction.");
        }
        if (this.reinviteUserAgentServer) {
            throw new Error("There is an ongoing re-INVITE server transaction.");
        }
        return new _user_agents_re_invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_8__.ReInviteUserAgentClient(this, delegate, options);
    }
    /** @param options */
    message(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending MESSAGE request`);
        if (this.early) {
            throw new Error("Dialog not confirmed.");
        }
        const message = this.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.MESSAGE, options);
        return new _user_agents_message_user_agent_client_js__WEBPACK_IMPORTED_MODULE_9__.MessageUserAgentClient(this.core, message, delegate);
    }
    /** @param options */
    notify(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending NOTIFY request`);
        if (this.early) {
            throw new Error("Dialog not confirmed.");
        }
        return new _user_agents_notify_user_agent_client_js__WEBPACK_IMPORTED_MODULE_10__.NotifyUserAgentClient(this, delegate, options);
    }
    /** @param options */
    prack(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending PRACK request`);
        return new _user_agents_prack_user_agent_client_js__WEBPACK_IMPORTED_MODULE_11__.PrackUserAgentClient(this, delegate, options);
    }
    /** @param options */
    refer(delegate, options) {
        this.logger.log(`INVITE dialog ${this.id} sending REFER request`);
        if (this.early) {
            throw new Error("Dialog not confirmed.");
        }
        return new _user_agents_refer_user_agent_client_js__WEBPACK_IMPORTED_MODULE_12__.ReferUserAgentClient(this, delegate, options);
    }
    /** @param message */
    receiveRequest(message) {
        this.logger.log(`INVITE dialog ${this.id} received ${message.method} request`);
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.ACK) {
            if (this.ackWait) {
                if (this.initialTransaction instanceof _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_3__.InviteClientTransaction) {
                    this.logger.warn(`INVITE dialog ${this.id} received unexpected ${message.method} request, dropping.`);
                    return;
                }
                if (this.initialTransaction.request.cseq !== message.cseq) {
                    this.logger.warn(`INVITE dialog ${this.id} received unexpected ${message.method} request, dropping.`);
                    return;
                }
                this.ackWait = false;
            }
            else {
                if (!this.reinviteUserAgentServer) {
                    this.logger.warn(`INVITE dialog ${this.id} received unexpected ${message.method} request, dropping.`);
                    return;
                }
                if (this.reinviteUserAgentServer.transaction.request.cseq !== message.cseq) {
                    this.logger.warn(`INVITE dialog ${this.id} received unexpected ${message.method} request, dropping.`);
                    return;
                }
                this.reinviteUserAgentServer = undefined;
            }
            this.signalingStateTransition(message);
            if (this.delegate && this.delegate.onAck) {
                const promiseOrVoid = this.delegate.onAck({ message });
                if (promiseOrVoid instanceof Promise) {
                    this.ackProcessing = true;
                    promiseOrVoid.then(() => (this.ackProcessing = false)).catch(() => (this.ackProcessing = false));
                }
            }
            return;
        }
        if (!this.sequenceGuard(message)) {
            this.logger.log(`INVITE dialog ${this.id} rejected out of order ${message.method} request.`);
            return;
        }
        super.receiveRequest(message);
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.INVITE) {
            const warning = () => {
                const reason = this.ackWait ? "waiting for initial ACK" : "processing initial ACK";
                this.logger.warn(`INVITE dialog ${this.id} received re-INVITE while ${reason}`);
                let msg = "RFC 5407 suggests the following to avoid this race condition... ";
                msg += " Note: Implementation issues are outside the scope of this document,";
                msg += " but the following tip is provided for avoiding race conditions of";
                msg += " this type.  The caller can delay sending re-INVITE F6 for some period";
                msg += " of time (2 seconds, perhaps), after which the caller can reasonably";
                msg += " assume that its ACK has been received.  Implementors can decouple the";
                msg += " actions of the user (e.g., pressing the hold button) from the actions";
                msg += " of the protocol (the sending of re-INVITE F6), so that the UA can";
                msg += " behave like this.  In this case, it is the implementor's choice as to";
                msg += " how long to wait.  In most cases, such an implementation may be";
                msg += " useful to prevent the type of race condition shown in this section.";
                msg += " This document expresses no preference about whether or not they";
                msg += " should wait for an ACK to be delivered.  After considering the impact";
                msg += " on user experience, implementors should decide whether or not to wait";
                msg += " for a while, because the user experience depends on the";
                msg += " implementation and has no direct bearing on protocol behavior.";
                this.logger.warn(msg);
                return;
            };
            const retryAfter = Math.floor(Math.random() * 10) + 1;
            const extraHeaders = [`Retry-After: ${retryAfter}`];
            if (this.ackProcessing) {
                this.core.replyStateless(message, { statusCode: 500, extraHeaders });
                warning();
                return;
            }
            if (this.ackWait && this.signalingState !== _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable) {
                this.core.replyStateless(message, { statusCode: 500, extraHeaders });
                warning();
                return;
            }
            if (this.reinviteUserAgentServer) {
                this.core.replyStateless(message, { statusCode: 500, extraHeaders });
                return;
            }
            if (this.reinviteUserAgentClient) {
                this.core.replyStateless(message, { statusCode: 491 });
                return;
            }
        }
        if (message.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.INVITE) {
            const contact = message.parseHeader("contact");
            if (!contact) {
                throw new Error("Contact undefined.");
            }
            if (!(contact instanceof _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_13__.NameAddrHeader)) {
                throw new Error("Contact not instance of NameAddrHeader.");
            }
            this.dialogState.remoteTarget = contact.uri;
        }
        switch (message.method) {
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.BYE:
                {
                    const uas = new _user_agents_bye_user_agent_server_js__WEBPACK_IMPORTED_MODULE_14__.ByeUserAgentServer(this, message);
                    this.delegate && this.delegate.onBye ? this.delegate.onBye(uas) : uas.accept();
                    this.dispose();
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.INFO:
                {
                    const uas = new _user_agents_info_user_agent_server_js__WEBPACK_IMPORTED_MODULE_15__.InfoUserAgentServer(this, message);
                    this.delegate && this.delegate.onInfo
                        ? this.delegate.onInfo(uas)
                        : uas.reject({
                            statusCode: 469,
                            extraHeaders: ["Recv-Info:"]
                        });
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.INVITE:
                {
                    const uas = new _user_agents_re_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_16__.ReInviteUserAgentServer(this, message);
                    this.signalingStateTransition(message);
                    this.delegate && this.delegate.onInvite ? this.delegate.onInvite(uas) : uas.reject({ statusCode: 488 });
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.MESSAGE:
                {
                    const uas = new _user_agents_message_user_agent_server_js__WEBPACK_IMPORTED_MODULE_17__.MessageUserAgentServer(this.core, message);
                    this.delegate && this.delegate.onMessage ? this.delegate.onMessage(uas) : uas.accept();
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.NOTIFY:
                {
                    const uas = new _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_18__.NotifyUserAgentServer(this, message);
                    this.delegate && this.delegate.onNotify ? this.delegate.onNotify(uas) : uas.accept();
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.PRACK:
                {
                    const uas = new _user_agents_prack_user_agent_server_js__WEBPACK_IMPORTED_MODULE_19__.PrackUserAgentServer(this, message);
                    this.delegate && this.delegate.onPrack ? this.delegate.onPrack(uas) : uas.accept();
                }
                break;
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_4__.C.REFER:
                {
                    const uas = new _user_agents_refer_user_agent_server_js__WEBPACK_IMPORTED_MODULE_20__.ReferUserAgentServer(this, message);
                    this.delegate && this.delegate.onRefer ? this.delegate.onRefer(uas) : uas.reject();
                }
                break;
            default:
                {
                    this.logger.log(`INVITE dialog ${this.id} received unimplemented ${message.method} request`);
                    this.core.replyStateless(message, { statusCode: 501 });
                }
                break;
        }
    }
    /** @param message */
    reliableSequenceGuard(message) {
        const statusCode = message.statusCode;
        if (!statusCode) {
            throw new Error("Status code undefined");
        }
        if (statusCode > 100 && statusCode < 200) {
            const requireHeader = message.getHeader("require");
            const rseqHeader = message.getHeader("rseq");
            const rseq = requireHeader && requireHeader.includes("100rel") && rseqHeader ? Number(rseqHeader) : undefined;
            if (rseq) {
                if (this.rseq && this.rseq + 1 !== rseq) {
                    return false;
                }
                this.rseq = this.rseq ? this.rseq + 1 : rseq;
            }
        }
        return true;
    }
    signalingStateRollback() {
        if (this._signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer ||
            this.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer) {
            if (this._rollbackOffer && this._rollbackAnswer) {
                this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable;
                this._offer = this._rollbackOffer;
                this._answer = this._rollbackAnswer;
            }
        }
    }
    /** @param message */
    signalingStateTransition(message) {
        const body = (0,_messages_body_js__WEBPACK_IMPORTED_MODULE_21__.getBody)(message);
        if (!body || body.contentDisposition !== "session") {
            return;
        }
        if (this._signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable) {
            this._rollbackOffer = this._offer;
            this._rollbackAnswer = this._answer;
        }
        if (message instanceof _messages_incoming_request_message_js__WEBPACK_IMPORTED_MODULE_22__.IncomingRequestMessage) {
            switch (this._signalingState) {
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Initial:
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer;
                    this._offer = body;
                    this._answer = undefined;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable;
                    this._answer = body;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer:
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Closed:
                    break;
                default:
                    throw new Error("Unexpected signaling state.");
            }
        }
        if (message instanceof _messages_incoming_response_message_js__WEBPACK_IMPORTED_MODULE_23__.IncomingResponseMessage) {
            switch (this._signalingState) {
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Initial:
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer;
                    this._offer = body;
                    this._answer = undefined;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable;
                    this._answer = body;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer:
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Closed:
                    break;
                default:
                    throw new Error("Unexpected signaling state.");
            }
        }
        if (message instanceof _messages_outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_24__.OutgoingRequestMessage) {
            switch (this._signalingState) {
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Initial:
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer;
                    this._offer = body;
                    this._answer = undefined;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer:
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable;
                    this._answer = body;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Closed:
                    break;
                default:
                    throw new Error("Unexpected signaling state.");
            }
        }
        if ((0,_messages_body_js__WEBPACK_IMPORTED_MODULE_21__.isBody)(message)) {
            switch (this._signalingState) {
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Initial:
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer;
                    this._offer = body;
                    this._answer = undefined;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveLocalOffer:
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.HaveRemoteOffer:
                    this._signalingState = _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Stable;
                    this._answer = body;
                    break;
                case _session_session_js__WEBPACK_IMPORTED_MODULE_1__.SignalingState.Closed:
                    break;
                default:
                    throw new Error("Unexpected signaling state.");
            }
        }
    }
    start2xxRetransmissionTimer() {
        if (this.initialTransaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            const transaction = this.initialTransaction;
            let timeout = _timers_js__WEBPACK_IMPORTED_MODULE_25__.Timers.T1;
            const retransmission = () => {
                if (!this.ackWait) {
                    this.invite2xxTimer = undefined;
                    return;
                }
                this.logger.log("No ACK for 2xx response received, attempting retransmission");
                transaction.retransmitAcceptedResponse();
                timeout = Math.min(timeout * 2, _timers_js__WEBPACK_IMPORTED_MODULE_25__.Timers.T2);
                this.invite2xxTimer = setTimeout(retransmission, timeout);
            };
            this.invite2xxTimer = setTimeout(retransmission, timeout);
            const stateChanged = () => {
                if (transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_5__.TransactionState.Terminated) {
                    transaction.removeStateChangeListener(stateChanged);
                    if (this.invite2xxTimer) {
                        clearTimeout(this.invite2xxTimer);
                        this.invite2xxTimer = undefined;
                    }
                    if (this.ackWait) {
                        if (this.delegate && this.delegate.onAckTimeout) {
                            this.delegate.onAckTimeout();
                        }
                        else {
                            this.bye();
                        }
                    }
                }
            };
            transaction.addStateChangeListener(stateChanged);
        }
    }
    startReInvite2xxRetransmissionTimer() {
        if (this.reinviteUserAgentServer && this.reinviteUserAgentServer.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            const transaction = this.reinviteUserAgentServer.transaction;
            let timeout = _timers_js__WEBPACK_IMPORTED_MODULE_25__.Timers.T1;
            const retransmission = () => {
                if (!this.reinviteUserAgentServer) {
                    this.invite2xxTimer = undefined;
                    return;
                }
                this.logger.log("No ACK for 2xx response received, attempting retransmission");
                transaction.retransmitAcceptedResponse();
                timeout = Math.min(timeout * 2, _timers_js__WEBPACK_IMPORTED_MODULE_25__.Timers.T2);
                this.invite2xxTimer = setTimeout(retransmission, timeout);
            };
            this.invite2xxTimer = setTimeout(retransmission, timeout);
            const stateChanged = () => {
                if (transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_5__.TransactionState.Terminated) {
                    transaction.removeStateChangeListener(stateChanged);
                    if (this.invite2xxTimer) {
                        clearTimeout(this.invite2xxTimer);
                        this.invite2xxTimer = undefined;
                    }
                    if (this.reinviteUserAgentServer) {
                    }
                }
            };
            transaction.addStateChangeListener(stateChanged);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "InviteServerTransaction": () => ( InviteServerTransaction)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(30);
 var _timers_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(37);
 var _server_transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(73);
 var _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(64);




/**
 * @remarks
 * @public
 */
class InviteServerTransaction extends _server_transaction_js__WEBPACK_IMPORTED_MODULE_0__.ServerTransaction {
    /**
     * @param request
     * @param transport
     * @param user
     */
    constructor(request, transport, user) {
        super(request, transport, user, _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding, "sip.transaction.ist");
    }
    dispose() {
        this.stopProgressExtensionTimer();
        if (this.H) {
            clearTimeout(this.H);
            this.H = undefined;
        }
        if (this.I) {
            clearTimeout(this.I);
            this.I = undefined;
        }
        if (this.L) {
            clearTimeout(this.L);
            this.L = undefined;
        }
        super.dispose();
    }
    get kind() {
        return "ist";
    }
    /** @param request */
    receiveRequest(request) {
        switch (this.state) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.INVITE) {
                    if (this.lastProvisionalResponse) {
                        this.send(this.lastProvisionalResponse).catch((error) => {
                            this.logTransportError(error, "Failed to send retransmission of provisional response.");
                        });
                    }
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted:
                if (request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.INVITE) {
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.INVITE) {
                    if (!this.lastFinalResponse) {
                        throw new Error("Last final response undefined.");
                    }
                    this.send(this.lastFinalResponse).catch((error) => {
                        this.logTransportError(error, "Failed to send retransmission of final response.");
                    });
                    return;
                }
                if (request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.ACK) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Confirmed);
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Confirmed:
                if (request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.INVITE || request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.ACK) {
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                if (request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.INVITE || request.method === _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.ACK) {
                    return;
                }
                break;
            default:
                throw new Error(`Invalid state ${this.state}`);
        }
        const message = `INVITE server transaction received unexpected ${request.method} request while in state ${this.state}.`;
        this.logger.warn(message);
        return;
    }
    /**
     * @param statusCode
     * @param response
     */
    receiveResponse(statusCode, response) {
        if (statusCode < 100 || statusCode > 699) {
            throw new Error(`Invalid status code ${statusCode}`);
        }
        switch (this.state) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (statusCode >= 100 && statusCode <= 199) {
                    this.lastProvisionalResponse = response;
                    if (statusCode > 100) {
                        this.startProgressExtensionTimer();
                    }
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send 1xx response.");
                    });
                    return;
                }
                if (statusCode >= 200 && statusCode <= 299) {
                    this.lastFinalResponse = response;
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted);
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send 2xx response.");
                    });
                    return;
                }
                if (statusCode >= 300 && statusCode <= 699) {
                    this.lastFinalResponse = response;
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send non-2xx final response.");
                    });
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted:
                if (statusCode >= 200 && statusCode <= 299) {
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send 2xx response.");
                    });
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Confirmed:
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                break;
            default:
                throw new Error(`Invalid state ${this.state}`);
        }
        const message = `INVITE server transaction received unexpected ${statusCode} response from TU while in state ${this.state}.`;
        this.logger.error(message);
        throw new Error(message);
    }
    retransmitAcceptedResponse() {
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted && this.lastFinalResponse) {
            this.send(this.lastFinalResponse).catch((error) => {
                this.logTransportError(error, "Failed to send 2xx response.");
            });
        }
    }
    onTransportError(error) {
        if (this.user.onTransportError) {
            this.user.onTransportError(error);
        }
    }
    typeToString() {
        return "INVITE server transaction";
    }
    /** @param newState */
    stateTransition(newState) {
        const invalidStateTransition = () => {
            throw new Error(`Invalid state transition from ${this.state} to ${newState}`);
        };
        switch (newState) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                invalidStateTransition();
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted:
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Confirmed:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted &&
                    this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed &&
                    this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Confirmed) {
                    invalidStateTransition();
                }
                break;
            default:
                invalidStateTransition();
        }
        this.stopProgressExtensionTimer();
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted) {
            this.L = setTimeout(() => this.timerL(), _timers_js__WEBPACK_IMPORTED_MODULE_3__.Timers.TIMER_L);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.H = setTimeout(() => this.timerH(), _timers_js__WEBPACK_IMPORTED_MODULE_3__.Timers.TIMER_H);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Confirmed) {
            this.I = setTimeout(() => this.timerI(), _timers_js__WEBPACK_IMPORTED_MODULE_3__.Timers.TIMER_I);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated) {
            this.dispose();
        }
        this.setState(newState);
    }
    startProgressExtensionTimer() {
        if (this.progressExtensionTimer === undefined) {
            this.progressExtensionTimer = setInterval(() => {
                this.logger.debug(`Progress extension timer expired for INVITE server transaction ${this.id}.`);
                if (!this.lastProvisionalResponse) {
                    throw new Error("Last provisional response undefined.");
                }
                this.send(this.lastProvisionalResponse).catch((error) => {
                    this.logTransportError(error, "Failed to send retransmission of provisional response.");
                });
            }, _timers_js__WEBPACK_IMPORTED_MODULE_3__.Timers.PROVISIONAL_RESPONSE_INTERVAL);
        }
    }
    stopProgressExtensionTimer() {
        if (this.progressExtensionTimer !== undefined) {
            clearInterval(this.progressExtensionTimer);
            this.progressExtensionTimer = undefined;
        }
    }
    timerG() {
    }
    timerH() {
        this.logger.debug(`Timer H expired for INVITE server transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.logger.warn("ACK to negative final response was never received, terminating transaction.");
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
    timerI() {
        this.logger.debug(`Timer I expired for INVITE server transaction ${this.id}.`);
        this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
    }
    timerL() {
        this.logger.debug(`Timer L expired for INVITE server transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Accepted) {
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ServerTransaction": () => ( ServerTransaction)
 });
 var _transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(67);

/**
 * @remarks
 * @public
 */
class ServerTransaction extends _transaction_js__WEBPACK_IMPORTED_MODULE_0__.Transaction {
    constructor(_request, transport, user, state, loggerCategory) {
        super(transport, user, _request.viaBranch, state, loggerCategory);
        this._request = _request;
        this.user = user;
    }
    get request() {
        return this._request;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ByeUserAgentClient": () => ( ByeUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/** @public */
class ByeUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.BYE, options);
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, dialog.userAgentCore, message, delegate);
        dialog.dispose();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "InfoUserAgentClient": () => ( InfoUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/** @public */
class InfoUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.INFO, options);
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, dialog.userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ReInviteUserAgentClient": () => ( ReInviteUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(69);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/**
 * @remarks
 * @public
 */
class ReInviteUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.INVITE, options);
        super(_transactions_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteClientTransaction, dialog.userAgentCore, message, delegate);
        this.delegate = delegate;
        dialog.signalingStateTransition(message);
        dialog.reinviteUserAgentClient = this;
        this.dialog = dialog;
    }
    receiveResponse(message) {
        if (!this.authenticationGuard(message, this.dialog)) {
            return;
        }
        const statusCode = message.statusCode ? message.statusCode.toString() : "";
        if (!statusCode) {
            throw new Error("Response status code undefined.");
        }
        switch (true) {
            case /^100$/.test(statusCode):
                if (this.delegate && this.delegate.onTrying) {
                    this.delegate.onTrying({ message });
                }
                break;
            case /^1[0-9]{2}$/.test(statusCode):
                if (this.delegate && this.delegate.onProgress) {
                    this.delegate.onProgress({
                        message,
                        session: this.dialog,
                        // eslint-disable-next-line @typescript-eslint/no-unused-vars
                        prack: (options) => {
                            throw new Error("Unimplemented.");
                        }
                    });
                }
                break;
            case /^2[0-9]{2}$/.test(statusCode):
                this.dialog.signalingStateTransition(message);
                if (this.delegate && this.delegate.onAccept) {
                    this.delegate.onAccept({
                        message,
                        session: this.dialog,
                        ack: (options) => {
                            const outgoingAckRequest = this.dialog.ack(options);
                            return outgoingAckRequest;
                        }
                    });
                }
                break;
            case /^3[0-9]{2}$/.test(statusCode):
                this.dialog.signalingStateRollback();
                this.dialog.reinviteUserAgentClient = undefined;
                if (this.delegate && this.delegate.onRedirect) {
                    this.delegate.onRedirect({ message });
                }
                break;
            case /^[4-6][0-9]{2}$/.test(statusCode):
                this.dialog.signalingStateRollback();
                this.dialog.reinviteUserAgentClient = undefined;
                if (this.delegate && this.delegate.onReject) {
                    this.delegate.onReject({ message });
                }
                else {
                }
                break;
            default:
                throw new Error(`Invalid status code ${statusCode}`);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "MessageUserAgentClient": () => ( MessageUserAgentClient)
 });
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);


/** @public */
class MessageUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteClientTransaction, core, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "NotifyUserAgentClient": () => ( NotifyUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/** @public */
class NotifyUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.NOTIFY, options);
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, dialog.userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "PrackUserAgentClient": () => ( PrackUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/** @public */
class PrackUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.PRACK, options);
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, dialog.userAgentCore, message, delegate);
        dialog.signalingStateTransition(message);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ReferUserAgentClient": () => ( ReferUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/** @public */
class ReferUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.REFER, options);
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, dialog.userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ByeUserAgentServer": () => ( ByeUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class ByeUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(dialog, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, dialog.userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "UserAgentServer": () => ( UserAgentServer)
 });
 var _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(36);
 var _messages_outgoing_response_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(84);
 var _messages_utils_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(21);
 var _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(72);
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(83);
 var _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(64);






/**
 * @remarks
 * @public
 */
class UserAgentServer {
    constructor(transactionConstructor, core, message, delegate) {
        this.transactionConstructor = transactionConstructor;
        this.core = core;
        this.message = message;
        this.delegate = delegate;
        this.logger = this.loggerFactory.getLogger("sip.user-agent-server");
        this.toTag = message.toTag ? message.toTag : (0,_messages_utils_js__WEBPACK_IMPORTED_MODULE_0__.newTag)();
        this.init();
    }
    dispose() {
        this.transaction.dispose();
    }
    get loggerFactory() {
        return this.core.loggerFactory;
    }
    get transaction() {
        if (!this._transaction) {
            throw new Error("Transaction undefined.");
        }
        return this._transaction;
    }
    accept(options = { statusCode: 200 }) {
        if (!this.acceptable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError(`${this.message.method} not acceptable in state ${this.transaction.state}.`);
        }
        const statusCode = options.statusCode;
        if (statusCode < 200 || statusCode > 299) {
            throw new TypeError(`Invalid statusCode: ${statusCode}`);
        }
        const response = this.reply(options);
        return response;
    }
    progress(options = { statusCode: 180 }) {
        if (!this.progressable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError(`${this.message.method} not progressable in state ${this.transaction.state}.`);
        }
        const statusCode = options.statusCode;
        if (statusCode < 101 || statusCode > 199) {
            throw new TypeError(`Invalid statusCode: ${statusCode}`);
        }
        const response = this.reply(options);
        return response;
    }
    redirect(contacts, options = { statusCode: 302 }) {
        if (!this.redirectable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError(`${this.message.method} not redirectable in state ${this.transaction.state}.`);
        }
        const statusCode = options.statusCode;
        if (statusCode < 300 || statusCode > 399) {
            throw new TypeError(`Invalid statusCode: ${statusCode}`);
        }
        const contactHeaders = new Array();
        contacts.forEach((contact) => contactHeaders.push(`Contact: ${contact.toString()}`));
        options.extraHeaders = (options.extraHeaders || []).concat(contactHeaders);
        const response = this.reply(options);
        return response;
    }
    reject(options = { statusCode: 480 }) {
        if (!this.rejectable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError(`${this.message.method} not rejectable in state ${this.transaction.state}.`);
        }
        const statusCode = options.statusCode;
        if (statusCode < 400 || statusCode > 699) {
            throw new TypeError(`Invalid statusCode: ${statusCode}`);
        }
        const response = this.reply(options);
        return response;
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    trying(options) {
        if (!this.tryingable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError(`${this.message.method} not tryingable in state ${this.transaction.state}.`);
        }
        const response = this.reply({ statusCode: 100 });
        return response;
    }
    /** @param request */
    receiveCancel(message) {
        if (this.delegate && this.delegate.onCancel) {
            this.delegate.onCancel(message);
        }
    }
    get acceptable() {
        if (this.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            return (this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding || this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Accepted);
        }
        if (this.transaction instanceof _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__.NonInviteServerTransaction) {
            return (this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Trying || this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding);
        }
        throw new Error("Unknown transaction type.");
    }
    get progressable() {
        if (this.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            return this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding;
        }
        if (this.transaction instanceof _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__.NonInviteServerTransaction) {
            return false;
        }
        throw new Error("Unknown transaction type.");
    }
    get redirectable() {
        if (this.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            return this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding;
        }
        if (this.transaction instanceof _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__.NonInviteServerTransaction) {
            return (this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Trying || this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding);
        }
        throw new Error("Unknown transaction type.");
    }
    get rejectable() {
        if (this.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            return this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding;
        }
        if (this.transaction instanceof _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__.NonInviteServerTransaction) {
            return (this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Trying || this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding);
        }
        throw new Error("Unknown transaction type.");
    }
    get tryingable() {
        if (this.transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction) {
            return this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Proceeding;
        }
        if (this.transaction instanceof _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__.NonInviteServerTransaction) {
            return this.transaction.state === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Trying;
        }
        throw new Error("Unknown transaction type.");
    }
    /**
     * @param statusCode
     * @param options
     */
    reply(options) {
        if (!options.toTag && options.statusCode !== 100) {
            options.toTag = this.toTag;
        }
        options.userAgent = options.userAgent || this.core.configuration.userAgentHeaderFieldValue;
        options.supported = options.supported || this.core.configuration.supportedOptionTagsResponse;
        const response = (0,_messages_outgoing_response_js__WEBPACK_IMPORTED_MODULE_5__.constructOutgoingResponse)(this.message, options);
        this.transaction.receiveResponse(options.statusCode, response.message);
        return response;
    }
    init() {
        const user = {
            loggerFactory: this.loggerFactory,
            onStateChange: (newState) => {
                if (newState === _transactions_transaction_state_js__WEBPACK_IMPORTED_MODULE_3__.TransactionState.Terminated) {
                    // eslint-disable-next-line @typescript-eslint/no-use-before-define
                    this.core.userAgentServers.delete(userAgentServerId);
                    this.dispose();
                }
            },
            onTransportError: (error) => {
                this.logger.error(error.message);
                if (this.delegate && this.delegate.onTransportError) {
                    this.delegate.onTransportError(error);
                }
                else {
                    this.logger.error("User agent server response transport error.");
                }
            }
        };
        const transaction = new this.transactionConstructor(this.message, this.core.transport, user);
        this._transaction = transaction;
        const userAgentServerId = transaction.id;
        this.core.userAgentServers.set(transaction.id, this);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "NonInviteServerTransaction": () => ( NonInviteServerTransaction)
 });
 var _timers_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(37);
 var _server_transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(73);
 var _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(64);



/**
 * @remarks
 * @public
 */
class NonInviteServerTransaction extends _server_transaction_js__WEBPACK_IMPORTED_MODULE_0__.ServerTransaction {
    /**
     * @param request
     * @param transport
     * @param user
     */
    constructor(request, transport, user) {
        super(request, transport, user, _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying, "sip.transaction.nist");
    }
    dispose() {
        if (this.J) {
            clearTimeout(this.J);
            this.J = undefined;
        }
        super.dispose();
    }
    get kind() {
        return "nist";
    }
    /** @param request */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    receiveRequest(request) {
        switch (this.state) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying:
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (!this.lastResponse) {
                    throw new Error("Last response undefined.");
                }
                this.send(this.lastResponse).catch((error) => {
                    this.logTransportError(error, "Failed to send retransmission of provisional response.");
                });
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (!this.lastResponse) {
                    throw new Error("Last response undefined.");
                }
                this.send(this.lastResponse).catch((error) => {
                    this.logTransportError(error, "Failed to send retransmission of final response.");
                });
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                break;
            default:
                throw new Error(`Invalid state ${this.state}`);
        }
    }
    /**
     * @param statusCode
     * @param response
     */
    receiveResponse(statusCode, response) {
        if (statusCode < 100 || statusCode > 699) {
            throw new Error(`Invalid status code ${statusCode}`);
        }
        if (statusCode > 100 && statusCode <= 199) {
            throw new Error("Provisional response other than 100 not allowed.");
        }
        switch (this.state) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying:
                this.lastResponse = response;
                if (statusCode >= 100 && statusCode < 200) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding);
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send provisional response.");
                    });
                    return;
                }
                if (statusCode >= 200 && statusCode <= 699) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send final response.");
                    });
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                this.lastResponse = response;
                if (statusCode >= 200 && statusCode <= 699) {
                    this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed);
                    this.send(response).catch((error) => {
                        this.logTransportError(error, "Failed to send final response.");
                    });
                    return;
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                return;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                break;
            default:
                throw new Error(`Invalid state ${this.state}`);
        }
        const message = `Non-INVITE server transaction received unexpected ${statusCode} response from TU while in state ${this.state}.`;
        this.logger.error(message);
        throw new Error(message);
    }
    onTransportError(error) {
        if (this.user.onTransportError) {
            this.user.onTransportError(error);
        }
        this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated, true);
    }
    typeToString() {
        return "non-INVITE server transaction";
    }
    stateTransition(newState, dueToTransportError = false) {
        const invalidStateTransition = () => {
            throw new Error(`Invalid state transition from ${this.state} to ${newState}`);
        };
        switch (newState) {
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying:
                invalidStateTransition();
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Trying && this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding) {
                    invalidStateTransition();
                }
                break;
            case _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated:
                if (this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Proceeding && this.state !== _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
                    if (!dueToTransportError) {
                        invalidStateTransition();
                    }
                }
                break;
            default:
                invalidStateTransition();
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.J = setTimeout(() => this.timerJ(), _timers_js__WEBPACK_IMPORTED_MODULE_2__.Timers.TIMER_J);
        }
        if (newState === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated) {
            this.dispose();
        }
        this.setState(newState);
    }
    timerJ() {
        this.logger.debug(`Timer J expired for NON-INVITE server transaction ${this.id}.`);
        if (this.state === _transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Completed) {
            this.stateTransition(_transaction_state_js__WEBPACK_IMPORTED_MODULE_1__.TransactionState.Terminated);
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "constructOutgoingResponse": () => ( constructOutgoingResponse)
 });
 var _utils_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(21);

/** @internal */
function constructOutgoingResponse(message, options) {
    const CRLF = "\r\n";
    if (options.statusCode < 100 || options.statusCode > 699) {
        throw new TypeError("Invalid statusCode: " + options.statusCode);
    }
    const reasonPhrase = options.reasonPhrase ? options.reasonPhrase : (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.getReasonPhrase)(options.statusCode);
    let response = "SIP/2.0 " + options.statusCode + " " + reasonPhrase + CRLF;
    if (options.statusCode >= 100 && options.statusCode < 200) {
    }
    if (options.statusCode === 100) {
    }
    const fromHeader = "From: " + message.getHeader("From") + CRLF;
    const callIdHeader = "Call-ID: " + message.callId + CRLF;
    const cSeqHeader = "CSeq: " + message.cseq + " " + message.method + CRLF;
    const viaHeaders = message.getHeaders("via").reduce((previous, current) => {
        return previous + "Via: " + current + CRLF;
    }, "");
    let toHeader = "To: " + message.getHeader("to");
    if (options.statusCode > 100 && !message.parseHeader("to").hasParam("tag")) {
        let toTag = options.toTag;
        if (!toTag) {
            toTag = (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.newTag)();
        }
        toHeader += ";tag=" + toTag;
    }
    toHeader += CRLF;
    let supportedHeader = "";
    if (options.supported) {
        supportedHeader = "Supported: " + options.supported.join(", ") + CRLF;
    }
    let userAgentHeader = "";
    if (options.userAgent) {
        userAgentHeader = "User-Agent: " + options.userAgent + CRLF;
    }
    let extensionHeaders = "";
    if (options.extraHeaders) {
        extensionHeaders = options.extraHeaders.reduce((previous, current) => {
            return previous + current.trim() + CRLF;
        }, "");
    }
    response += viaHeaders;
    response += fromHeader;
    response += toHeader;
    response += cSeqHeader;
    response += callIdHeader;
    response += supportedHeader;
    response += userAgentHeader;
    response += extensionHeaders;
    if (options.body) {
        response += "Content-Type: " + options.body.contentType + CRLF;
        response += "Content-Length: " + (0,_utils_js__WEBPACK_IMPORTED_MODULE_0__.utf8Length)(options.body.content) + CRLF + CRLF;
        response += options.body.content;
    }
    else {
        response += "Content-Length: " + 0 + CRLF + CRLF;
    }
    return { message: response };
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "InfoUserAgentServer": () => ( InfoUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class InfoUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(dialog, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, dialog.userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ReInviteUserAgentServer": () => ( ReInviteUserAgentServer)
 });
 var _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(72);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/**
 * @remarks
 * @public
 */
class ReInviteUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(dialog, message, delegate) {
        super(_transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteServerTransaction, dialog.userAgentCore, message, delegate);
        dialog.reinviteUserAgentServer = this;
        this.dialog = dialog;
    }
    /** @param options */
    accept(options = { statusCode: 200 }) {
        options.extraHeaders = options.extraHeaders || [];
        options.extraHeaders = options.extraHeaders.concat(this.dialog.routeSet.map((route) => `Record-Route: ${route}`));
        const response = super.accept(options);
        const session = this.dialog;
        const result = Object.assign(Object.assign({}, response), { session });
        if (options.body) {
            this.dialog.signalingStateTransition(options.body);
        }
        this.dialog.reConfirm();
        return result;
    }
    /** @param options */
    progress(options = { statusCode: 180 }) {
        const response = super.progress(options);
        const session = this.dialog;
        const result = Object.assign(Object.assign({}, response), { session });
        if (options.body) {
            this.dialog.signalingStateTransition(options.body);
        }
        return result;
    }
    /**
     * @param contacts
     * @param options
     */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    redirect(contacts, options = { statusCode: 302 }) {
        this.dialog.signalingStateRollback();
        this.dialog.reinviteUserAgentServer = undefined;
        throw new Error("Unimplemented.");
    }
    /** @param options */
    reject(options = { statusCode: 488 }) {
        this.dialog.signalingStateRollback();
        this.dialog.reinviteUserAgentServer = undefined;
        return super.reject(options);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "MessageUserAgentServer": () => ( MessageUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class MessageUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, core, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "NotifyUserAgentServer": () => ( NotifyUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


// eslint-disable-next-line @typescript-eslint/no-explicit-any
function instanceOfDialog(object) {
    return object.userAgentCore !== undefined;
}
/** @public */
class NotifyUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    /**
     * @param dialogOrCore
     * @param message
     */
    constructor(dialogOrCore, message, delegate) {
        const userAgentCore = instanceOfDialog(dialogOrCore) ? dialogOrCore.userAgentCore : dialogOrCore;
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "PrackUserAgentServer": () => ( PrackUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class PrackUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(dialog, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, dialog.userAgentCore, message, delegate);
        dialog.signalingStateTransition(message);
        this.dialog = dialog;
    }
    /** @param options */
    accept(options = { statusCode: 200 }) {
        if (options.body) {
            this.dialog.signalingStateTransition(options.body);
        }
        return super.accept(options);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ReferUserAgentServer": () => ( ReferUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


// eslint-disable-next-line @typescript-eslint/no-explicit-any
function instanceOfSessionDialog(object) {
    return object.userAgentCore !== undefined;
}
/** @public */
class ReferUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    /**
     * @param dialogOrCore
     * @param message
     */
    constructor(dialogOrCore, message, delegate) {
        const userAgentCore = instanceOfSessionDialog(dialogOrCore) ? dialogOrCore.userAgentCore : dialogOrCore;
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "PublishUserAgentClient": () => ( PublishUserAgentClient)
 });
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);


/** @public */
class PublishUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteClientTransaction, core, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "RegisterUserAgentClient": () => ( RegisterUserAgentClient)
 });
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);


/** @public */
class RegisterUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteClientTransaction, core, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SubscribeUserAgentClient": () => ( SubscribeUserAgentClient)
 });
 var _dialogs_subscription_dialog_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(94);
 var _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(47);
 var _timers_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(37);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);





/**
 * @remarks
 * @public
 */
class SubscribeUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(core, message, delegate) {
        const event = message.getHeader("Event");
        if (!event) {
            throw new Error("Event undefined");
        }
        const expires = message.getHeader("Expires");
        if (!expires) {
            throw new Error("Expires undefined");
        }
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteClientTransaction, core, message, delegate);
        this.delegate = delegate;
        this.subscriberId = message.callId + message.fromTag + event;
        this.subscriptionExpiresRequested = this.subscriptionExpires = Number(expires);
        this.subscriptionEvent = event;
        this.subscriptionState = _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.NotifyWait;
        this.waitNotifyStart();
    }
    dispose() {
        super.dispose();
    }
    /** @param uas */
    onNotify(uas) {
        const event = uas.message.parseHeader("Event").event;
        if (!event || event !== this.subscriptionEvent) {
            this.logger.warn(`Failed to parse event.`);
            uas.reject({ statusCode: 489 });
            return;
        }
        const subscriptionState = uas.message.parseHeader("Subscription-State");
        if (!subscriptionState || !subscriptionState.state) {
            this.logger.warn("Failed to parse subscription state.");
            uas.reject({ statusCode: 489 });
            return;
        }
        const state = subscriptionState.state;
        switch (state) {
            case "pending":
                break;
            case "active":
                break;
            case "terminated":
                break;
            default:
                this.logger.warn(`Invalid subscription state ${state}`);
                uas.reject({ statusCode: 489 });
                return;
        }
        if (state !== "terminated") {
            const contact = uas.message.parseHeader("contact");
            if (!contact) {
                this.logger.warn("Failed to parse contact.");
                uas.reject({ statusCode: 489 });
                return;
            }
        }
        if (this.dialog) {
            throw new Error("Dialog already created. This implementation only supports install of single subscriptions.");
        }
        this.waitNotifyStop();
        this.subscriptionExpires = subscriptionState.expires
            ? Math.min(this.subscriptionExpires, Math.max(subscriptionState.expires, 0))
            : this.subscriptionExpires;
        switch (state) {
            case "pending":
                this.subscriptionState = _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Pending;
                break;
            case "active":
                this.subscriptionState = _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Active;
                break;
            case "terminated":
                this.subscriptionState = _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Terminated;
                break;
            default:
                throw new Error(`Unrecognized state ${state}.`);
        }
        if (this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionState.Terminated) {
            const dialogState = _dialogs_subscription_dialog_js__WEBPACK_IMPORTED_MODULE_3__.SubscriptionDialog.initialDialogStateForSubscription(this.message, uas.message);
            this.dialog = new _dialogs_subscription_dialog_js__WEBPACK_IMPORTED_MODULE_3__.SubscriptionDialog(this.subscriptionEvent, this.subscriptionExpires, this.subscriptionState, this.core, dialogState);
        }
        if (this.delegate && this.delegate.onNotify) {
            const request = uas;
            const subscription = this.dialog;
            this.delegate.onNotify({ request, subscription });
        }
        else {
            uas.accept();
        }
    }
    waitNotifyStart() {
        if (!this.N) {
            this.core.subscribers.set(this.subscriberId, this);
            this.N = setTimeout(() => this.timerN(), _timers_js__WEBPACK_IMPORTED_MODULE_4__.Timers.TIMER_N);
        }
    }
    waitNotifyStop() {
        if (this.N) {
            this.core.subscribers.delete(this.subscriberId);
            clearTimeout(this.N);
            this.N = undefined;
        }
    }
    /** @param message */
    receiveResponse(message) {
        if (!this.authenticationGuard(message)) {
            return;
        }
        if (message.statusCode && message.statusCode >= 200 && message.statusCode < 300) {
            const expires = message.getHeader("Expires");
            if (!expires) {
                this.logger.warn("Expires header missing in a 200-class response to SUBSCRIBE");
            }
            else {
                const subscriptionExpiresReceived = Number(expires);
                if (subscriptionExpiresReceived > this.subscriptionExpiresRequested) {
                    this.logger.warn("Expires header in a 200-class response to SUBSCRIBE with a higher value than the one in the request");
                }
                if (subscriptionExpiresReceived < this.subscriptionExpires) {
                    this.subscriptionExpires = subscriptionExpiresReceived;
                }
            }
            if (this.dialog) {
                if (this.dialog.subscriptionExpires > this.subscriptionExpires) {
                    this.dialog.subscriptionExpires = this.subscriptionExpires;
                }
            }
        }
        if (message.statusCode && message.statusCode >= 300 && message.statusCode < 700) {
            this.waitNotifyStop();
        }
        super.receiveResponse(message);
    }
    timerN() {
        this.logger.warn(`Timer N expired for SUBSCRIBE user agent client. Timed out waiting for NOTIFY.`);
        this.waitNotifyStop();
        if (this.delegate && this.delegate.onNotifyTimeout) {
            this.delegate.onNotifyTimeout();
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SubscriptionDialog": () => ( SubscriptionDialog)
 });
 var _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(26);
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(30);
 var _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(47);
 var _timers_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(37);
 var _user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(29);
 var _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(88);
 var _user_agents_re_subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(95);
 var _dialog_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(70);








/**
 * @remarks
 * @public
 */
class SubscriptionDialog extends _dialog_js__WEBPACK_IMPORTED_MODULE_0__.Dialog {
    constructor(subscriptionEvent, subscriptionExpires, subscriptionState, core, state, delegate) {
        super(core, state);
        this.delegate = delegate;
        this._autoRefresh = false;
        this._subscriptionEvent = subscriptionEvent;
        this._subscriptionExpires = subscriptionExpires;
        this._subscriptionExpiresInitial = subscriptionExpires;
        this._subscriptionExpiresLastSet = Math.floor(Date.now() / 1000);
        this._subscriptionRefresh = undefined;
        this._subscriptionRefreshLastSet = undefined;
        this._subscriptionState = subscriptionState;
        this.logger = core.loggerFactory.getLogger("sip.subscribe-dialog");
        this.logger.log(`SUBSCRIBE dialog ${this.id} constructed`);
    }
    /**
     * @param outgoingRequestMessage
     * @param incomingResponseMessage
     */
    static initialDialogStateForSubscription(outgoingSubscribeRequestMessage, incomingNotifyRequestMessage) {
        const secure = false;
        const routeSet = incomingNotifyRequestMessage.getHeaders("record-route");
        const contact = incomingNotifyRequestMessage.parseHeader("contact");
        if (!contact) {
            throw new Error("Contact undefined.");
        }
        if (!(contact instanceof _grammar_name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader)) {
            throw new Error("Contact not instance of NameAddrHeader.");
        }
        const remoteTarget = contact.uri;
        const localSequenceNumber = outgoingSubscribeRequestMessage.cseq;
        const remoteSequenceNumber = undefined;
        const callId = outgoingSubscribeRequestMessage.callId;
        const localTag = outgoingSubscribeRequestMessage.fromTag;
        const remoteTag = incomingNotifyRequestMessage.fromTag;
        if (!callId) {
            throw new Error("Call id undefined.");
        }
        if (!localTag) {
            throw new Error("From tag undefined.");
        }
        if (!remoteTag) {
            throw new Error("To tag undefined.");
        }
        if (!outgoingSubscribeRequestMessage.from) {
            throw new Error("From undefined.");
        }
        if (!outgoingSubscribeRequestMessage.to) {
            throw new Error("To undefined.");
        }
        const localURI = outgoingSubscribeRequestMessage.from.uri;
        const remoteURI = outgoingSubscribeRequestMessage.to.uri;
        const early = false;
        const dialogState = {
            id: callId + localTag + remoteTag,
            early,
            callId,
            localTag,
            remoteTag,
            localSequenceNumber,
            remoteSequenceNumber,
            localURI,
            remoteURI,
            remoteTarget,
            routeSet,
            secure
        };
        return dialogState;
    }
    dispose() {
        super.dispose();
        if (this.N) {
            clearTimeout(this.N);
            this.N = undefined;
        }
        this.refreshTimerClear();
        this.logger.log(`SUBSCRIBE dialog ${this.id} destroyed`);
    }
    get autoRefresh() {
        return this._autoRefresh;
    }
    set autoRefresh(autoRefresh) {
        this._autoRefresh = true;
        this.refreshTimerSet();
    }
    get subscriptionEvent() {
        return this._subscriptionEvent;
    }
    get subscriptionExpires() {
        const secondsSinceLastSet = Math.floor(Date.now() / 1000) - this._subscriptionExpiresLastSet;
        const secondsUntilExpires = this._subscriptionExpires - secondsSinceLastSet;
        return Math.max(secondsUntilExpires, 0);
    }
    set subscriptionExpires(expires) {
        if (expires < 0) {
            throw new Error("Expires must be greater than or equal to zero.");
        }
        this._subscriptionExpires = expires;
        this._subscriptionExpiresLastSet = Math.floor(Date.now() / 1000);
        if (this.autoRefresh) {
            const refresh = this.subscriptionRefresh;
            if (refresh === undefined || refresh >= expires) {
                this.refreshTimerSet();
            }
        }
    }
    get subscriptionExpiresInitial() {
        return this._subscriptionExpiresInitial;
    }
    get subscriptionRefresh() {
        if (this._subscriptionRefresh === undefined || this._subscriptionRefreshLastSet === undefined) {
            return undefined;
        }
        const secondsSinceLastSet = Math.floor(Date.now() / 1000) - this._subscriptionRefreshLastSet;
        const secondsUntilExpires = this._subscriptionRefresh - secondsSinceLastSet;
        return Math.max(secondsUntilExpires, 0);
    }
    get subscriptionState() {
        return this._subscriptionState;
    }
    /** @param message */
    receiveRequest(message) {
        this.logger.log(`SUBSCRIBE dialog ${this.id} received ${message.method} request`);
        if (!this.sequenceGuard(message)) {
            this.logger.log(`SUBSCRIBE dialog ${this.id} rejected out of order ${message.method} request.`);
            return;
        }
        super.receiveRequest(message);
        switch (message.method) {
            case _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_2__.C.NOTIFY:
                this.onNotify(message);
                break;
            default:
                this.logger.log(`SUBSCRIBE dialog ${this.id} received unimplemented ${message.method} request`);
                this.core.replyStateless(message, { statusCode: 501 });
                break;
        }
    }
    refresh() {
        const allowHeader = "Allow: " + _user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_3__.AllowedMethods.toString();
        const options = {};
        options.extraHeaders = (options.extraHeaders || []).slice();
        options.extraHeaders.push(allowHeader);
        options.extraHeaders.push("Event: " + this.subscriptionEvent);
        options.extraHeaders.push("Expires: " + this.subscriptionExpiresInitial);
        options.extraHeaders.push("Contact: " + this.core.configuration.contact.toString());
        return this.subscribe(undefined, options);
    }
    /**
     * @param delegate
     * @param options
     */
    subscribe(delegate, options = {}) {
        var _a;
        if (this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending && this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Active) {
            throw new Error(`Invalid state ${this.subscriptionState}. May only re-subscribe while in state "pending" or "active".`);
        }
        this.logger.log(`SUBSCRIBE dialog ${this.id} sending SUBSCRIBE request`);
        const uac = new _user_agents_re_subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_5__.ReSubscribeUserAgentClient(this, delegate, options);
        if (this.N) {
            clearTimeout(this.N);
            this.N = undefined;
        }
        if (!((_a = options.extraHeaders) === null || _a === void 0 ? void 0 : _a.includes("Expires: 0"))) {
            this.N = setTimeout(() => this.timerN(), _timers_js__WEBPACK_IMPORTED_MODULE_6__.Timers.TIMER_N);
        }
        return uac;
    }
    terminate() {
        this.stateTransition(_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Terminated);
        this.onTerminated();
    }
    unsubscribe() {
        const allowHeader = "Allow: " + _user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_3__.AllowedMethods.toString();
        const options = {};
        options.extraHeaders = (options.extraHeaders || []).slice();
        options.extraHeaders.push(allowHeader);
        options.extraHeaders.push("Event: " + this.subscriptionEvent);
        options.extraHeaders.push("Expires: 0");
        options.extraHeaders.push("Contact: " + this.core.configuration.contact.toString());
        return this.subscribe(undefined, options);
    }
    /** @param message */
    onNotify(message) {
        const event = message.parseHeader("Event").event;
        if (!event || event !== this.subscriptionEvent) {
            this.core.replyStateless(message, { statusCode: 489 });
            return;
        }
        if (this.N) {
            clearTimeout(this.N);
            this.N = undefined;
        }
        const subscriptionState = message.parseHeader("Subscription-State");
        if (!subscriptionState || !subscriptionState.state) {
            this.core.replyStateless(message, { statusCode: 489 });
            return;
        }
        const state = subscriptionState.state;
        const expires = subscriptionState.expires ? Math.max(subscriptionState.expires, 0) : undefined;
        switch (state) {
            case "pending":
                this.stateTransition(_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending, expires);
                break;
            case "active":
                this.stateTransition(_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Active, expires);
                break;
            case "terminated":
                this.stateTransition(_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Terminated, expires);
                break;
            default:
                this.logger.warn("Unrecognized subscription state.");
                break;
        }
        const uas = new _user_agents_notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_7__.NotifyUserAgentServer(this, message);
        if (this.delegate && this.delegate.onNotify) {
            this.delegate.onNotify(uas);
        }
        else {
            uas.accept();
        }
    }
    onRefresh(request) {
        if (this.delegate && this.delegate.onRefresh) {
            this.delegate.onRefresh(request);
        }
    }
    onTerminated() {
        if (this.delegate && this.delegate.onTerminated) {
            this.delegate.onTerminated();
        }
    }
    refreshTimerClear() {
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = undefined;
        }
    }
    refreshTimerSet() {
        this.refreshTimerClear();
        if (this.autoRefresh && this.subscriptionExpires > 0) {
            const refresh = this.subscriptionExpires * 900;
            this._subscriptionRefresh = Math.floor(refresh / 1000);
            this._subscriptionRefreshLastSet = Math.floor(Date.now() / 1000);
            this.refreshTimer = setTimeout(() => {
                this.refreshTimer = undefined;
                this._subscriptionRefresh = undefined;
                this._subscriptionRefreshLastSet = undefined;
                this.onRefresh(this.refresh());
            }, refresh);
        }
    }
    stateTransition(newState, newExpires) {
        const invalidStateTransition = () => {
            this.logger.warn(`Invalid subscription state transition from ${this.subscriptionState} to ${newState}`);
        };
        switch (newState) {
            case _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Initial:
                invalidStateTransition();
                return;
            case _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.NotifyWait:
                invalidStateTransition();
                return;
            case _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending:
                if (this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.NotifyWait &&
                    this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending) {
                    invalidStateTransition();
                    return;
                }
                break;
            case _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Active:
                if (this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.NotifyWait &&
                    this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending &&
                    this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Active) {
                    invalidStateTransition();
                    return;
                }
                break;
            case _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Terminated:
                if (this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.NotifyWait &&
                    this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending &&
                    this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Active) {
                    invalidStateTransition();
                    return;
                }
                break;
            default:
                invalidStateTransition();
                return;
        }
        if (newState === _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Pending) {
            if (newExpires) {
                this.subscriptionExpires = newExpires;
            }
        }
        if (newState === _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Active) {
            if (newExpires) {
                this.subscriptionExpires = newExpires;
            }
        }
        if (newState === _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Terminated) {
            this.dispose();
        }
        this._subscriptionState = newState;
    }
    timerN() {
        this.logger.warn(`Timer N expired for SUBSCRIBE dialog. Timed out waiting for NOTIFY.`);
        if (this.subscriptionState !== _subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Terminated) {
            this.stateTransition(_subscription_subscription_js__WEBPACK_IMPORTED_MODULE_4__.SubscriptionState.Terminated);
            this.onTerminated();
        }
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ReSubscribeUserAgentClient": () => ( ReSubscribeUserAgentClient)
 });
 var _messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(30);
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);



/** @public */
class ReSubscribeUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(dialog, delegate, options) {
        const message = dialog.createOutgoingRequestMessage(_messages_methods_constants_js__WEBPACK_IMPORTED_MODULE_1__.C.SUBSCRIBE, options);
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_2__.NonInviteClientTransaction, dialog.userAgentCore, message, delegate);
        this.dialog = dialog;
    }
    waitNotifyStop() {
        return;
    }
    /** @param message */
    receiveResponse(message) {
        if (message.statusCode && message.statusCode >= 200 && message.statusCode < 300) {
            const expires = message.getHeader("Expires");
            if (!expires) {
                this.logger.warn("Expires header missing in a 200-class response to SUBSCRIBE");
            }
            else {
                const subscriptionExpiresReceived = Number(expires);
                if (this.dialog.subscriptionExpires > subscriptionExpiresReceived) {
                    this.dialog.subscriptionExpires = subscriptionExpiresReceived;
                }
            }
        }
        if (message.statusCode && message.statusCode >= 400 && message.statusCode < 700) {
            const errorCodes = [404, 405, 410, 416, 480, 481, 482, 483, 484, 485, 489, 501, 604];
            if (errorCodes.includes(message.statusCode)) {
                this.dialog.terminate();
            }
        }
        super.receiveResponse(message);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "InviteUserAgentServer": () => ( InviteUserAgentServer)
 });
 var _dialogs_dialog_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(70);
 var _dialogs_session_dialog_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(71);
 var _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(36);
 var _session_session_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(31);
 var _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(72);
 var _user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(29);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);







/**
 * @remarks
 * @public
 */
class InviteUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(core, message, delegate) {
        super(_transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteServerTransaction, core, message, delegate);
        this.core = core;
    }
    dispose() {
        if (this.earlyDialog) {
            this.earlyDialog.dispose();
        }
        super.dispose();
    }
    /** @param options */
    accept(options = { statusCode: 200 }) {
        if (!this.acceptable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_2__.TransactionStateError(`${this.message.method} not acceptable in state ${this.transaction.state}.`);
        }
        if (!this.confirmedDialog) {
            if (this.earlyDialog) {
                this.earlyDialog.confirm();
                this.confirmedDialog = this.earlyDialog;
                this.earlyDialog = undefined;
            }
            else {
                const transaction = this.transaction;
                if (!(transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteServerTransaction)) {
                    throw new Error("Transaction not instance of InviteClientTransaction.");
                }
                const state = _dialogs_dialog_js__WEBPACK_IMPORTED_MODULE_3__.Dialog.initialDialogStateForUserAgentServer(this.message, this.toTag);
                this.confirmedDialog = new _dialogs_session_dialog_js__WEBPACK_IMPORTED_MODULE_4__.SessionDialog(transaction, this.core, state);
            }
        }
        const recordRouteHeader = this.message.getHeaders("record-route").map((header) => `Record-Route: ${header}`);
        const contactHeader = `Contact: ${this.core.configuration.contact.toString()}`;
        const allowHeader = "Allow: " + _user_agent_core_allowed_methods_js__WEBPACK_IMPORTED_MODULE_5__.AllowedMethods.toString();
        if (!options.body) {
            if (this.confirmedDialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Stable) {
                options.body = this.confirmedDialog.answer;
            }
            else if (this.confirmedDialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Initial ||
                this.confirmedDialog.signalingState === _session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.HaveRemoteOffer) {
                throw new Error("Response must have a body.");
            }
        }
        options.statusCode = options.statusCode || 200;
        options.extraHeaders = options.extraHeaders || [];
        options.extraHeaders = options.extraHeaders.concat(recordRouteHeader);
        options.extraHeaders.push(allowHeader);
        options.extraHeaders.push(contactHeader);
        const response = super.accept(options);
        const session = this.confirmedDialog;
        const result = Object.assign(Object.assign({}, response), { session });
        if (options.body) {
            if (this.confirmedDialog.signalingState !== _session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Stable) {
                this.confirmedDialog.signalingStateTransition(options.body);
            }
        }
        return result;
    }
    /** @param options */
    progress(options = { statusCode: 180 }) {
        if (!this.progressable) {
            throw new _exceptions_transaction_state_error_js__WEBPACK_IMPORTED_MODULE_2__.TransactionStateError(`${this.message.method} not progressable in state ${this.transaction.state}.`);
        }
        if (!this.earlyDialog) {
            const transaction = this.transaction;
            if (!(transaction instanceof _transactions_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteServerTransaction)) {
                throw new Error("Transaction not instance of InviteClientTransaction.");
            }
            const state = _dialogs_dialog_js__WEBPACK_IMPORTED_MODULE_3__.Dialog.initialDialogStateForUserAgentServer(this.message, this.toTag, true);
            this.earlyDialog = new _dialogs_session_dialog_js__WEBPACK_IMPORTED_MODULE_4__.SessionDialog(transaction, this.core, state);
        }
        const recordRouteHeader = this.message.getHeaders("record-route").map((header) => `Record-Route: ${header}`);
        const contactHeader = `Contact: ${this.core.configuration.contact}`;
        options.extraHeaders = options.extraHeaders || [];
        options.extraHeaders = options.extraHeaders.concat(recordRouteHeader);
        options.extraHeaders.push(contactHeader);
        const response = super.progress(options);
        const session = this.earlyDialog;
        const result = Object.assign(Object.assign({}, response), { session });
        if (options.body) {
            if (this.earlyDialog.signalingState !== _session_session_js__WEBPACK_IMPORTED_MODULE_6__.SignalingState.Stable) {
                this.earlyDialog.signalingStateTransition(options.body);
            }
        }
        return result;
    }
    /**
     * @param contacts
     * @param options
     */
    redirect(contacts, options = { statusCode: 302 }) {
        return super.redirect(contacts, options);
    }
    /** @param options */
    reject(options = { statusCode: 486 }) {
        return super.reject(options);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "RegisterUserAgentServer": () => ( RegisterUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class RegisterUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, core, message, delegate);
        this.core = core;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SubscribeUserAgentServer": () => ( SubscribeUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class SubscribeUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, core, message, delegate);
        this.core = core;
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Parser": () => ( Parser)
 });
 var _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(22);
 var _incoming_request_message_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(19);
 var _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(27);
/* eslint-disable no-inner-declarations */
/* eslint-disable @typescript-eslint/no-namespace */



/** @internal */
var Parser;
(function (Parser) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function getHeader(data, headerStart) {
        let start = headerStart;
        let end = 0;
        let partialEnd = 0;
        if (data.substring(start, start + 2).match(/(^\r\n)/)) {
            return -2;
        }
        while (end === 0) {
            partialEnd = data.indexOf("\r\n", start);
            if (partialEnd === -1) {
                return partialEnd;
            }
            if (!data.substring(partialEnd + 2, partialEnd + 4).match(/(^\r\n)/) &&
                data.charAt(partialEnd + 2).match(/(^\s+)/)) {
                start = partialEnd + 2;
            }
            else {
                end = partialEnd;
            }
        }
        return end;
    }
    Parser.getHeader = getHeader;
    function parseHeader(message,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    data, headerStart, headerEnd) {
        const hcolonIndex = data.indexOf(":", headerStart);
        const headerName = data.substring(headerStart, hcolonIndex).trim();
        const headerValue = data.substring(hcolonIndex + 1, headerEnd).trim();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let parsed;
        switch (headerName.toLowerCase()) {
            case "via":
            case "v":
                message.addHeader("via", headerValue);
                if (message.getHeaders("via").length === 1) {
                    parsed = message.parseHeader("Via");
                    if (parsed) {
                        message.via = parsed;
                        message.viaBranch = parsed.branch;
                    }
                }
                else {
                    parsed = 0;
                }
                break;
            case "from":
            case "f":
                message.setHeader("from", headerValue);
                parsed = message.parseHeader("from");
                if (parsed) {
                    message.from = parsed;
                    message.fromTag = parsed.getParam("tag");
                }
                break;
            case "to":
            case "t":
                message.setHeader("to", headerValue);
                parsed = message.parseHeader("to");
                if (parsed) {
                    message.to = parsed;
                    message.toTag = parsed.getParam("tag");
                }
                break;
            case "record-route":
                parsed = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__.Grammar.parse(headerValue, "Record_Route");
                if (parsed === -1) {
                    parsed = undefined;
                    break;
                }
                if (!(parsed instanceof Array)) {
                    parsed = undefined;
                    break;
                }
                parsed.forEach((header) => {
                    message.addHeader("record-route", headerValue.substring(header.position, header.offset));
                    message.headers["Record-Route"][message.getHeaders("record-route").length - 1].parsed = header.parsed;
                });
                break;
            case "call-id":
            case "i":
                message.setHeader("call-id", headerValue);
                parsed = message.parseHeader("call-id");
                if (parsed) {
                    message.callId = headerValue;
                }
                break;
            case "contact":
            case "m":
                parsed = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__.Grammar.parse(headerValue, "Contact");
                if (parsed === -1) {
                    parsed = undefined;
                    break;
                }
                if (!(parsed instanceof Array)) {
                    parsed = undefined;
                    break;
                }
                parsed.forEach((header) => {
                    message.addHeader("contact", headerValue.substring(header.position, header.offset));
                    message.headers.Contact[message.getHeaders("contact").length - 1].parsed = header.parsed;
                });
                break;
            case "content-length":
            case "l":
                message.setHeader("content-length", headerValue);
                parsed = message.parseHeader("content-length");
                break;
            case "content-type":
            case "c":
                message.setHeader("content-type", headerValue);
                parsed = message.parseHeader("content-type");
                break;
            case "cseq":
                message.setHeader("cseq", headerValue);
                parsed = message.parseHeader("cseq");
                if (parsed) {
                    message.cseq = parsed.value;
                }
                if (message instanceof _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_1__.IncomingResponseMessage) {
                    message.method = parsed.method;
                }
                break;
            case "max-forwards":
                message.setHeader("max-forwards", headerValue);
                parsed = message.parseHeader("max-forwards");
                break;
            case "www-authenticate":
                message.setHeader("www-authenticate", headerValue);
                parsed = message.parseHeader("www-authenticate");
                break;
            case "proxy-authenticate":
                message.setHeader("proxy-authenticate", headerValue);
                parsed = message.parseHeader("proxy-authenticate");
                break;
            case "refer-to":
            case "r":
                message.setHeader("refer-to", headerValue);
                parsed = message.parseHeader("refer-to");
                if (parsed) {
                    message.referTo = parsed;
                }
                break;
            default:
                message.addHeader(headerName.toLowerCase(), headerValue);
                parsed = 0;
        }
        if (parsed === undefined) {
            return {
                error: "error parsing header '" + headerName + "'"
            };
        }
        else {
            return true;
        }
    }
    Parser.parseHeader = parseHeader;
    function parseMessage(data, logger) {
        let headerStart = 0;
        let headerEnd = data.indexOf("\r\n");
        if (headerEnd === -1) {
            logger.warn("no CRLF found, not a SIP message, discarded");
            return;
        }
        const firstLine = data.substring(0, headerEnd);
        const parsed = _grammar_grammar_js__WEBPACK_IMPORTED_MODULE_0__.Grammar.parse(firstLine, "Request_Response");
        let message;
        if (parsed === -1) {
            logger.warn('error parsing first line of SIP message: "' + firstLine + '"');
            return;
        }
        else if (!parsed.status_code) {
            message = new _incoming_request_message_js__WEBPACK_IMPORTED_MODULE_2__.IncomingRequestMessage();
            message.method = parsed.method;
            message.ruri = parsed.uri;
        }
        else {
            message = new _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_1__.IncomingResponseMessage();
            message.statusCode = parsed.status_code;
            message.reasonPhrase = parsed.reason_phrase;
        }
        message.data = data;
        headerStart = headerEnd + 2;
        let bodyStart;
        // eslint-disable-next-line no-constant-condition
        while (true) {
            headerEnd = getHeader(data, headerStart);
            if (headerEnd === -2) {
                bodyStart = headerStart + 2;
                break;
            }
            else if (headerEnd === -1) {
                logger.error("malformed message");
                return;
            }
            const parsedHeader = parseHeader(message, data, headerStart, headerEnd);
            if (parsedHeader && parsedHeader !== true) {
                logger.error(parsedHeader.error);
                return;
            }
            headerStart = headerEnd + 2;
        }
        if (message.hasHeader("content-length")) {
            message.body = data.substr(bodyStart, Number(message.getHeader("content-length")));
        }
        else {
            message.body = data.substring(bodyStart);
        }
        return message;
    }
    Parser.parseMessage = parseMessage;
})(Parser = Parser || (Parser = {}));


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Grammar": () => ( _grammar_js__WEBPACK_IMPORTED_MODULE_0__.Grammar),
   "NameAddrHeader": () => ( _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__.NameAddrHeader),
   "Parameters": () => ( _parameters_js__WEBPACK_IMPORTED_MODULE_2__.Parameters),
   "URI": () => ( _uri_js__WEBPACK_IMPORTED_MODULE_3__.URI),
   "equivalentURI": () => ( _uri_js__WEBPACK_IMPORTED_MODULE_3__.equivalentURI)
 });
 var _grammar_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(22);
 var _name_addr_header_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(26);
 var _parameters_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(25);
 var _uri_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(24);






 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ByeUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ByeUserAgentClient),
   "ByeUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ByeUserAgentServer),
   "C": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.C),
   "CancelUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.CancelUserAgentClient),
   "ClientTransaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.ClientTransaction),
   "Dialog": () => ( _dialogs_index_js__WEBPACK_IMPORTED_MODULE_0__.Dialog),
   "DigestAuthentication": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.DigestAuthentication),
   "Exception": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_1__.Exception),
   "Grammar": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_10__.Grammar),
   "IncomingMessage": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.IncomingMessage),
   "IncomingRequestMessage": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.IncomingRequestMessage),
   "IncomingResponseMessage": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.IncomingResponseMessage),
   "InfoUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.InfoUserAgentClient),
   "InfoUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.InfoUserAgentServer),
   "InviteClientTransaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.InviteClientTransaction),
   "InviteServerTransaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.InviteServerTransaction),
   "InviteUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.InviteUserAgentClient),
   "InviteUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.InviteUserAgentServer),
   "Levels": () => ( _log_index_js__WEBPACK_IMPORTED_MODULE_2__.Levels),
   "Logger": () => ( _log_index_js__WEBPACK_IMPORTED_MODULE_2__.Logger),
   "LoggerFactory": () => ( _log_index_js__WEBPACK_IMPORTED_MODULE_2__.LoggerFactory),
   "MessageUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.MessageUserAgentClient),
   "MessageUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.MessageUserAgentServer),
   "NameAddrHeader": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_10__.NameAddrHeader),
   "NonInviteClientTransaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.NonInviteClientTransaction),
   "NonInviteServerTransaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.NonInviteServerTransaction),
   "NotifyUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.NotifyUserAgentClient),
   "NotifyUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.NotifyUserAgentServer),
   "OutgoingRequestMessage": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.OutgoingRequestMessage),
   "Parameters": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_10__.Parameters),
   "Parser": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.Parser),
   "PrackUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.PrackUserAgentClient),
   "PrackUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.PrackUserAgentServer),
   "PublishUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.PublishUserAgentClient),
   "ReInviteUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ReInviteUserAgentClient),
   "ReInviteUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ReInviteUserAgentServer),
   "ReSubscribeUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ReSubscribeUserAgentClient),
   "ReSubscribeUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ReSubscribeUserAgentServer),
   "ReferUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ReferUserAgentClient),
   "ReferUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.ReferUserAgentServer),
   "RegisterUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.RegisterUserAgentClient),
   "RegisterUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.RegisterUserAgentServer),
   "ServerTransaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.ServerTransaction),
   "SessionDialog": () => ( _dialogs_index_js__WEBPACK_IMPORTED_MODULE_0__.SessionDialog),
   "SessionState": () => ( _session_index_js__WEBPACK_IMPORTED_MODULE_4__.SessionState),
   "SignalingState": () => ( _session_index_js__WEBPACK_IMPORTED_MODULE_4__.SignalingState),
   "SubscribeUserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.SubscribeUserAgentClient),
   "SubscribeUserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.SubscribeUserAgentServer),
   "SubscriptionDialog": () => ( _dialogs_index_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionDialog),
   "SubscriptionState": () => ( _subscription_index_js__WEBPACK_IMPORTED_MODULE_5__.SubscriptionState),
   "Timers": () => ( _timers_js__WEBPACK_IMPORTED_MODULE_9__.Timers),
   "Transaction": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.Transaction),
   "TransactionState": () => ( _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__.TransactionState),
   "TransactionStateError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError),
   "TransportError": () => ( _exceptions_index_js__WEBPACK_IMPORTED_MODULE_1__.TransportError),
   "URI": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_10__.URI),
   "UserAgentClient": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.UserAgentClient),
   "UserAgentCore": () => ( _user_agent_core_index_js__WEBPACK_IMPORTED_MODULE_7__.UserAgentCore),
   "UserAgentServer": () => ( _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__.UserAgentServer),
   "constructOutgoingResponse": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.constructOutgoingResponse),
   "equivalentURI": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_10__.equivalentURI),
   "fromBodyLegacy": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.fromBodyLegacy),
   "getBody": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.getBody),
   "isBody": () => ( _messages_index_js__WEBPACK_IMPORTED_MODULE_3__.isBody)
 });
 var _dialogs_index_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(102);
 var _exceptions_index_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(103);
 var _log_index_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(104);
 var _messages_index_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(105);
 var _session_index_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(107);
 var _subscription_index_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(108);
 var _transactions_index_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(109);
 var _user_agent_core_index_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(110);
 var _user_agents_index_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(111);
 var _timers_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(37);
 var _grammar_index_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(100);














 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Dialog": () => ( _dialog_js__WEBPACK_IMPORTED_MODULE_0__.Dialog),
   "SessionDialog": () => ( _session_dialog_js__WEBPACK_IMPORTED_MODULE_1__.SessionDialog),
   "SubscriptionDialog": () => ( _subscription_dialog_js__WEBPACK_IMPORTED_MODULE_2__.SubscriptionDialog)
 });
 var _dialog_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(70);
 var _session_dialog_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(71);
 var _subscription_dialog_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(94);






 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Exception": () => ( _exception_js__WEBPACK_IMPORTED_MODULE_0__.Exception),
   "TransactionStateError": () => ( _transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__.TransactionStateError),
   "TransportError": () => ( _transport_error_js__WEBPACK_IMPORTED_MODULE_2__.TransportError)
 });
 var _exception_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(5);
 var _transaction_state_error_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(36);
 var _transport_error_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(68);





 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Levels": () => ( _levels_js__WEBPACK_IMPORTED_MODULE_0__.Levels),
   "Logger": () => ( _logger_js__WEBPACK_IMPORTED_MODULE_2__.Logger),
   "LoggerFactory": () => ( _logger_factory_js__WEBPACK_IMPORTED_MODULE_1__.LoggerFactory)
 });
 var _levels_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(52);
 var _logger_factory_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(51);
 var _logger_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(53);





 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "C": () => ( _methods_index_js__WEBPACK_IMPORTED_MODULE_0__.C),
   "DigestAuthentication": () => ( _digest_authentication_js__WEBPACK_IMPORTED_MODULE_2__.DigestAuthentication),
   "IncomingMessage": () => ( _incoming_message_js__WEBPACK_IMPORTED_MODULE_3__.IncomingMessage),
   "IncomingRequestMessage": () => ( _incoming_request_message_js__WEBPACK_IMPORTED_MODULE_4__.IncomingRequestMessage),
   "IncomingResponseMessage": () => ( _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_5__.IncomingResponseMessage),
   "OutgoingRequestMessage": () => ( _outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_6__.OutgoingRequestMessage),
   "Parser": () => ( _parser_js__WEBPACK_IMPORTED_MODULE_8__.Parser),
   "constructOutgoingResponse": () => ( _outgoing_response_js__WEBPACK_IMPORTED_MODULE_7__.constructOutgoingResponse),
   "fromBodyLegacy": () => ( _body_js__WEBPACK_IMPORTED_MODULE_1__.fromBodyLegacy),
   "getBody": () => ( _body_js__WEBPACK_IMPORTED_MODULE_1__.getBody),
   "isBody": () => ( _body_js__WEBPACK_IMPORTED_MODULE_1__.isBody)
 });
 var _methods_index_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(106);
 var _body_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(18);
 var _digest_authentication_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(59);
 var _incoming_message_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(20);
 var _incoming_request_message_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(19);
 var _incoming_response_message_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(27);
 var _outgoing_request_message_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(28);
 var _outgoing_response_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(84);
 var _parser_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(99);














 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "C": () => ( _constants_js__WEBPACK_IMPORTED_MODULE_0__.C)
 });
 var _constants_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(30);















 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionState": () => ( _session_js__WEBPACK_IMPORTED_MODULE_0__.SessionState),
   "SignalingState": () => ( _session_js__WEBPACK_IMPORTED_MODULE_0__.SignalingState)
 });
 var _session_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(31);




 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SubscriptionState": () => ( _subscription_js__WEBPACK_IMPORTED_MODULE_0__.SubscriptionState)
 });
 var _subscription_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(47);




 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ClientTransaction": () => ( _client_transaction_js__WEBPACK_IMPORTED_MODULE_0__.ClientTransaction),
   "InviteClientTransaction": () => ( _invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.InviteClientTransaction),
   "InviteServerTransaction": () => ( _invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__.InviteServerTransaction),
   "NonInviteClientTransaction": () => ( _non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_3__.NonInviteClientTransaction),
   "NonInviteServerTransaction": () => ( _non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__.NonInviteServerTransaction),
   "ServerTransaction": () => ( _server_transaction_js__WEBPACK_IMPORTED_MODULE_5__.ServerTransaction),
   "Transaction": () => ( _transaction_js__WEBPACK_IMPORTED_MODULE_7__.Transaction),
   "TransactionState": () => ( _transaction_state_js__WEBPACK_IMPORTED_MODULE_6__.TransactionState)
 });
 var _client_transaction_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(66);
 var _invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(69);
 var _invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(72);
 var _non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(65);
 var _non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(83);
 var _server_transaction_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(73);
 var _transaction_state_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(64);
 var _transaction_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(67);












 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "UserAgentCore": () => ( _user_agent_core_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentCore)
 });
 var _user_agent_core_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(61);





 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ByeUserAgentClient": () => ( _bye_user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.ByeUserAgentClient),
   "ByeUserAgentServer": () => ( _bye_user_agent_server_js__WEBPACK_IMPORTED_MODULE_1__.ByeUserAgentServer),
   "CancelUserAgentClient": () => ( _cancel_user_agent_client_js__WEBPACK_IMPORTED_MODULE_2__.CancelUserAgentClient),
   "InfoUserAgentClient": () => ( _info_user_agent_client_js__WEBPACK_IMPORTED_MODULE_3__.InfoUserAgentClient),
   "InfoUserAgentServer": () => ( _info_user_agent_server_js__WEBPACK_IMPORTED_MODULE_4__.InfoUserAgentServer),
   "InviteUserAgentClient": () => ( _invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_5__.InviteUserAgentClient),
   "InviteUserAgentServer": () => ( _invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_6__.InviteUserAgentServer),
   "MessageUserAgentClient": () => ( _message_user_agent_client_js__WEBPACK_IMPORTED_MODULE_7__.MessageUserAgentClient),
   "MessageUserAgentServer": () => ( _message_user_agent_server_js__WEBPACK_IMPORTED_MODULE_8__.MessageUserAgentServer),
   "NotifyUserAgentClient": () => ( _notify_user_agent_client_js__WEBPACK_IMPORTED_MODULE_9__.NotifyUserAgentClient),
   "NotifyUserAgentServer": () => ( _notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_10__.NotifyUserAgentServer),
   "PrackUserAgentClient": () => ( _prack_user_agent_client_js__WEBPACK_IMPORTED_MODULE_12__.PrackUserAgentClient),
   "PrackUserAgentServer": () => ( _prack_user_agent_server_js__WEBPACK_IMPORTED_MODULE_13__.PrackUserAgentServer),
   "PublishUserAgentClient": () => ( _publish_user_agent_client_js__WEBPACK_IMPORTED_MODULE_11__.PublishUserAgentClient),
   "ReInviteUserAgentClient": () => ( _re_invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_14__.ReInviteUserAgentClient),
   "ReInviteUserAgentServer": () => ( _re_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_15__.ReInviteUserAgentServer),
   "ReSubscribeUserAgentClient": () => ( _re_subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_16__.ReSubscribeUserAgentClient),
   "ReSubscribeUserAgentServer": () => ( _re_subscribe_user_agent_server_js__WEBPACK_IMPORTED_MODULE_17__.ReSubscribeUserAgentServer),
   "ReferUserAgentClient": () => ( _refer_user_agent_client_js__WEBPACK_IMPORTED_MODULE_18__.ReferUserAgentClient),
   "ReferUserAgentServer": () => ( _refer_user_agent_server_js__WEBPACK_IMPORTED_MODULE_19__.ReferUserAgentServer),
   "RegisterUserAgentClient": () => ( _register_user_agent_client_js__WEBPACK_IMPORTED_MODULE_20__.RegisterUserAgentClient),
   "RegisterUserAgentServer": () => ( _register_user_agent_server_js__WEBPACK_IMPORTED_MODULE_21__.RegisterUserAgentServer),
   "SubscribeUserAgentClient": () => ( _subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_22__.SubscribeUserAgentClient),
   "SubscribeUserAgentServer": () => ( _subscribe_user_agent_server_js__WEBPACK_IMPORTED_MODULE_23__.SubscribeUserAgentServer),
   "UserAgentClient": () => ( _user_agent_client_js__WEBPACK_IMPORTED_MODULE_24__.UserAgentClient),
   "UserAgentServer": () => ( _user_agent_server_js__WEBPACK_IMPORTED_MODULE_25__.UserAgentServer)
 });
 var _bye_user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(74);
 var _bye_user_agent_server_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(81);
 var _cancel_user_agent_client_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(112);
 var _info_user_agent_client_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(75);
 var _info_user_agent_server_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(85);
 var _invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(62);
 var _invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(96);
 var _message_user_agent_client_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(77);
 var _message_user_agent_server_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(87);
 var _notify_user_agent_client_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(78);
 var _notify_user_agent_server_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(88);
 var _publish_user_agent_client_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(91);
 var _prack_user_agent_client_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(79);
 var _prack_user_agent_server_js__WEBPACK_IMPORTED_MODULE_13__ = __webpack_require__(89);
 var _re_invite_user_agent_client_js__WEBPACK_IMPORTED_MODULE_14__ = __webpack_require__(76);
 var _re_invite_user_agent_server_js__WEBPACK_IMPORTED_MODULE_15__ = __webpack_require__(86);
 var _re_subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_16__ = __webpack_require__(95);
 var _re_subscribe_user_agent_server_js__WEBPACK_IMPORTED_MODULE_17__ = __webpack_require__(113);
 var _refer_user_agent_client_js__WEBPACK_IMPORTED_MODULE_18__ = __webpack_require__(80);
 var _refer_user_agent_server_js__WEBPACK_IMPORTED_MODULE_19__ = __webpack_require__(90);
 var _register_user_agent_client_js__WEBPACK_IMPORTED_MODULE_20__ = __webpack_require__(92);
 var _register_user_agent_server_js__WEBPACK_IMPORTED_MODULE_21__ = __webpack_require__(97);
 var _subscribe_user_agent_client_js__WEBPACK_IMPORTED_MODULE_22__ = __webpack_require__(93);
 var _subscribe_user_agent_server_js__WEBPACK_IMPORTED_MODULE_23__ = __webpack_require__(98);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_24__ = __webpack_require__(63);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_25__ = __webpack_require__(82);




























 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "CancelUserAgentClient": () => ( CancelUserAgentClient)
 });
 var _transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(65);
 var _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(63);


/** @public */
class CancelUserAgentClient extends _user_agent_client_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentClient {
    constructor(core, message, delegate) {
        super(_transactions_non_invite_client_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteClientTransaction, core, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "ReSubscribeUserAgentServer": () => ( ReSubscribeUserAgentServer)
 });
 var _transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(83);
 var _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(82);


/** @public */
class ReSubscribeUserAgentServer extends _user_agent_server_js__WEBPACK_IMPORTED_MODULE_0__.UserAgentServer {
    constructor(dialog, message, delegate) {
        super(_transactions_non_invite_server_transaction_js__WEBPACK_IMPORTED_MODULE_1__.NonInviteServerTransaction, dialog.userAgentCore, message, delegate);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionDescriptionHandler": () => ( _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__.SessionDescriptionHandler),
   "SessionManager": () => ( _session_manager_index_js__WEBPACK_IMPORTED_MODULE_2__.SessionManager),
   "SimpleUser": () => ( _simple_user_index_js__WEBPACK_IMPORTED_MODULE_3__.SimpleUser),
   "Transport": () => ( _transport_index_js__WEBPACK_IMPORTED_MODULE_4__.Transport),
   "WebAudioSessionDescriptionHandler": () => ( _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__.WebAudioSessionDescriptionHandler),
   "addMidLines": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.addMidLines),
   "cleanJitsiSdpImageattr": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.cleanJitsiSdpImageattr),
   "defaultManagedSessionFactory": () => ( _session_manager_index_js__WEBPACK_IMPORTED_MODULE_2__.defaultManagedSessionFactory),
   "defaultMediaStreamFactory": () => ( _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__.defaultMediaStreamFactory),
   "defaultPeerConnectionConfiguration": () => ( _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__.defaultPeerConnectionConfiguration),
   "defaultSessionDescriptionHandlerFactory": () => ( _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__.defaultSessionDescriptionHandlerFactory),
   "holdModifier": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.holdModifier),
   "startLocalConference": () => ( _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__.startLocalConference),
   "stripG722": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.stripG722),
   "stripRtpPayload": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.stripRtpPayload),
   "stripTcpCandidates": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.stripTcpCandidates),
   "stripTelephoneEvent": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.stripTelephoneEvent),
   "stripVideo": () => ( _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__.stripVideo)
 });
 var _modifiers_index_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(115);
 var _session_description_handler_index_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(117);
 var _session_manager_index_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(119);
 var _simple_user_index_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(122);
 var _transport_index_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(124);







 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "addMidLines": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.addMidLines),
   "cleanJitsiSdpImageattr": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.cleanJitsiSdpImageattr),
   "holdModifier": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.holdModifier),
   "stripG722": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.stripG722),
   "stripRtpPayload": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.stripRtpPayload),
   "stripTcpCandidates": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.stripTcpCandidates),
   "stripTelephoneEvent": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.stripTelephoneEvent),
   "stripVideo": () => ( _modifiers_js__WEBPACK_IMPORTED_MODULE_0__.stripVideo)
 });
 var _modifiers_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(116);



 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "addMidLines": () => ( addMidLines),
   "cleanJitsiSdpImageattr": () => ( cleanJitsiSdpImageattr),
   "holdModifier": () => ( holdModifier),
   "stripG722": () => ( stripG722),
   "stripRtpPayload": () => ( stripRtpPayload),
   "stripTcpCandidates": () => ( stripTcpCandidates),
   "stripTelephoneEvent": () => ( stripTelephoneEvent),
   "stripVideo": () => ( stripVideo)
 });
const stripPayload = (sdp, payload) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mediaDescs = [];
    const lines = sdp.split(/\r\n/);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let currentMediaDesc;
    for (let i = 0; i < lines.length;) {
        const line = lines[i];
        if (/^m=(?:audio|video)/.test(line)) {
            currentMediaDesc = {
                index: i,
                stripped: []
            };
            mediaDescs.push(currentMediaDesc);
        }
        else if (currentMediaDesc) {
            const rtpmap = /^a=rtpmap:(\d+) ([^/]+)\//.exec(line);
            if (rtpmap && payload === rtpmap[2]) {
                lines.splice(i, 1);
                currentMediaDesc.stripped.push(rtpmap[1]);
                continue;
            }
        }
        i++;
    }
    for (const mediaDesc of mediaDescs) {
        const mline = lines[mediaDesc.index].split(" ");
        for (let j = 3; j < mline.length;) {
            if (mediaDesc.stripped.indexOf(mline[j]) !== -1) {
                mline.splice(j, 1);
                continue;
            }
            j++;
        }
        lines[mediaDesc.index] = mline.join(" ");
    }
    return lines.join("\r\n");
};
const stripMediaDescription = (sdp, description) => {
    const descriptionRegExp = new RegExp("m=" + description + ".*$", "gm");
    const groupRegExp = new RegExp("^a=group:.*$", "gm");
    if (descriptionRegExp.test(sdp)) {
        let midLineToRemove;
        sdp = sdp.split(/^m=/gm).filter((section) => {
            if (section.substr(0, description.length) === description) {
                midLineToRemove = section.match(/^a=mid:.*$/gm);
                if (midLineToRemove) {
                    const step = midLineToRemove[0].match(/:.+$/g);
                    if (step) {
                        midLineToRemove = step[0].substr(1);
                    }
                }
                return false;
            }
            return true;
        }).join("m=");
        const groupLine = sdp.match(groupRegExp);
        if (groupLine && groupLine.length === 1) {
            let groupLinePortion = groupLine[0];
            // eslint-disable-next-line no-useless-escape
            const groupRegExpReplace = new RegExp("\ *" + midLineToRemove + "[^\ ]*", "g");
            groupLinePortion = groupLinePortion.replace(groupRegExpReplace, "");
            sdp = sdp.split(groupRegExp).join(groupLinePortion);
        }
    }
    return sdp;
};
/** @public */
function stripTcpCandidates(description) {
    description.sdp = (description.sdp || "").replace(/^a=candidate:\d+ \d+ tcp .*?\r\n/img, "");
    return Promise.resolve(description);
}
/** @public */
function stripTelephoneEvent(description) {
    description.sdp = stripPayload(description.sdp || "", "telephone-event");
    return Promise.resolve(description);
}
/** @public */
function cleanJitsiSdpImageattr(description) {
    description.sdp = (description.sdp || "").replace(/^(a=imageattr:.*?)(x|y)=\[0-/gm, "$1$2=[1:");
    return Promise.resolve(description);
}
/** @public */
function stripG722(description) {
    description.sdp = stripPayload(description.sdp || "", "G722");
    return Promise.resolve(description);
}
/** @public */
function stripRtpPayload(payload) {
    return (description) => {
        description.sdp = stripPayload(description.sdp || "", payload);
        return Promise.resolve(description);
    };
}
/** @public */
function stripVideo(description) {
    description.sdp = stripMediaDescription(description.sdp || "", "video");
    return Promise.resolve(description);
}
/** @public */
function addMidLines(description) {
    let sdp = description.sdp || "";
    if (sdp.search(/^a=mid.*$/gm) === -1) {
        const mlines = sdp.match(/^m=.*$/gm);
        const sdpArray = sdp.split(/^m=.*$/gm);
        if (mlines) {
            mlines.forEach((elem, idx) => {
                mlines[idx] = elem + "\na=mid:" + idx;
            });
        }
        sdpArray.forEach((elem, idx) => {
            if (mlines && mlines[idx]) {
                sdpArray[idx] = elem + mlines[idx];
            }
        });
        sdp = sdpArray.join("");
        description.sdp = sdp;
    }
    return Promise.resolve(description);
}
/** @param description */
function holdModifier(description) {
    if (!description.sdp || !description.type) {
        throw new Error("Invalid SDP");
    }
    let sdp = description.sdp;
    const type = description.type;
    if (sdp) {
        if (!/a=(sendrecv|sendonly|recvonly|inactive)/.test(sdp)) {
            sdp = sdp.replace(/(m=[^\r]*\r\n)/g, "$1a=sendonly\r\n");
        }
        else {
            sdp = sdp.replace(/a=sendrecv\r\n/g, "a=sendonly\r\n");
            sdp = sdp.replace(/a=recvonly\r\n/g, "a=inactive\r\n");
        }
    }
    return Promise.resolve({ sdp, type });
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionDescriptionHandler": () => ( _session_description_handler_js__WEBPACK_IMPORTED_MODULE_3__.SessionDescriptionHandler),
   "WebAudioSessionDescriptionHandler": () => ( _web_audio_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.WebAudioSessionDescriptionHandler),
   "defaultMediaStreamFactory": () => ( _media_stream_factory_default_js__WEBPACK_IMPORTED_MODULE_0__.defaultMediaStreamFactory),
   "defaultPeerConnectionConfiguration": () => ( _peer_connection_configuration_default_js__WEBPACK_IMPORTED_MODULE_1__.defaultPeerConnectionConfiguration),
   "defaultSessionDescriptionHandlerFactory": () => ( _session_description_handler_factory_default_js__WEBPACK_IMPORTED_MODULE_2__.defaultSessionDescriptionHandlerFactory),
   "startLocalConference": () => ( _web_audio_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.startLocalConference)
 });
 var _media_stream_factory_default_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(55);
 var _peer_connection_configuration_default_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(56);
 var _session_description_handler_factory_default_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(54);
 var _session_description_handler_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(57);
 var _web_audio_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(118);













 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "WebAudioSessionDescriptionHandler": () => ( WebAudioSessionDescriptionHandler),
   "startLocalConference": () => ( startLocalConference)
 });
 var _session_description_handler_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(57);

/**
 * @param conferenceSessions
 * @beta
 */
function startLocalConference(conferenceSessions) {
    if (conferenceSessions.length < 2) {
        throw new Error("Start local conference requires at leaast 2 sessions.");
    }
    const pairs = (arr) => arr.map((v, i) => arr.slice(i + 1).map((w) => [v, w])).reduce((acc, curVal) => acc.concat(curVal), []);
    pairs(conferenceSessions.map((session) => session.sessionDescriptionHandler)).forEach(([sdh0, sdh1]) => {
        if (!(sdh0 instanceof WebAudioSessionDescriptionHandler && sdh1 instanceof WebAudioSessionDescriptionHandler)) {
            throw new Error("Session description handler not instance of SessionManagerSessionDescriptionHandler");
        }
        sdh0.joinWith(sdh1);
    });
}
class WebAudioSessionDescriptionHandler extends _session_description_handler_js__WEBPACK_IMPORTED_MODULE_0__.SessionDescriptionHandler {
    constructor(logger, mediaStreamFactory, sessionDescriptionHandlerConfiguration) {
        super(logger, mediaStreamFactory, sessionDescriptionHandlerConfiguration);
        if (!WebAudioSessionDescriptionHandler.audioContext) {
            WebAudioSessionDescriptionHandler.audioContext = new AudioContext();
        }
    }
    /** @param enable */
    enableSenderTracks(enable) {
        const stream = this.localMediaStreamReal;
        if (stream === undefined) {
            throw new Error("Stream undefined.");
        }
        stream.getAudioTracks().forEach((track) => {
            track.enabled = enable;
        });
    }
    /** @param stream */
    initLocalMediaStream(stream) {
        if (!WebAudioSessionDescriptionHandler.audioContext) {
            throw new Error("SessionManagerSessionDescriptionHandler.audioContext undefined.");
        }
        this.localMediaStreamReal = stream;
        this.localMediaStreamSourceNode = WebAudioSessionDescriptionHandler.audioContext.createMediaStreamSource(stream);
        this.localMediaStreamDestinationNode =
            WebAudioSessionDescriptionHandler.audioContext.createMediaStreamDestination();
        this.localMediaStreamSourceNode.connect(this.localMediaStreamDestinationNode);
        return this.localMediaStreamDestinationNode.stream;
    }
    /** @param peer */
    joinWith(peer) {
        if (!WebAudioSessionDescriptionHandler.audioContext) {
            throw new Error("SessionManagerSessionDescriptionHandler.audioContext undefined.");
        }
        const ourNewInboundStreamSource = WebAudioSessionDescriptionHandler.audioContext.createMediaStreamSource(this.remoteMediaStream);
        const peerOutboundStreamDestination = peer.localMediaStreamDestinationNode;
        if (peerOutboundStreamDestination === undefined) {
            throw new Error("Peer outbound (local) stream local media stream destination is undefined.");
        }
        ourNewInboundStreamSource.connect(peerOutboundStreamDestination);
        const peerNewInboundStreamSource = WebAudioSessionDescriptionHandler.audioContext.createMediaStreamSource(peer.remoteMediaStream);
        const ourOutboundStreamDestination = this.localMediaStreamDestinationNode;
        if (ourOutboundStreamDestination === undefined) {
            throw new Error("Our outbound (local) stream local media stream destination is undefined.");
        }
        peerNewInboundStreamSource.connect(ourOutboundStreamDestination);
    }
    /**
     * @param stream
     * @remarks
     */
    setRealLocalMediaStream(stream) {
        if (!WebAudioSessionDescriptionHandler.audioContext) {
            throw new Error("SessionManagerSessionDescriptionHandler.audioContext undefined.");
        }
        if (!this.localMediaStreamReal) {
            this.initLocalMediaStream(stream);
            return;
        }
        if (!this.localMediaStreamDestinationNode || !this.localMediaStreamSourceNode || !this.localMediaStreamReal) {
            throw new Error("Local media stream undefined.");
        }
        this.localMediaStreamReal = stream;
        this.localMediaStreamSourceNode.disconnect(this.localMediaStreamDestinationNode);
        this.localMediaStreamSourceNode = WebAudioSessionDescriptionHandler.audioContext.createMediaStreamSource(stream);
        this.localMediaStreamSourceNode.connect(this.localMediaStreamDestinationNode);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionManager": () => ( _session_manager_js__WEBPACK_IMPORTED_MODULE_1__.SessionManager),
   "defaultManagedSessionFactory": () => ( _managed_session_factory_default_js__WEBPACK_IMPORTED_MODULE_0__.defaultManagedSessionFactory)
 });
 var _managed_session_factory_default_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(120);
 var _session_manager_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(121);








 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "defaultManagedSessionFactory": () => ( defaultManagedSessionFactory)
 });
/** @public */
function defaultManagedSessionFactory() {
    return (sessionManager, session) => {
        return { session, held: false, muted: false };
    };
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SessionManager": () => ( SessionManager)
 });
 var _api_invitation_js__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(15);
 var _api_inviter_js__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(38);
 var _api_messager_js__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(39);
 var _api_registerer_js__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(43);
 var _api_registerer_state_js__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(42);
 var _api_exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_11__ = __webpack_require__(6);
 var _api_session_js__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(16);
 var _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__ = __webpack_require__(17);
 var _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(50);
 var _api_user_agent_state_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(49);
 var _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(57);
 var _transport_transport_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(58);
 var _managed_session_factory_default_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(120);













/** @public */
class SessionManager {
    /**
     * @param server
     * @param options
     */
    constructor(server, options = {}) {
        this.managedSessions = [];
        this.attemptingReconnection = false;
        this.optionsPingFailure = false;
        this.optionsPingRunning = false;
        this.shouldBeConnected = false;
        this.shouldBeRegistered = false;
        this.delegate = options.delegate;
        this.options = Object.assign({
            aor: "",
            autoStop: true,
            delegate: {},
            iceStopWaitingOnServerReflexive: false,
            managedSessionFactory: (0,_managed_session_factory_default_js__WEBPACK_IMPORTED_MODULE_0__.defaultManagedSessionFactory)(),
            maxSimultaneousSessions: 2,
            media: {},
            optionsPingInterval: -1,
            optionsPingRequestURI: "",
            reconnectionAttempts: 3,
            reconnectionDelay: 4,
            registrationRetry: false,
            registrationRetryInterval: 3,
            registerGuard: null,
            registererOptions: {},
            registererRegisterOptions: {},
            sendDTMFUsingSessionDescriptionHandler: false,
            userAgentOptions: {}
        }, SessionManager.stripUndefinedProperties(options));
        const userAgentOptions = Object.assign({}, options.userAgentOptions);
        if (!userAgentOptions.transportConstructor) {
            userAgentOptions.transportConstructor = _transport_transport_js__WEBPACK_IMPORTED_MODULE_1__.Transport;
        }
        if (!userAgentOptions.transportOptions) {
            userAgentOptions.transportOptions = {
                server
            };
        }
        if (!userAgentOptions.uri) {
            if (options.aor) {
                const uri = _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent.makeURI(options.aor);
                if (!uri) {
                    throw new Error(`Failed to create valid URI from ${options.aor}`);
                }
                userAgentOptions.uri = uri;
            }
        }
        this.userAgent = new _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent(userAgentOptions);
        this.userAgent.delegate = {
            onConnect: () => {
                this.logger.log(`Connected`);
                if (this.delegate && this.delegate.onServerConnect) {
                    this.delegate.onServerConnect();
                }
                if (this.shouldBeRegistered) {
                    this.register();
                }
                if (this.options.optionsPingInterval > 0) {
                    this.optionsPingStart();
                }
            },
            onDisconnect: async (error) => {
                this.logger.log(`Disconnected`);
                let optionsPingFailure = false;
                if (this.options.optionsPingInterval > 0) {
                    optionsPingFailure = this.optionsPingFailure;
                    this.optionsPingFailure = false;
                    this.optionsPingStop();
                }
                if (this.delegate && this.delegate.onServerDisconnect) {
                    this.delegate.onServerDisconnect(error);
                }
                if (error || optionsPingFailure) {
                    if (this.registerer) {
                        this.logger.log(`Disposing of registerer...`);
                        this.registerer.dispose().catch((e) => {
                            this.logger.debug(`Error occurred disposing of registerer after connection with server was lost.`);
                            this.logger.debug(e.toString());
                        });
                        this.registerer = undefined;
                    }
                    this.managedSessions
                        .slice()
                        .map((el) => el.session)
                        .forEach(async (session) => {
                        this.logger.log(`Disposing of session...`);
                        session.dispose().catch((e) => {
                            this.logger.debug(`Error occurred disposing of a session after connection with server was lost.`);
                            this.logger.debug(e.toString());
                        });
                    });
                    if (this.shouldBeConnected) {
                        this.attemptReconnection();
                    }
                }
            },
            onInvite: (invitation) => {
                this.logger.log(`[${invitation.id}] Received INVITE`);
                const maxSessions = this.options.maxSimultaneousSessions;
                if (maxSessions !== 0 && this.managedSessions.length > maxSessions) {
                    this.logger.warn(`[${invitation.id}] Session already in progress, rejecting INVITE...`);
                    invitation
                        .reject()
                        .then(() => {
                        this.logger.log(`[${invitation.id}] Rejected INVITE`);
                    })
                        .catch((error) => {
                        this.logger.error(`[${invitation.id}] Failed to reject INVITE`);
                        this.logger.error(error.toString());
                    });
                    return;
                }
                const referralInviterOptions = {
                    sessionDescriptionHandlerOptions: { constraints: this.constraints }
                };
                this.initSession(invitation, referralInviterOptions);
                if (this.delegate && this.delegate.onCallReceived) {
                    this.delegate.onCallReceived(invitation);
                }
                else {
                    this.logger.warn(`[${invitation.id}] No handler available, rejecting INVITE...`);
                    invitation
                        .reject()
                        .then(() => {
                        this.logger.log(`[${invitation.id}] Rejected INVITE`);
                    })
                        .catch((error) => {
                        this.logger.error(`[${invitation.id}] Failed to reject INVITE`);
                        this.logger.error(error.toString());
                    });
                }
            },
            onMessage: (message) => {
                message.accept().then(() => {
                    if (this.delegate && this.delegate.onMessageReceived) {
                        this.delegate.onMessageReceived(message);
                    }
                });
            },
            onNotify: (notification) => {
                notification.accept().then(() => {
                    if (this.delegate && this.delegate.onNotificationReceived) {
                        this.delegate.onNotificationReceived(notification);
                    }
                });
            }
        };
        this.registererOptions = Object.assign({}, options.registererOptions);
        this.registererRegisterOptions = Object.assign({}, options.registererRegisterOptions);
        if (this.options.registrationRetry) {
            this.registererRegisterOptions.requestDelegate = this.registererRegisterOptions.requestDelegate || {};
            const existingOnReject = this.registererRegisterOptions.requestDelegate.onReject;
            this.registererRegisterOptions.requestDelegate.onReject = (response) => {
                existingOnReject && existingOnReject(response);
                this.attemptRegistration();
            };
        }
        this.logger = this.userAgent.getLogger("sip.SessionManager");
        window.addEventListener("online", () => {
            this.logger.log(`Online`);
            if (this.shouldBeConnected) {
                this.connect();
            }
        });
        if (this.options.autoStop) {
            window.addEventListener("beforeunload", async () => {
                this.shouldBeConnected = false;
                this.shouldBeRegistered = false;
                if (this.userAgent.state !== _api_user_agent_state_js__WEBPACK_IMPORTED_MODULE_3__.UserAgentState.Stopped) {
                    await this.userAgent.stop();
                }
            });
        }
    }
    /** @param options */
    static stripUndefinedProperties(options) {
        return Object.keys(options).reduce((object, key) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            if (options[key] !== undefined) {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                object[key] = options[key];
            }
            return object;
        }, {});
    }
    /** @param session */
    getLocalMediaStream(session) {
        const sdh = session.sessionDescriptionHandler;
        if (!sdh) {
            return undefined;
        }
        if (!(sdh instanceof _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.SessionDescriptionHandler)) {
            throw new Error("Session description handler not instance of web SessionDescriptionHandler");
        }
        return sdh.localMediaStream;
    }
    /** @param session */
    getRemoteMediaStream(session) {
        const sdh = session.sessionDescriptionHandler;
        if (!sdh) {
            return undefined;
        }
        if (!(sdh instanceof _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.SessionDescriptionHandler)) {
            throw new Error("Session description handler not instance of web SessionDescriptionHandler");
        }
        return sdh.remoteMediaStream;
    }
    /**
     * @param session
     * @deprecated
     */
    getLocalAudioTrack(session) {
        var _a;
        return (_a = this.getLocalMediaStream(session)) === null || _a === void 0 ? void 0 : _a.getTracks().find((track) => track.kind === "audio");
    }
    /**
     * @param session
     * @deprecated
     */
    getLocalVideoTrack(session) {
        var _a;
        return (_a = this.getLocalMediaStream(session)) === null || _a === void 0 ? void 0 : _a.getTracks().find((track) => track.kind === "video");
    }
    /**
     * @param session
     * @deprecated
     */
    getRemoteAudioTrack(session) {
        var _a;
        return (_a = this.getRemoteMediaStream(session)) === null || _a === void 0 ? void 0 : _a.getTracks().find((track) => track.kind === "audio");
    }
    /**
     * @param session
     * @deprecated
     */
    getRemoteVideoTrack(session) {
        var _a;
        return (_a = this.getRemoteMediaStream(session)) === null || _a === void 0 ? void 0 : _a.getTracks().find((track) => track.kind === "video");
    }
    async connect() {
        this.logger.log(`Connecting UserAgent...`);
        this.shouldBeConnected = true;
        if (this.userAgent.state !== _api_user_agent_state_js__WEBPACK_IMPORTED_MODULE_3__.UserAgentState.Started) {
            return this.userAgent.start();
        }
        return this.userAgent.reconnect();
    }
    async disconnect() {
        this.logger.log(`Disconnecting UserAgent...`);
        if (this.userAgent.state === _api_user_agent_state_js__WEBPACK_IMPORTED_MODULE_3__.UserAgentState.Stopped) {
            return Promise.resolve();
        }
        this.shouldBeConnected = false;
        this.shouldBeRegistered = false;
        this.registerer = undefined;
        return this.userAgent.stop();
    }
    isConnected() {
        return this.userAgent.isConnected();
    }
    async register(registererRegisterOptions) {
        this.logger.log(`Registering UserAgent...`);
        this.shouldBeRegistered = true;
        if (registererRegisterOptions !== undefined) {
            this.registererRegisterOptions = Object.assign({}, registererRegisterOptions);
        }
        if (!this.registerer) {
            this.registerer = new _api_registerer_js__WEBPACK_IMPORTED_MODULE_5__.Registerer(this.userAgent, this.registererOptions);
            this.registerer.stateChange.addListener((state) => {
                switch (state) {
                    case _api_registerer_state_js__WEBPACK_IMPORTED_MODULE_6__.RegistererState.Initial:
                        break;
                    case _api_registerer_state_js__WEBPACK_IMPORTED_MODULE_6__.RegistererState.Registered:
                        if (this.delegate && this.delegate.onRegistered) {
                            this.delegate.onRegistered();
                        }
                        break;
                    case _api_registerer_state_js__WEBPACK_IMPORTED_MODULE_6__.RegistererState.Unregistered:
                        if (this.delegate && this.delegate.onUnregistered) {
                            this.delegate.onUnregistered();
                        }
                        if (this.shouldBeRegistered) {
                            this.attemptRegistration();
                        }
                        break;
                    case _api_registerer_state_js__WEBPACK_IMPORTED_MODULE_6__.RegistererState.Terminated:
                        break;
                    default:
                        throw new Error("Unknown registerer state.");
                }
            });
        }
        return this.attemptRegistration(true);
    }
    async unregister(registererUnregisterOptions) {
        this.logger.log(`Unregistering UserAgent...`);
        this.shouldBeRegistered = false;
        if (!this.registerer) {
            this.logger.warn(`No registerer to unregister.`);
            return Promise.resolve();
        }
        return this.registerer.unregister(registererUnregisterOptions).then(() => {
            return;
        });
    }
    /**
     * @remarks
     * @param destination
     * @param inviterOptions
     * @param inviterInviteOptions
     */
    async call(destination, inviterOptions, inviterInviteOptions) {
        this.logger.log(`Beginning Session...`);
        const maxSessions = this.options.maxSimultaneousSessions;
        if (maxSessions !== 0 && this.managedSessions.length > maxSessions) {
            return Promise.reject(new Error("Maximum number of sessions already exists."));
        }
        const target = _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent.makeURI(destination);
        if (!target) {
            return Promise.reject(new Error(`Failed to create a valid URI from "${destination}"`));
        }
        if (!inviterOptions) {
            inviterOptions = {};
        }
        if (!inviterOptions.sessionDescriptionHandlerOptions) {
            inviterOptions.sessionDescriptionHandlerOptions = {};
        }
        if (!inviterOptions.sessionDescriptionHandlerOptions.constraints) {
            inviterOptions.sessionDescriptionHandlerOptions.constraints = this.constraints;
        }
        if (inviterOptions.earlyMedia) {
            inviterInviteOptions = inviterInviteOptions || {};
            inviterInviteOptions.requestDelegate = inviterInviteOptions.requestDelegate || {};
            const existingOnProgress = inviterInviteOptions.requestDelegate.onProgress;
            inviterInviteOptions.requestDelegate.onProgress = (response) => {
                if (response.message.statusCode === 183) {
                    this.setupRemoteMedia(inviter);
                }
                existingOnProgress && existingOnProgress(response);
            };
        }
        if (this.options.iceStopWaitingOnServerReflexive) {
            inviterOptions.delegate = inviterOptions.delegate || {};
            inviterOptions.delegate.onSessionDescriptionHandler = (sessionDescriptionHandler) => {
                if (!(sessionDescriptionHandler instanceof _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.SessionDescriptionHandler)) {
                    throw new Error("Session description handler not instance of SessionDescriptionHandler");
                }
                sessionDescriptionHandler.peerConnectionDelegate = {
                    onicecandidate: (event) => {
                        var _a;
                        if (((_a = event.candidate) === null || _a === void 0 ? void 0 : _a.type) === "srflx") {
                            this.logger.log(`[${inviter.id}] Found srflx ICE candidate, stop waiting...`);
                            const sdh = sessionDescriptionHandler;
                            sdh.iceGatheringComplete();
                        }
                    }
                };
            };
        }
        const inviter = new _api_inviter_js__WEBPACK_IMPORTED_MODULE_7__.Inviter(this.userAgent, target, inviterOptions);
        return this.sendInvite(inviter, inviterOptions, inviterInviteOptions).then(() => {
            return inviter;
        });
    }
    /**
     * @param session
     * @remarks
     */
    async hangup(session) {
        this.logger.log(`[${session.id}] Hangup...`);
        if (!this.sessionExists(session)) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.terminate(session);
    }
    /**
     * @param session
     * @remarks
     * @param invitationAcceptOptions
     */
    async answer(session, invitationAcceptOptions) {
        this.logger.log(`[${session.id}] Accepting Invitation...`);
        if (!this.sessionExists(session)) {
            return Promise.reject(new Error("Session does not exist."));
        }
        if (!(session instanceof _api_invitation_js__WEBPACK_IMPORTED_MODULE_8__.Invitation)) {
            return Promise.reject(new Error("Session not instance of Invitation."));
        }
        if (!invitationAcceptOptions) {
            invitationAcceptOptions = {};
        }
        if (!invitationAcceptOptions.sessionDescriptionHandlerOptions) {
            invitationAcceptOptions.sessionDescriptionHandlerOptions = {};
        }
        if (!invitationAcceptOptions.sessionDescriptionHandlerOptions.constraints) {
            invitationAcceptOptions.sessionDescriptionHandlerOptions.constraints = this.constraints;
        }
        return session.accept(invitationAcceptOptions);
    }
    /**
     * @param session
     * @remarks
     */
    async decline(session) {
        this.logger.log(`[${session.id}] Rejecting Invitation...`);
        if (!this.sessionExists(session)) {
            return Promise.reject(new Error("Session does not exist."));
        }
        if (!(session instanceof _api_invitation_js__WEBPACK_IMPORTED_MODULE_8__.Invitation)) {
            return Promise.reject(new Error("Session not instance of Invitation."));
        }
        return session.reject();
    }
    /**
     * @param session
     * @remarks
     */
    async hold(session) {
        this.logger.log(`[${session.id}] Holding session...`);
        return this.setHold(session, true);
    }
    /**
     * @param session
     * @remarks
     */
    async unhold(session) {
        this.logger.log(`[${session.id}] Unholding session...`);
        return this.setHold(session, false);
    }
    /**
     * @param session
     * @remarks
     */
    isHeld(session) {
        const managedSession = this.sessionManaged(session);
        return managedSession ? managedSession.held : false;
    }
    /**
     * @param session
     * @remarks
     */
    mute(session) {
        this.logger.log(`[${session.id}] Disabling media tracks...`);
        this.setMute(session, true);
    }
    /**
     * @param session
     * @remarks
     */
    unmute(session) {
        this.logger.log(`[${session.id}] Enabling media tracks...`);
        this.setMute(session, false);
    }
    /**
     * @param session
     * @remarks
     */
    isMuted(session) {
        const managedSession = this.sessionManaged(session);
        return managedSession ? managedSession.muted : false;
    }
    /**
     * @param session
     * @remarks
     * @param tone
     */
    async sendDTMF(session, tone) {
        this.logger.log(`[${session.id}] Sending DTMF...`);
        if (!/^[0-9A-D#*,]$/.exec(tone)) {
            return Promise.reject(new Error("Invalid DTMF tone."));
        }
        if (!this.sessionExists(session)) {
            return Promise.reject(new Error("Session does not exist."));
        }
        this.logger.log(`[${session.id}] Sending DTMF tone: ${tone}`);
        if (this.options.sendDTMFUsingSessionDescriptionHandler) {
            if (!session.sessionDescriptionHandler) {
                return Promise.reject(new Error("Session desciption handler undefined."));
            }
            if (!session.sessionDescriptionHandler.sendDtmf(tone)) {
                return Promise.reject(new Error("Failed to send DTMF"));
            }
            return Promise.resolve();
        }
        else {
            const dtmf = tone;
            const duration = 2000;
            const body = {
                contentDisposition: "render",
                contentType: "application/dtmf-relay",
                content: "Signal=" + dtmf + "\r\nDuration=" + duration
            };
            const requestOptions = { body };
            return session.info({ requestOptions }).then(() => {
                return;
            });
        }
    }
    /**
     * @param session
     * @param target
     * @remarks
     */
    async transfer(session, target, options) {
        this.logger.log(`[${session.id}] Referring session...`);
        if (target instanceof _api_session_js__WEBPACK_IMPORTED_MODULE_9__.Session) {
            return session.refer(target, options).then(() => {
                return;
            });
        }
        const uri = _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent.makeURI(target);
        if (!uri) {
            return Promise.reject(new Error(`Failed to create a valid URI from "${target}"`));
        }
        return session.refer(uri, options).then(() => {
            return;
        });
    }
    /**
     * @remarks
     * @param destination
     */
    async message(destination, message) {
        this.logger.log(`Sending message...`);
        const target = _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent.makeURI(destination);
        if (!target) {
            return Promise.reject(new Error(`Failed to create a valid URI from "${destination}"`));
        }
        return new _api_messager_js__WEBPACK_IMPORTED_MODULE_10__.Messager(this.userAgent, target, message).message();
    }
    get constraints() {
        let constraints = { audio: true, video: false };
        if (this.options.media.constraints) {
            constraints = Object.assign({}, this.options.media.constraints);
        }
        return constraints;
    }
    /** @param reconnectionAttempt */
    attemptReconnection(reconnectionAttempt = 1) {
        const reconnectionAttempts = this.options.reconnectionAttempts;
        const reconnectionDelay = this.options.reconnectionDelay;
        if (!this.shouldBeConnected) {
            this.logger.log(`Should not be connected currently`);
            return;
        }
        if (this.attemptingReconnection) {
            this.logger.log(`Reconnection attempt already in progress`);
        }
        if (reconnectionAttempt > reconnectionAttempts) {
            this.logger.log(`Reconnection maximum attempts reached`);
            return;
        }
        if (reconnectionAttempt === 1) {
            this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - trying`);
        }
        else {
            this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - trying in ${reconnectionDelay} seconds`);
        }
        this.attemptingReconnection = true;
        setTimeout(() => {
            if (!this.shouldBeConnected) {
                this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - aborted`);
                this.attemptingReconnection = false;
                return;
            }
            this.userAgent
                .reconnect()
                .then(() => {
                this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - succeeded`);
                this.attemptingReconnection = false;
            })
                .catch((error) => {
                this.logger.log(`Reconnection attempt ${reconnectionAttempt} of ${reconnectionAttempts} - failed`);
                this.logger.error(error.message);
                this.attemptingReconnection = false;
                this.attemptReconnection(++reconnectionAttempt);
            });
        }, reconnectionAttempt === 1 ? 0 : reconnectionDelay * 1000);
    }
    /** @param withoutDelay */
    attemptRegistration(withoutDelay = false) {
        this.logger.log(`Registration attempt ${withoutDelay ? "without delay" : ""}`);
        if (!this.shouldBeRegistered) {
            this.logger.log(`Should not be registered currently`);
            return Promise.resolve();
        }
        if (this.registrationAttemptTimeout !== undefined) {
            this.logger.log(`Registration attempt already in progress`);
            return Promise.resolve();
        }
        const _register = () => {
            if (!this.registerer) {
                this.logger.log(`Registerer undefined`);
                return Promise.resolve();
            }
            if (!this.isConnected()) {
                this.logger.log(`User agent not connected`);
                return Promise.resolve();
            }
            if (this.userAgent.state === _api_user_agent_state_js__WEBPACK_IMPORTED_MODULE_3__.UserAgentState.Stopped) {
                this.logger.log(`User agent stopped`);
                return Promise.resolve();
            }
            if (!this.options.registerGuard) {
                return this.registerer.register(this.registererRegisterOptions).then(() => {
                    return;
                });
            }
            return this.options
                .registerGuard()
                .catch((error) => {
                this.logger.log(`Register guard rejected will making registration attempt`);
                throw error;
            })
                .then((halt) => {
                if (halt || !this.registerer) {
                    return Promise.resolve();
                }
                return this.registerer.register(this.registererRegisterOptions).then(() => {
                    return;
                });
            });
        };
        const computeRegistrationTimeout = (lowerBound) => {
            const upperBound = lowerBound * 2;
            return 1000 * (Math.random() * (upperBound - lowerBound) + lowerBound);
        };
        return new Promise((resolve, reject) => {
            this.registrationAttemptTimeout = setTimeout(() => {
                _register()
                    .then(() => {
                    this.registrationAttemptTimeout = undefined;
                    resolve();
                })
                    .catch((error) => {
                    this.registrationAttemptTimeout = undefined;
                    if (error instanceof _api_exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_11__.RequestPendingError) {
                        resolve();
                    }
                    else {
                        reject(error);
                    }
                });
            }, withoutDelay ? 0 : computeRegistrationTimeout(this.options.registrationRetryInterval));
        });
    }
    cleanupMedia(session) {
        const managedSession = this.sessionManaged(session);
        if (!managedSession) {
            throw new Error("Managed session does not exist.");
        }
        if (managedSession.mediaLocal) {
            if (managedSession.mediaLocal.video) {
                managedSession.mediaLocal.video.srcObject = null;
                managedSession.mediaLocal.video.pause();
            }
        }
        if (managedSession.mediaRemote) {
            if (managedSession.mediaRemote.audio) {
                managedSession.mediaRemote.audio.srcObject = null;
                managedSession.mediaRemote.audio.pause();
            }
            if (managedSession.mediaRemote.video) {
                managedSession.mediaRemote.video.srcObject = null;
                managedSession.mediaRemote.video.pause();
            }
        }
    }
    enableReceiverTracks(session, enable) {
        if (!this.sessionExists(session)) {
            throw new Error("Session does not exist.");
        }
        const sessionDescriptionHandler = session.sessionDescriptionHandler;
        if (!(sessionDescriptionHandler instanceof _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.SessionDescriptionHandler)) {
            throw new Error("Session's session description handler not instance of SessionDescriptionHandler.");
        }
        sessionDescriptionHandler.enableReceiverTracks(enable);
    }
    enableSenderTracks(session, enable) {
        if (!this.sessionExists(session)) {
            throw new Error("Session does not exist.");
        }
        const sessionDescriptionHandler = session.sessionDescriptionHandler;
        if (!(sessionDescriptionHandler instanceof _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.SessionDescriptionHandler)) {
            throw new Error("Session's session description handler not instance of SessionDescriptionHandler.");
        }
        sessionDescriptionHandler.enableSenderTracks(enable);
    }
    /**
     * @param session
     * @param referralInviterOptions
     */
    initSession(session, referralInviterOptions) {
        this.sessionAdd(session);
        if (this.delegate && this.delegate.onCallCreated) {
            this.delegate.onCallCreated(session);
        }
        session.stateChange.addListener((state) => {
            this.logger.log(`[${session.id}] Session state changed to ${state}`);
            switch (state) {
                case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Initial:
                    break;
                case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Establishing:
                    break;
                case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Established:
                    this.setupLocalMedia(session);
                    this.setupRemoteMedia(session);
                    if (this.delegate && this.delegate.onCallAnswered) {
                        this.delegate.onCallAnswered(session);
                    }
                    break;
                case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Terminating:

                case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Terminated:
                    if (this.sessionExists(session)) {
                        this.cleanupMedia(session);
                        this.sessionRemove(session);
                        if (this.delegate && this.delegate.onCallHangup) {
                            this.delegate.onCallHangup(session);
                        }
                    }
                    break;
                default:
                    throw new Error("Unknown session state.");
            }
        });
        session.delegate = session.delegate || {};
        session.delegate.onInfo = (info) => {
            var _a;
            if (((_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallDTMFReceived) === undefined) {
                info.reject();
                return;
            }
            const contentType = info.request.getHeader("content-type");
            if (!contentType || !/^application\/dtmf-relay/i.exec(contentType)) {
                info.reject();
                return;
            }
            const body = info.request.body.split("\r\n", 2);
            if (body.length !== 2) {
                info.reject();
                return;
            }
            let tone;
            const toneRegExp = /^(Signal\s*?=\s*?)([0-9A-D#*]{1})(\s)?.*/;
            if (body[0] !== undefined && toneRegExp.test(body[0])) {
                tone = body[0].replace(toneRegExp, "$2");
            }
            if (!tone) {
                info.reject();
                return;
            }
            let duration;
            const durationRegExp = /^(Duration\s?=\s?)([0-9]{1,4})(\s)?.*/;
            if (body[1] !== undefined && durationRegExp.test(body[1])) {
                duration = parseInt(body[1].replace(durationRegExp, "$2"), 10);
            }
            if (!duration) {
                info.reject();
                return;
            }
            info
                .accept()
                .then(() => {
                if (this.delegate && this.delegate.onCallDTMFReceived) {
                    if (!tone || !duration) {
                        throw new Error("Tone or duration undefined.");
                    }
                    this.delegate.onCallDTMFReceived(session, tone, duration);
                }
            })
                .catch((error) => {
                this.logger.error(error.message);
            });
        };
        session.delegate.onRefer = (referral) => {
            referral
                .accept()
                .then(() => this.sendInvite(referral.makeInviter(referralInviterOptions), referralInviterOptions))
                .catch((error) => {
                this.logger.error(error.message);
            });
        };
    }
    /**
     * @param requestURI
     * @param fromURI
     * @param toURI
     */
    optionsPingRun(requestURI, fromURI, toURI) {
        if (this.options.optionsPingInterval < 1) {
            throw new Error("Invalid options ping interval.");
        }
        if (this.optionsPingRunning) {
            return;
        }
        this.optionsPingRunning = true;
        this.optionsPingTimeout = setTimeout(() => {
            this.optionsPingTimeout = undefined;
            const onPingSuccess = () => {
                this.optionsPingFailure = false;
                if (this.optionsPingRunning) {
                    this.optionsPingRunning = false;
                    this.optionsPingRun(requestURI, fromURI, toURI);
                }
            };
            const onPingFailure = () => {
                this.logger.error("OPTIONS ping failed");
                this.optionsPingFailure = true;
                this.optionsPingRunning = false;
                this.userAgent.transport.disconnect().catch((error) => this.logger.error(error));
            };
            const core = this.userAgent.userAgentCore;
            const message = core.makeOutgoingRequestMessage("OPTIONS", requestURI, fromURI, toURI, {});
            this.optionsPingRequest = core.request(message, {
                onAccept: () => {
                    this.optionsPingRequest = undefined;
                    onPingSuccess();
                },
                onReject: (response) => {
                    this.optionsPingRequest = undefined;
                    if (response.message.statusCode === 408 || response.message.statusCode === 503) {
                        onPingFailure();
                    }
                    else {
                        onPingSuccess();
                    }
                }
            });
        }, this.options.optionsPingInterval * 1000);
    }
    optionsPingStart() {
        this.logger.log(`OPTIONS pings started`);
        let requestURI, fromURI, toURI;
        if (this.options.optionsPingRequestURI) {
            requestURI = _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent.makeURI(this.options.optionsPingRequestURI);
            if (!requestURI) {
                throw new Error("Failed to create Request URI.");
            }
            fromURI = this.userAgent.contact.uri.clone();
            toURI = this.userAgent.contact.uri.clone();
        }
        else if (this.options.aor) {
            const uri = _api_user_agent_js__WEBPACK_IMPORTED_MODULE_2__.UserAgent.makeURI(this.options.aor);
            if (!uri) {
                throw new Error("Failed to create URI.");
            }
            requestURI = uri.clone();
            requestURI.user = undefined;
            fromURI = uri.clone();
            toURI = uri.clone();
        }
        else {
            this.logger.error("You have enabled sending OPTIONS pings and as such you must provide either " +
                "a) an AOR to register, or b) an RURI to use for the target of the OPTIONS ping requests. ");
            return;
        }
        this.optionsPingRun(requestURI, fromURI, toURI);
    }
    optionsPingStop() {
        this.logger.log(`OPTIONS pings stopped`);
        this.optionsPingRunning = false;
        this.optionsPingFailure = false;
        if (this.optionsPingRequest) {
            this.optionsPingRequest.dispose();
            this.optionsPingRequest = undefined;
        }
        if (this.optionsPingTimeout) {
            clearTimeout(this.optionsPingTimeout);
            this.optionsPingTimeout = undefined;
        }
    }
    async sendInvite(inviter, inviterOptions, inviterInviteOptions) {
        this.initSession(inviter, inviterOptions);
        return inviter.invite(inviterInviteOptions).then(() => {
            this.logger.log(`[${inviter.id}] Sent INVITE`);
        });
    }
    sessionAdd(session) {
        const managedSession = this.options.managedSessionFactory(this, session);
        this.managedSessions.push(managedSession);
    }
    sessionExists(session) {
        return this.sessionManaged(session) !== undefined;
    }
    sessionManaged(session) {
        return this.managedSessions.find((el) => el.session.id === session.id);
    }
    sessionRemove(session) {
        this.managedSessions = this.managedSessions.filter((el) => el.session.id !== session.id);
    }
    /**
     * @param session
     * @param hold
     */
    async setHold(session, hold) {
        if (!this.sessionExists(session)) {
            return Promise.reject(new Error("Session does not exist."));
        }
        if (this.isHeld(session) === hold) {
            return Promise.resolve();
        }
        const sessionDescriptionHandler = session.sessionDescriptionHandler;
        if (!(sessionDescriptionHandler instanceof _session_description_handler_session_description_handler_js__WEBPACK_IMPORTED_MODULE_4__.SessionDescriptionHandler)) {
            throw new Error("Session's session description handler not instance of SessionDescriptionHandler.");
        }
        const options = {
            requestDelegate: {
                onAccept: () => {
                    const managedSession = this.sessionManaged(session);
                    if (managedSession !== undefined) {
                        managedSession.held = hold;
                        this.enableReceiverTracks(session, !managedSession.held);
                        this.enableSenderTracks(session, !managedSession.held && !managedSession.muted);
                        if (this.delegate && this.delegate.onCallHold) {
                            this.delegate.onCallHold(session, managedSession.held);
                        }
                    }
                },
                onReject: () => {
                    this.logger.warn(`[${session.id}] Re-invite request was rejected`);
                    const managedSession = this.sessionManaged(session);
                    if (managedSession !== undefined) {
                        managedSession.held = !hold;
                        this.enableReceiverTracks(session, !managedSession.held);
                        this.enableSenderTracks(session, !managedSession.held && !managedSession.muted);
                        if (this.delegate && this.delegate.onCallHold) {
                            this.delegate.onCallHold(session, managedSession.held);
                        }
                    }
                }
            }
        };
        const sessionDescriptionHandlerOptions = session.sessionDescriptionHandlerOptionsReInvite;
        sessionDescriptionHandlerOptions.hold = hold;
        session.sessionDescriptionHandlerOptionsReInvite = sessionDescriptionHandlerOptions;
        const managedSession = this.sessionManaged(session);
        if (!managedSession) {
            throw new Error("Managed session is undefiend.");
        }
        managedSession.held = hold;
        return session
            .invite(options)
            .then(() => {
            const managedSession = this.sessionManaged(session);
            if (managedSession !== undefined) {
                this.enableReceiverTracks(session, !managedSession.held);
                this.enableSenderTracks(session, !managedSession.held && !managedSession.muted);
            }
        })
            .catch((error) => {
            managedSession.held = !hold;
            if (error instanceof _api_exceptions_request_pending_js__WEBPACK_IMPORTED_MODULE_11__.RequestPendingError) {
                this.logger.error(`[${session.id}] A hold request is already in progress.`);
            }
            throw error;
        });
    }
    /**
     * @param session
     * @param mute
     */
    setMute(session, mute) {
        if (!this.sessionExists(session)) {
            this.logger.warn(`[${session.id}] A session is required to enabled/disable media tracks`);
            return;
        }
        if (session.state !== _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Established) {
            this.logger.warn(`[${session.id}] An established session is required to enable/disable media tracks`);
            return;
        }
        const managedSession = this.sessionManaged(session);
        if (managedSession !== undefined) {
            managedSession.muted = mute;
            this.enableSenderTracks(session, !managedSession.held && !managedSession.muted);
        }
    }
    setupLocalMedia(session) {
        const managedSession = this.sessionManaged(session);
        if (!managedSession) {
            throw new Error("Managed session does not exist.");
        }
        const mediaLocal = typeof this.options.media.local === "function" ? this.options.media.local(session) : this.options.media.local;
        managedSession.mediaLocal = mediaLocal;
        const mediaElement = mediaLocal === null || mediaLocal === void 0 ? void 0 : mediaLocal.video;
        if (mediaElement) {
            const localStream = this.getLocalMediaStream(session);
            if (!localStream) {
                throw new Error("Local media stream undefiend.");
            }
            mediaElement.srcObject = localStream;
            mediaElement.volume = 0;
            mediaElement.play().catch((error) => {
                this.logger.error(`[${session.id}] Failed to play local media`);
                this.logger.error(error.message);
            });
        }
    }
    setupRemoteMedia(session) {
        const managedSession = this.sessionManaged(session);
        if (!managedSession) {
            throw new Error("Managed session does not exist.");
        }
        const mediaRemote = typeof this.options.media.remote === "function" ? this.options.media.remote(session) : this.options.media.remote;
        managedSession.mediaRemote = mediaRemote;
        const mediaElement = (mediaRemote === null || mediaRemote === void 0 ? void 0 : mediaRemote.video) || (mediaRemote === null || mediaRemote === void 0 ? void 0 : mediaRemote.audio);
        if (mediaElement) {
            const remoteStream = this.getRemoteMediaStream(session);
            if (!remoteStream) {
                throw new Error("Remote media stream undefiend.");
            }
            mediaElement.autoplay = true;
            mediaElement.srcObject = remoteStream;
            mediaElement.play().catch((error) => {
                this.logger.error(`[${session.id}] Failed to play remote media`);
                this.logger.error(error.message);
            });
            remoteStream.onaddtrack = () => {
                this.logger.log(`Remote media onaddtrack`);
                mediaElement.load();
                mediaElement.play().catch((error) => {
                    this.logger.error(`[${session.id}] Failed to play remote media`);
                    this.logger.error(error.message);
                });
            };
        }
    }
    /**
     * @param session
     * @remarks
     */
    async terminate(session) {
        this.logger.log(`[${session.id}] Terminating...`);
        switch (session.state) {
            case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Initial:
                if (session instanceof _api_inviter_js__WEBPACK_IMPORTED_MODULE_7__.Inviter) {
                    return session.cancel().then(() => {
                        this.logger.log(`[${session.id}] Inviter never sent INVITE (canceled)`);
                    });
                }
                else if (session instanceof _api_invitation_js__WEBPACK_IMPORTED_MODULE_8__.Invitation) {
                    return session.reject().then(() => {
                        this.logger.log(`[${session.id}] Invitation rejected (sent 480)`);
                    });
                }
                else {
                    throw new Error("Unknown session type.");
                }
            case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Establishing:
                if (session instanceof _api_inviter_js__WEBPACK_IMPORTED_MODULE_7__.Inviter) {
                    return session.cancel().then(() => {
                        this.logger.log(`[${session.id}] Inviter canceled (sent CANCEL)`);
                    });
                }
                else if (session instanceof _api_invitation_js__WEBPACK_IMPORTED_MODULE_8__.Invitation) {
                    return session.reject().then(() => {
                        this.logger.log(`[${session.id}] Invitation rejected (sent 480)`);
                    });
                }
                else {
                    throw new Error("Unknown session type.");
                }
            case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Established:
                return session.bye().then(() => {
                    this.logger.log(`[${session.id}] Session ended (sent BYE)`);
                });
            case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Terminating:
                break;
            case _api_session_state_js__WEBPACK_IMPORTED_MODULE_12__.SessionState.Terminated:
                break;
            default:
                throw new Error("Unknown state");
        }
        this.logger.log(`[${session.id}] Terminating in state ${session.state}, no action taken`);
        return Promise.resolve();
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SimpleUser": () => ( _simple_user_js__WEBPACK_IMPORTED_MODULE_0__.SimpleUser)
 });
 var _simple_user_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(123);





 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "SimpleUser": () => ( SimpleUser)
 });
 var _session_manager_session_manager_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(121);

/**
 * @remarks
 * @public
 */
class SimpleUser {
    /**
     * @param server
     * @param options
     */
    constructor(server, options = {}) {
        this.session = undefined;
        this.delegate = options.delegate;
        this.options = Object.assign({}, options);
        const sessionManagerOptions = {
            aor: this.options.aor,
            delegate: {
                onCallAnswered: () => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallAnswered) === null || _b === void 0 ? void 0 : _b.call(_a); },
                onCallCreated: (session) => {
                    var _a, _b;
                    this.session = session;
                    (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallCreated) === null || _b === void 0 ? void 0 : _b.call(_a);
                },
                onCallReceived: () => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallReceived) === null || _b === void 0 ? void 0 : _b.call(_a); },
                onCallHangup: () => {
                    var _a, _b;
                    this.session = undefined;
                    ((_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallHangup) && ((_b = this.delegate) === null || _b === void 0 ? void 0 : _b.onCallHangup());
                },
                onCallHold: (s, held) => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallHold) === null || _b === void 0 ? void 0 : _b.call(_a, held); },
                onCallDTMFReceived: (s, tone, dur) => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onCallDTMFReceived) === null || _b === void 0 ? void 0 : _b.call(_a, tone, dur); },
                onMessageReceived: (message) => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onMessageReceived) === null || _b === void 0 ? void 0 : _b.call(_a, message.request.body); },
                onRegistered: () => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onRegistered) === null || _b === void 0 ? void 0 : _b.call(_a); },
                onUnregistered: () => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onUnregistered) === null || _b === void 0 ? void 0 : _b.call(_a); },
                onServerConnect: () => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onServerConnect) === null || _b === void 0 ? void 0 : _b.call(_a); },
                onServerDisconnect: () => { var _a, _b; return (_b = (_a = this.delegate) === null || _a === void 0 ? void 0 : _a.onServerDisconnect) === null || _b === void 0 ? void 0 : _b.call(_a); }
            },
            maxSimultaneousSessions: 1,
            media: this.options.media,
            reconnectionAttempts: this.options.reconnectionAttempts,
            reconnectionDelay: this.options.reconnectionDelay,
            registererOptions: this.options.registererOptions,
            sendDTMFUsingSessionDescriptionHandler: this.options.sendDTMFUsingSessionDescriptionHandler,
            userAgentOptions: this.options.userAgentOptions
        };
        this.sessionManager = new _session_manager_session_manager_js__WEBPACK_IMPORTED_MODULE_0__.SessionManager(server, sessionManagerOptions);
        this.logger = this.sessionManager.userAgent.getLogger("sip.SimpleUser");
    }
    /** @internal */
    get id() {
        return (this.options.userAgentOptions && this.options.userAgentOptions.displayName) || "Anonymous";
    }
    get localMediaStream() {
        return this.session && this.sessionManager.getLocalMediaStream(this.session);
    }
    get remoteMediaStream() {
        return this.session && this.sessionManager.getRemoteMediaStream(this.session);
    }
    /** @deprecated */
    get localAudioTrack() {
        return this.session && this.sessionManager.getLocalAudioTrack(this.session);
    }
    /** @deprecated */
    get localVideoTrack() {
        return this.session && this.sessionManager.getLocalVideoTrack(this.session);
    }
    /** @deprecated */
    get remoteAudioTrack() {
        return this.session && this.sessionManager.getRemoteAudioTrack(this.session);
    }
    /** @deprecated */
    get remoteVideoTrack() {
        return this.session && this.sessionManager.getRemoteVideoTrack(this.session);
    }
    connect() {
        this.logger.log(`[${this.id}] Connecting UserAgent...`);
        return this.sessionManager.connect();
    }
    disconnect() {
        this.logger.log(`[${this.id}] Disconnecting UserAgent...`);
        return this.sessionManager.disconnect();
    }
    isConnected() {
        return this.sessionManager.isConnected();
    }
    register(registererRegisterOptions) {
        this.logger.log(`[${this.id}] Registering UserAgent...`);
        return this.sessionManager.register(registererRegisterOptions);
    }
    unregister(registererUnregisterOptions) {
        this.logger.log(`[${this.id}] Unregistering UserAgent...`);
        return this.sessionManager.unregister(registererUnregisterOptions);
    }
    /**
     * @remarks
     * @param destination
     * @param inviterOptions
     * @param inviterInviteOptions
     */
    call(destination, inviterOptions, inviterInviteOptions) {
        this.logger.log(`[${this.id}] Beginning Session...`);
        if (this.session) {
            return Promise.reject(new Error("Session already exists."));
        }
        return this.sessionManager.call(destination, inviterOptions, inviterInviteOptions).then(() => {
            return;
        });
    }
    hangup() {
        this.logger.log(`[${this.id}] Hangup...`);
        if (!this.session) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.sessionManager.hangup(this.session).then(() => {
            this.session = undefined;
        });
    }
    /**
     * @remarks
     * @param invitationAcceptOptions
     */
    answer(invitationAcceptOptions) {
        this.logger.log(`[${this.id}] Accepting Invitation...`);
        if (!this.session) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.sessionManager.answer(this.session, invitationAcceptOptions);
    }
    decline() {
        this.logger.log(`[${this.id}] rejecting Invitation...`);
        if (!this.session) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.sessionManager.decline(this.session);
    }
    hold() {
        this.logger.log(`[${this.id}] holding session...`);
        if (!this.session) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.sessionManager.hold(this.session);
    }
    unhold() {
        this.logger.log(`[${this.id}] unholding session...`);
        if (!this.session) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.sessionManager.unhold(this.session);
    }
    isHeld() {
        return this.session ? this.sessionManager.isHeld(this.session) : false;
    }
    mute() {
        this.logger.log(`[${this.id}] disabling media tracks...`);
        return this.session && this.sessionManager.mute(this.session);
    }
    unmute() {
        this.logger.log(`[${this.id}] enabling media tracks...`);
        return this.session && this.sessionManager.unmute(this.session);
    }
    isMuted() {
        return this.session ? this.sessionManager.isMuted(this.session) : false;
    }
    /**
     * @remarks
     * @param tone
     */
    sendDTMF(tone) {
        this.logger.log(`[${this.id}] sending DTMF...`);
        if (!this.session) {
            return Promise.reject(new Error("Session does not exist."));
        }
        return this.sessionManager.sendDTMF(this.session, tone);
    }
    /**
     * @remarks
     * @param destination
     */
    message(destination, message) {
        this.logger.log(`[${this.id}] sending message...`);
        return this.sessionManager.message(destination, message);
    }
}


 }),
 ((__unused_webpack_module, __webpack_exports__, __webpack_require__) => {

__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Transport": () => ( _transport_js__WEBPACK_IMPORTED_MODULE_0__.Transport)
 });
 var _transport_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(58);




 })
	]);

	var __webpack_module_cache__ = {};

	function __webpack_require__(moduleId) {

		var cachedModule = __webpack_module_cache__[moduleId];
		if (cachedModule !== undefined) {
			return cachedModule.exports;
		}

		var module = __webpack_module_cache__[moduleId] = {


			exports: {}
		};

		__webpack_modules__[moduleId](module, module.exports, __webpack_require__);

		return module.exports;
	}

	(() => {

		__webpack_require__.d = (exports, definition) => {
			for(var key in definition) {
				if(__webpack_require__.o(definition, key) && !__webpack_require__.o(exports, key)) {
					Object.defineProperty(exports, key, { enumerable: true, get: definition[key] });
				}
			}
		};
	})();

	(() => {
		__webpack_require__.o = (obj, prop) => (Object.prototype.hasOwnProperty.call(obj, prop))
	})();

	(() => {

		__webpack_require__.r = (exports) => {
			if(typeof Symbol !== 'undefined' && Symbol.toStringTag) {
				Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
			}
			Object.defineProperty(exports, '__esModule', { value: true });
		};
	})();
var __webpack_exports__ = {};
(() => {
__webpack_require__.r(__webpack_exports__);
 __webpack_require__.d(__webpack_exports__, {
   "Ack": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Ack),
   "Bye": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Bye),
   "Cancel": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Cancel),
   "ContentTypeUnsupportedError": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.ContentTypeUnsupportedError),
   "Core": () => ( _core_index_js__WEBPACK_IMPORTED_MODULE_3__),
   "EmitterImpl": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.EmitterImpl),
   "Grammar": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_2__.Grammar),
   "Info": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Info),
   "Invitation": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Invitation),
   "Inviter": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Inviter),
   "Message": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Message),
   "Messager": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Messager),
   "NameAddrHeader": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_2__.NameAddrHeader),
   "Notification": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Notification),
   "Parameters": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_2__.Parameters),
   "Publisher": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Publisher),
   "PublisherState": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.PublisherState),
   "Referral": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Referral),
   "Registerer": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Registerer),
   "RegistererState": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.RegistererState),
   "RequestPendingError": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.RequestPendingError),
   "SIPExtension": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.SIPExtension),
   "Session": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Session),
   "SessionDescriptionHandlerError": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.SessionDescriptionHandlerError),
   "SessionState": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.SessionState),
   "SessionTerminatedError": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.SessionTerminatedError),
   "StateTransitionError": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.StateTransitionError),
   "Subscriber": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Subscriber),
   "Subscription": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.Subscription),
   "SubscriptionState": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.SubscriptionState),
   "TransportState": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.TransportState),
   "URI": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_2__.URI),
   "UserAgent": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.UserAgent),
   "UserAgentRegisteredOptionTags": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.UserAgentRegisteredOptionTags),
   "UserAgentState": () => ( _api_index_js__WEBPACK_IMPORTED_MODULE_1__.UserAgentState),
   "Web": () => ( _platform_web_index_js__WEBPACK_IMPORTED_MODULE_4__),
   "equivalentURI": () => ( _grammar_index_js__WEBPACK_IMPORTED_MODULE_2__.equivalentURI),
   "name": () => ( name),
   "version": () => ( version)
 });
 var _version_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(1);
 var _api_index_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(2);
 var _grammar_index_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(100);
 var _core_index_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(101);
 var _platform_web_index_js__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(114);

const version = _version_js__WEBPACK_IMPORTED_MODULE_0__.LIBRARY_VERSION;
const name = "sip.js";








})();

	return __webpack_exports__;
 })()
;
});