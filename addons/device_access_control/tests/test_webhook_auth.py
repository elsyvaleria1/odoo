from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase, NarrowedReceiver

AUTH_MODE_PARAM = "device_access_control.auth_mode"


@tagged("post_install", "-at_install")
class TestAccessDeviceWebhookAuth(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env.ref(
            "device_access_control.device_kind_access_control",
            raise_if_not_found=False,
        ) or cls.env["device.kind"].search([("code", "=", "access_control")], limit=1)
        cls.config = cls._create_device_profile(name="Access Auth Config")
        cls.device = cls._create_device_device(
            config=cls.config,
            name="Front Door Reader",
            identifier="DS-K1T671M-TEST",
            device_category_id=cls.category.id,
        )
        cls.token = cls.device.credential_id.sudo().credential_value
        cls.env["ir.config_parameter"].sudo().set_param(AUTH_MODE_PARAM, "enforce")

    def _event_payload(self, name="Impersonated Person"):
        return {
            "eventType": "AccessControllerEvent",
            "dateTime": "2026-08-09T03:14:00-06:00",
            "AccessControllerEvent": {
                "majorEventType": 5,
                "subEventType": 75,
                "employeeNoString": "E-007",
                "cardNo": "9988776655",
                "name": name,
                "serialNo": "999",
                "attendanceStatus": "checkIn",
            },
        }

    def _pending_command(self):
        return self.env["access.command"].create(
            {
                "device_id": self.device.id,
                "command_type": "open_door",
                "payload": '{"door": 1}',
            }
        )

    def _bearer(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_identifier_alone_cannot_forge_an_event(self):
        before = self.env["access.event"].search_count([])
        self.url_open(
            f"/access_device/webhook/{self.device.identifier}",
            json=self._event_payload(),
        )
        self.assertEqual(
            self.env["access.event"].search_count([]),
            before,
            "an event was created by a caller presenting only the serial number",
        )

    def test_identifier_alone_cannot_read_or_drain_the_command_queue(self):
        command = self._pending_command()
        response = self.url_open(f"/access_device/commands/{self.device.identifier}")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("open_door", response.text)
        command.invalidate_recordset()
        self.assertEqual(
            command.state,
            "pending",
            "an unauthenticated poll consumed a real command",
        )

    def test_identifier_alone_cannot_fake_a_heartbeat(self):
        self.device.write({"connection_state": "disconnected"})
        self.env.flush_all()
        self.url_open(
            f"/access_device/heartbeat/{self.device.identifier}", method="POST"
        )
        self.device.invalidate_recordset()
        self.assertEqual(self.device.connection_state, "disconnected")

    def test_identifier_alone_cannot_report_a_command_result(self):
        command = self._pending_command()
        self.url_open(
            f"/access_device/result/{self.device.identifier}",
            json={"command_id": command.id, "success": True},
        )
        command.invalidate_recordset()
        self.assertEqual(command.state, "pending")

    def test_the_token_bearer_can_do_all_four(self):
        before = self.env["access.event"].search_count([])
        self.url_open(
            f"/access_device/webhook/{self.device.identifier}",
            json=self._event_payload("Genuine Person"),
            headers=self._bearer(),
        )
        self.assertEqual(self.env["access.event"].search_count([]), before + 1)

        command = self._pending_command()
        response = self.url_open(
            f"/access_device/commands/{self.device.identifier}",
            headers=self._bearer(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("open_door", response.text)
        command.invalidate_recordset()
        self.assertEqual(command.state, "sent")

        self.device.write({"connection_state": "disconnected"})
        self.env.flush_all()
        beat = self.url_open(
            f"/access_device/heartbeat/{self.device.identifier}",
            method="POST",
            headers=self._bearer(),
        )
        self.assertEqual(beat.status_code, 200, beat.text[:200])
        self.device.invalidate_recordset()
        self.assertEqual(
            self.device.connection_state,
            "connected",
            "an authenticated heartbeat must mark the reader connected",
        )

    def test_x_device_token_header_also_works(self):
        response = self.url_open(
            f"/access_device/commands/{self.device.identifier}",
            headers={"X-Device-Token": self.token},
        )
        self.assertEqual(response.status_code, 200)

    def test_a_non_access_device_token_is_not_accepted_here(self):
        tracker = self._create_device_device(
            config=self.config, name="Fleet Tracker", identifier="GPS-NOT-A-DOOR"
        )
        response = self.url_open(
            f"/access_device/commands/{tracker.identifier}",
            headers={
                "Authorization": f"Bearer {tracker.credential_id.sudo().credential_value}"
            },
        )
        # No access-control device answers to that identifier: it is unknown
        # here, whatever it is elsewhere.
        self.assertEqual(response.status_code, 404)

    def test_audit_mode_keeps_unprovisioned_readers_working(self):
        self.env["ir.config_parameter"].sudo().set_param(AUTH_MODE_PARAM, "audit")
        before = self.env["access.event"].search_count([])
        self.url_open(
            f"/access_device/webhook/{self.device.identifier}",
            json=self._event_payload("Legacy Reader"),
        )
        self.assertEqual(self.env["access.event"].search_count([]), before + 1)
        self.env["ir.config_parameter"].sudo().set_param(AUTH_MODE_PARAM, "enforce")

    def test_shipped_default_is_enforce(self):
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", AUTH_MODE_PARAM)]
        ).unlink()
        self.assertEqual(self.device._inbound_auth_mode(), "enforce")

    def test_an_access_device_reads_its_mode_parameter_by_itself(self):
        self.env["ir.config_parameter"].sudo().set_param(AUTH_MODE_PARAM, "audit")
        self.assertEqual(self.device._inbound_auth_mode(), "audit")
        self.env["ir.config_parameter"].sudo().set_param(AUTH_MODE_PARAM, "enforce")

    def _exchanges(self):
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"device.device,{self.device.id}")]
        )

    def test_an_admitted_event_is_recorded_as_an_exchange(self):
        self.url_open(
            f"/access_device/webhook/{self.device.identifier}",
            json=self._event_payload(),
            headers=self._bearer(),
        )

        call = self._exchanges().filtered(lambda row: row.event_type == "access_event")
        self.assertEqual(len(call), 1)
        self.assertEqual(call.state, "success")
        self.assertIn("AccessControllerEvent", call.request_payload)

    def test_an_unknown_reader_is_recorded_in_the_access_log(self):
        self.url_open("/access_device/heartbeat/NO-SUCH-READER", data=b"{}")

        row = self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("refusal_reason", "=", "endpoint_not_found"),
                ("channel_name", "like", "device.device:%"),
            ]
        )
        self.assertIn("NO-SUCH-READER", row.channel_name)


