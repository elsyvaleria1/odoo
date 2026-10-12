import functools
import random
from urllib.parse import urlsplit

from odoo.tools import mail

from odoo.addons.link_tracker.tests.common import MockLinkTracker
from odoo.addons.mass_mailing.tests.common import MassMailCommon
from odoo.addons.sms.tests.common import SMSCase, SMSCommon


def _is_sms_trace_matching(number, status, record, trace):
    return (
        trace.sms_number == number
        and trace.trace_status == status
        and (trace.res_id == record.id if record else True)
    )


class MassSMSCase(SMSCase, MockLinkTracker):
    def assertSMSStatistics(self, recipients_info, mailing, records, check_sms=True):
        return self.assertSMSTraces(
            recipients_info, mailing, records, check_sms=check_sms
        )

    def assertSMSTraces(
        self,
        recipients_info,
        mailing,
        records,
        check_sms=True,
        is_cancel_not_sent=True,
        sent_unlink=False,
        sms_links_info=None,
    ):
        state_mapping = {
            "sent": "sent",
            "outgoing": "outgoing",
            "error": "error",
            "cancel": "canceled",
            "bounce": "error",
            "process": "process",
            "pending": "pending",
        }
        traces = self.env["mailing.trace"].search(
            [("mass_mailing_id", "in", mailing.ids), ("res_id", "in", records.ids)]
        )
        debug_info = "\n".join(
            f"Trace: to {t.sms_number} - state {t.trace_status} - res_id {t.res_id}"
            for t in traces
        )

        traces_info = []
        for trace in traces:
            record = records.filtered_domain([("id", "=", trace.res_id)])
            if record:
                traces_info.append(
                    f"Trace: doc {trace.res_id} on {trace.sms_number} - status {trace.trace_status} (rec {record.id})"
                )
            else:
                traces_info.append(
                    f"Trace: doc {trace.res_id} on {trace.sms_number} - status {trace.trace_status}"
                )
        debug_info = "\n".join(traces_info)
        self.assertTrue(all(s.model == records._name for s in traces))
        self.assertEqual(
            {s.res_id for s in traces},
            set(records.ids),
            f"Should find one trace / record. Found\n{debug_info}",
        )

        if not sms_links_info:
            sms_links_info = [None] * len(recipients_info)
        for recipient_info, link_info, record in zip(
            recipients_info, sms_links_info, records, strict=True
        ):
            invalid = set(recipient_info.keys()) - {
                "content",
                "record",
                "number",
                "partner",
                "failure_type",
                "trace_status",
                "check_sms",
            }
            if invalid:
                raise AssertionError(f"assertSMSTraces: invalid input {invalid}")

            partner = recipient_info.get("partner", self.env["res.partner"])
            number = recipient_info.get("number")
            if number is None and partner:
                number = partner._sms_get_recipients_info()[partner.id]["sanitized"]
            status = recipient_info.get("trace_status", "outgoing")
            failure_type = (
                recipient_info["failure_type"]
                if status in ("error", "cancel", "bounce")
                else None
            )
            content = recipient_info.get("content", None)
            record = record or recipient_info.get("record")
            recipient_check_sms = recipient_info.get("check_sms", check_sms)

            trace = traces.filtered(
                functools.partial(_is_sms_trace_matching, number, status, record)
            )
            self.assertTrue(
                len(trace) == 1,
                "SMS: found %s notification for number %s (res_id: %s) (status: %s) (1 expected)\n--MOCKED DATA\n%s"
                % (len(trace), number, record.id, status, debug_info),
            )
            sms_not_created = is_cancel_not_sent and trace.trace_status == "cancel"
            self.assertTrue(sms_not_created or bool(trace.sms_id_int))
            if sms_not_created:
                self.assertFalse(trace.sms_id_int)
                self.assertFalse(
                    self.env["mail.message"]
                    .sudo()
                    .search(
                        [
                            ("model", "=", record._name),
                            ("res_id", "=", record.id),
                            ("id", "in", self._new_sms.mail_message_id.ids),
                        ]
                    )
                )

            if recipient_check_sms and not sms_not_created:
                if status in {"process", "pending", "sent"}:
                    if sent_unlink:
                        self.assertSMSIapSent([number], content=content)
                    else:
                        self.assertSMS(partner, number, status, content=content)
                elif status in state_mapping:
                    sms_state = state_mapping[status]
                    self.assertSMS(
                        partner,
                        number,
                        sms_state,
                        failure_type=failure_type,
                        content=content,
                    )
                else:
                    raise NotImplementedError

            if link_info and not sms_not_created:
                sms_sent = self._find_sms_sent(partner, number)
                sms_sms = self._find_sms_sms(partner, number, state_mapping[status])
                for url, is_shortened, add_link_params in link_info:
                    if url == "unsubscribe":
                        url = "%s/sms/%d/%s" % (
                            mailing.get_base_url(),
                            mailing.id,
                            trace.sms_code,
                        )
                    link_params = {"utm_medium": "SMS", "utm_source": mailing.name}
                    if add_link_params:
                        link_params.update(**add_link_params)
                    self.assertLinkShortenedText(
                        sms_sms.body,
                        (url, is_shortened),
                        link_params=link_params,
                    )
                    self.assertLinkShortenedText(
                        sms_sent["body"],
                        (url, is_shortened),
                        link_params=link_params,
                    )
        return traces

    def gateway_sms_bounce(self, mailing, records, error_code="invalid_destination"):
        traces = mailing.mailing_trace_ids.filtered(
            lambda t: t.model == records._name and t.res_id in records.ids
        )
        statuses = [
            {
                "sms_status": error_code,
                "uuids": traces.sms_tracker_ids.mapped("sms_uuid"),
            }
        ]
        with self.with_user(self.user_admin.login):
            self._make_webhook_jsonrpc_request(statuses)

    def gateway_sms_click(self, mailing, record, use_sent_sms=True):
        trace = mailing.mailing_trace_ids.filtered(
            lambda t: t.model == record._name and t.res_id == record.id
        )
        if use_sent_sms:
            sms_sent = self._find_sms_sent(self.env["res.partner"], trace.sms_number)
            self.assertTrue(bool(sms_sent))
            return self.gateway_sms_sent_click(sms_sent)
        sms_sms = self._find_sms_sms(
            record._mail_get_partners()[record.id], trace.sms_number, "outgoing"
        )
        self.assertTrue(bool(sms_sms))
        with self.with_user(self.user_admin.login):
            return self.gateway_sms_sms_click(sms_sms)

    def gateway_sms_delivered(self, mailing, records):
        traces = mailing.mailing_trace_ids.filtered(
            lambda t: t.model == records._name and t.res_id in records.ids
        )
        with self.with_user(self.user_admin.login):
            statuses = [
                {
                    "sms_status": "delivered",
                    "uuids": traces.with_user(self.user_admin).sms_tracker_ids.mapped(
                        "sms_uuid"
                    ),
                }
            ]
            self._make_webhook_jsonrpc_request(statuses)

    def gateway_sms_sent_click(self, sms_sent):
        return self._gateway_sms_click(sms_sent["body"])

    def gateway_sms_sms_click(self, sms_sms):
        return self._gateway_sms_click(sms_sms.body)

    def _gateway_sms_click(self, body):
        for url in mail.TEXT_URL_REGEX.findall(body):
            if "/r/" in url:
                parsed_url = urlsplit(url)
                path_items = parsed_url.path.split("/")
                code, sms_id_int = path_items[2], int(path_items[4])
                trace_id = (
                    self.env["mailing.trace"]
                    .sudo()
                    .search([("sms_id_int", "=", sms_id_int)])
                    .id
                )

                self.env["link.tracker.click"].sudo().add_click(
                    code,
                    ip="100.200.300.%3f" % random.random(),
                    country_code="BE",
                    mailing_trace_id=trace_id,
                )


class MassSMSCommon(SMSCommon, MassSMSCase, MassMailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
