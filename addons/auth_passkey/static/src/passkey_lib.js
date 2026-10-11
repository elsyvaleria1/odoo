/** @odoo-module native */
import { startAuthentication, startRegistration } from "../lib/simplewebauthn.js";

export const passkeyLib = { startAuthentication, startRegistration };
