from odoo.addons.test_discuss_full.tests.test_performance import (
    TestDiscussFullPerformance,
)

TestDiscussFullPerformance._query_count_init_store += 6
TestDiscussFullPerformance._query_count_init_messaging += 1
TestDiscussFullPerformance._query_count_messaging_menu_channels += 1

old_get_init_store_data_result = TestDiscussFullPerformance._get_init_store_data_result


def _get_init_store_data_result(self):
    res = old_get_init_store_data_result(self)
    provider = self.env.ref("voip.default_voip_provider").sudo()
    res["Store"].update(
        {
            "helpdesk_livechat_active": False,
            "has_access_create_ticket": False,
            "voipConfig": {
                "callActivityTypeId": self.env.ref("mail.mail_activity_data_call").id,
                "mode": "demo",
                "missedCalls": 0,
                "pbxAddress": "localhost",
                "recordingPolicy": provider.recording_policy or "disabled",
                "webSocketUrl": provider.ws_server or "ws://localhost",
            },
        }
    )
    res["Store"]["settings"].update(
        {
            "homemenu_config": False,
            "how_to_call_on_mobile": "ask",
            "do_not_disturb_until_dt": False,
            "external_device_number": False,
            "onsip_auth_username": False,
            "should_call_from_another_device": False,
            "voip_provider_id": (provider.id, provider.name),
            "voip_secret": False,
            "voip_username": False,
            "color_scheme": "system",
        }
    )
    return res


TestDiscussFullPerformance._get_init_store_data_result = _get_init_store_data_result
