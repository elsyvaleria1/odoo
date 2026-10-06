from odoo.tests import TransactionCase, tagged

from ..models.followup_request import FollowupRequest


@tagged("post_install", "-at_install")
class TestFollowupRequestChannels(TransactionCase):
    def test_default_and_explicit_channel_selection(self):
        request = FollowupRequest(partner=None, followup_line=None)
        for channel in ("email", "sms", "snailmail", "whatsapp", "extension"):
            for default in (False, True):
                self.assertIs(request.is_channel_enabled(channel, default), default)
                for enabled in (False, True):
                    override = request.with_channel(channel, enabled)
                    self.assertIs(
                        override.is_channel_enabled(channel, default), enabled
                    )
                    self.assertNotIn(channel, request.channels)

    def test_changed_request_keeps_immutable_independent_overrides(self):
        request = FollowupRequest(partner=None, followup_line=None).with_channel(
            "email", True
        )
        changed = request.with_channel("sms", False)
        self.assertEqual(dict(request.channels), {"email": True})
        self.assertEqual(dict(changed.channels), {"email": True, "sms": False})
        with self.assertRaises(TypeError):
            changed.channels["email"] = False