@tagged("post_install", "-at_install")
class TestAccessDeviceWebhookWithoutSu(NarrowedReceiver, TestAccessDeviceWebhookAuth):
    def _post_badge(self, badge):
        payload = self._event_payload("Badge holder")
        payload["AccessControllerEvent"]["employeeNoString"] = badge
        payload["AccessControllerEvent"]["serialNo"] = badge
        self.url_open(
            f"/access_device/webhook/{self.device.identifier}",
            json=payload,
            headers=self._bearer(),
        )
        return self.env["access.event"].search(
            [("device_id", "=", self.device.id), ("event_uid", "=", badge)]
        )

    def test_a_badge_names_the_employee_of_the_reader_s_company(self):
        employee = self.env["hr.employee"].create(
            {"name": "Door Walker", "barcode": "BHOME1"}
        )

        event = self._post_badge("BHOME1")

        self.assertEqual(event.employee_id, employee)
        self.assertEqual(event.create_uid, self.env.ref("device.user_device_receiver"))

    def test_a_badge_never_names_an_employee_of_another_company(self):
        other_company = self.env["res.company"].create({"name": "Badge tenant"})
        self.env["hr.employee"].create(
            {
                "name": "Elsewhere",
                "barcode": "BAWAY1",
                "company_id": other_company.id,
            }
        )

        event = self._post_badge("BAWAY1")

        self.assertTrue(event, "the event is filed")
        self.assertFalse(event.employee_id)
