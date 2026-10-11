import re
from unittest.mock import patch

from odoo.fields import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase

from odoo.addons.bus.tools.channel_capability import resolve_capability
from odoo.addons.survey.tests import common


@tagged("post_install", "-at_install")
class TestSessionHostRoutes(common.TestSurveyCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host = new_test_user(
            cls.env,
            login="session_host",
            groups="base.group_user,survey.group_survey_manager",
        )
        cls.form = cls.env["survey.survey"].create(
            {
                "title": "Live session",
                "access_mode": "public",
                "users_login_required": False,
                "questions_layout": "page_per_question",
            }
        )
        cls.question = cls.env["survey.question"].create(
            {
                "title": "Pick one",
                "survey_id": cls.form.id,
                "question_type": "simple_choice",
                "suggested_answer_ids": [
                    Command.create({"value": "A"}),
                    Command.create({"value": "B"}),
                ],
            }
        )

    def _rpc(self, route, **params):
        response = self.url_open(
            route,
            data=json_dumps(
                {"jsonrpc": "2.0", "method": "call", "params": params, "id": 1}
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json().get("result")

    def _open_session(self):
        self.form.action_start_session()
        self.form.write(
            {
                "session_state": "in_progress",
                "session_question_id": self.question.id,
            }
        )

    def test_next_question_advances_a_ready_session(self):
        self.form.action_start_session()
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/next_question/{self.form.access_token}")
        (fragment,) = result["fragments"]
        self.assertEqual(
            (fragment["key"], fragment["swap"]), ("survey.session_manage", "outer")
        )
        self.assertIn('data-fragment="survey.session_manage"', fragment["html"])
        self.assertIn("background_image_url", result["data"])
        self.form.invalidate_recordset(["session_state"])
        self.assertEqual(self.form.session_state, "in_progress")

    def test_next_question_without_a_session_says_it_ended(self):
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/next_question/{self.form.access_token}")
        self.assertEqual((result["fragments"], result["data"]), ([], {"ended": True}))

    def test_going_back_is_rendered_on_the_screen_the_server_answers(self):
        self.env["survey.question"].create(
            {"title": "Second", "survey_id": self.form.id, "question_type": "char_box"}
        )
        self.form.action_start_session()
        self.authenticate("session_host", "session_host")
        self._rpc(f"/survey/session/next_question/{self.form.access_token}")
        self._rpc(f"/survey/session/next_question/{self.form.access_token}")
        result = self._rpc(
            f"/survey/session/next_question/{self.form.access_token}", go_back=True
        )
        self.assertIn('data-going-back="True"', result["fragments"][0]["html"])

    def test_results_are_served_for_a_live_session(self):
        self._open_session()
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/results/{self.form.access_token}")
        self.assertIsInstance(result, dict)
        self.assertTrue(result)
        self.assertNotIn(
            "is_html_empty", result, "a template helper is not a JSON value"
        )

    def test_results_are_refused_without_a_live_session(self):
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/results/{self.form.access_token}")
        self.assertFalse(result)

    def _attendee(self, score=5):
        answer = self.env["survey.user_input"].create(
            {
                "survey_id": self.form.id,
                "nickname": "Ana",
                "is_session_answer": True,
                "state": "in_progress",
            }
        )
        self.env["survey.user_input.line"].create(
            {
                "user_input_id": answer.id,
                "question_id": self.question.id,
                "answer_type": "suggestion",
                "suggested_answer_id": self.question.suggested_answer_ids[0].id,
                "answer_score": score,
                "skipped": False,
            }
        )
        return answer

    def test_leaderboard_renders_the_ranked_attendees(self):
        self._open_session()
        self._attendee()
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/leaderboard/{self.form.access_token}")
        (fragment,) = result["fragments"]
        self.assertEqual(fragment["key"], "survey.session_leaderboard")
        self.assertIn("Ana", fragment["html"])

    def test_leaderboard_is_empty_without_attendees(self):
        self._open_session()
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/leaderboard/{self.form.access_token}")
        (fragment,) = result["fragments"]
        self.assertNotIn("o_survey_session_leaderboard_item", fragment["html"])

    def test_leaderboard_is_empty_without_a_live_session(self):
        self.authenticate("session_host", "session_host")
        result = self._rpc(f"/survey/session/leaderboard/{self.form.access_token}")
        self.assertEqual(result["fragments"], [])

    def test_unknown_token_yields_no_session_data(self):
        self.authenticate("session_host", "session_host")
        self.assertFalse(self._rpc("/survey/session/results/not-a-token"))
        self.assertEqual(
            self._rpc("/survey/session/leaderboard/not-a-token")["fragments"], []
        )

    def test_a_session_speaks_on_its_capability_and_never_names_its_token(self):
        self.form.action_start_session()
        self.authenticate("session_host", "session_host")
        sent = []
        with patch.object(
            type(self.env["bus.bus"]),
            "_sendone",
            lambda _bus, target, notification_type, _message: sent.append(
                (target, notification_type)
            ),
        ):
            self._rpc(f"/survey/session/next_question/{self.form.access_token}")
            self.form.action_end_session()
        target = self.form._session_bus_target()
        self.assertEqual(sent, [(target, "next_question"), (target, "end_session")])
        self.assertEqual(
            resolve_capability(self.env, self.form._session_bus_channel()), target
        )
        self.assertNotIn(self.form.access_token, repr(sent))

    def test_a_participant_is_handed_the_session_capability(self):
        self._open_session()
        self.authenticate(None, None)
        page = self.url_open(f"/s/{self.form.session_code}").text
        channel = re.search(r'data-session-bus-channel="([^"]+)"', page)
        self.assertTrue(channel, "a session participant's page names its channel")
        self.assertEqual(
            resolve_capability(self.env, channel.group(1)),
            self.form._session_bus_target(),
        )

    def test_a_participant_page_follows_the_host_over_the_bus(self):
        self.env["survey.question"].create(
            {
                "title": "Live bus probe",
                "survey_id": self.form.id,
                "question_type": "text_box",
            }
        )
        self._open_session()
        code = """
            (async () => {
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const until = async (predicate) => {
                    for (let i = 0; i < 150 && !predicate(); i++) {
                        await wait(100);
                    }
                    return predicate();
                };
                const shows = (text) => document.body.innerText.includes(text);
                if (!(await until(() => shows("Pick one")))) {
                    console.error("the participant never saw the first question");
                    return;
                }
                await wait(1500);
                await fetch("/survey/session/next_question/%(token)s", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} }),
                });
                if (await until(() => shows("Live bus probe"))) {
                    console.log("test successful");
                } else {
                    console.error("the host's next question never reached the participant");
                }
            })();
        """ % {"token": self.form.access_token}
        self.browser_js(
            f"/s/{self.form.session_code}", code, login="session_host", timeout=60
        )

    def test_the_host_page_loads_each_script_once(self):
        IrAsset = self.env["ir.asset"]
        params = IrAsset._prepare_assets_params()
        bundles = (
            "web.assets_frontend",
            "survey.survey_assets",
            "survey.survey_user_input_session_assets",
        )
        seen = {}
        for bundle in bundles:
            for entry in IrAsset._get_asset_paths(bundle, params):
                if entry.path.endswith(".js"):
                    seen.setdefault(entry.path, []).append(bundle)
        twice = {path: owners for path, owners in seen.items() if len(owners) > 1}
        self.assertFalse(twice, "a script in two bundles runs, and registers, twice")

    def test_the_host_walks_the_screens_the_server_answers(self):
        self.question.write(
            {
                "title": "Scored question",
                "suggested_answer_ids": [
                    Command.clear(),
                    Command.create(
                        {"value": "A", "is_correct": True, "answer_score": 1}
                    ),
                    Command.create({"value": "B"}),
                ],
            }
        )
        self.env["survey.question"].create(
            {
                "title": "Last question",
                "survey_id": self.form.id,
                "question_type": "char_box",
                "save_as_nickname": True,
            }
        )
        self.form.scoring_type = "scoring_with_answers"
        self.form.action_start_session()
        self._attendee()

        self.start_tour(
            f"/survey/session/manage/{self.form.access_token}",
            "survey_session_host_screens",
            login="session_host",
        )
