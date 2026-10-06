import logging
from unittest.mock import patch

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from .test_ingest_failure import TestMobileIngestFailure
from odoo.addons.phone_call.models.phone_call import number_key

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestMobileRetryAfterFailure(TestMobileIngestFailure):
    def _poisoned_partners(self):
        return patch.object(
            type(self.env["phone.call"]),
            "_match_partners",
            lambda self, numbers, company: {
                number_key(number): 2_000_000_000 for number in numbers
            },
        )

    def _device_calls(self):
        return self.env["phone.call"].search([("device_id", "=", self.device.id)])

    def test_a_batch_resent_after_a_failed_ingest_is_stored(self):
        body = self._calls(1, offset=300)
        with self._poisoned_partners():
            failed = self._push("calllog", body)
        self.assertEqual(failed.status_code, 500, failed.text)

        retried = self._push("calllog", body)
        _logger.debug(
            "retry after a failed ingest answered %s %s; exchanges %s",
            retried.status_code,
            retried.text,
            self._events().mapped(lambda event: (event.id, event.state)),
        )
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(len(self._device_calls()), 1)

    def test_a_recording_resent_after_a_failed_store_is_stored(self):
        body = {
            "recorded_at": 1_767_225_600_000,
            "file_name": "call.m4a",
            "mimetype": "audio/mp4",
            "audio_b64": "AAAA",
        }
        with patch.object(
            type(self.env["phone.call"]),
            "_match_device_call",
            side_effect=RuntimeError("simulated store failure"),
        ):
            failed = self._push("recording", body)
        self.assertEqual(failed.status_code, 500, failed.text)

        retried = self._push("recording", body)
        _logger.debug(
            "recording retry answered %s %s", retried.status_code, retried.text
        )
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(
            self.env["ir.attachment"].search_count(
                [
                    ("res_model", "=", "phone.call"),
                    ("res_id", "in", self._device_calls().ids),
                ]
            ),
            1,
        )

    def test_a_batch_resent_after_a_refused_token_is_stored(self):
        body = self._calls(1, offset=400)
        refused = self.url_open(
            "/remote/mobile/PHONE-FAILURE-001/calllog",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong",
            },
        )
        _logger.debug("wrong token answered %s %s", refused.status_code, refused.text)
        self.assertEqual(refused.status_code, 401, refused.text)

        retried = self._push("calllog", body)
        _logger.debug(
            "retry after a refused token answered %s %s; exchanges %s",
            retried.status_code,
            retried.text,
            self._events().mapped(lambda event: (event.id, event.state)),
        )
        self.assertEqual(retried.status_code, 200, retried.text)

    def test_a_row_resent_after_the_cap_was_raised_is_stored(self):
        self.device.sudo().write({"max_payload_size": 100})
        body = self._calls(1, offset=500)
        refused = self._push("calllog", body)
        _logger.debug("over the cap answered %s %s", refused.status_code, refused.text)
        self.assertEqual(refused.status_code, 413, refused.text)

        self.device.sudo().write({"max_payload_size": 52428800})
        retried = self._push("calllog", body)
        _logger.debug(
            "retry after the cap was raised answered %s %s; exchanges %s",
            retried.status_code,
            retried.text,
            self._events().mapped(lambda event: (event.id, event.state)),
        )
        self.assertEqual(retried.status_code, 200, retried.text)
