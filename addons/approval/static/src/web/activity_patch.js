/** @odoo-module native */
import { Approval } from "@approval/web/approval";
import { Activity } from "@mail/core/web/activity";

Object.assign(Activity.components, { Approval });
