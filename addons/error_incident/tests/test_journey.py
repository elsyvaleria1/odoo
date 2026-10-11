from odoo.libs.json import loads as json_loads
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.error_incident.models.error_incident import (
    JOURNEY_NOTIFICATION,
    capture_payload,
)


def _fail():
    raise ValueError("the journey")


def _payload(**kwargs):
    try:
        _fail()
    except ValueError as exc:
        return capture_payload(exc, "request", **kwargs)
    raise AssertionError


class JourneyCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Incident = cls.env["error.incident"]
        cls.employee = new_test_user(
            cls.env, "journey.employee", groups="base.group_user", lang="en_US"
        )
        cls.colleague = new_test_user(
            cls.env, "journey.colleague", groups="base.group_user"
        )
        cls.portal = new_test_user(
            cls.env, "journey.portal", groups="base.group_portal"
        )

    def _capture(self, user, ref):
        return self.Incident.browse(
            self.Incident._capture(_payload(user_id=user.id, occurrence_ref=ref))
        )

    def _sent(self):
        users = {
            user.partner_id.id: user
            for user in (self.employee, self.colleague, self.portal)
        }
        sent = []
        for value in self.env.cr.precommit.data.get("bus.bus.values", []):
            channel = json_loads(value["channel"])
            message = json_loads(value["message"])
            if channel[1] == "res.partner" and channel[2] in users:
                sent.append((users[channel[2]], message["type"], message["payload"]))
        return sent

    def _forget_sent(self):
        self.env.cr.precommit.data.pop("bus.bus.values", None)


@tagged("post_install", "-at_install")
class TestJourney(JourneyCase):
    def test_each_state_is_a_step_or_an_outcome(self):
        incident = self._capture(self.employee, "j-state")
        expected = {
            "new": ("recorded", None, False),
            "acknowledged": ("acknowledged", None, False),
            "resolved": ("resolved", None, False),
            "regressed": ("recorded", None, True),
            "set_aside": ("recorded", "set_aside", False),
        }
        for state, (step, outcome, regressed) in expected.items():
            incident.incident_state = state
            journey = incident._journey()
            self.assertEqual(
                (journey["step"], journey["outcome"], journey["details"]["regressed"]),
                (step, outcome, regressed),
                state,
            )
            self.assertEqual(journey["steps"], ["recorded", "acknowledged", "resolved"])
            self.assertEqual(journey["incident"], incident.id)

    def test_a_capture_names_its_occurrence_to_whoever_hit_it(self):
        self._capture(self.employee, "j-own")
        [(user, kind, journey)] = self._sent()
        self.assertEqual((user, kind), (self.employee, JOURNEY_NOTIFICATION))
        self.assertEqual(journey["occurrence"], "j-own")
        self.assertEqual(journey["details"]["count"], 1)

    def test_a_capture_is_news_to_nobody_else(self):
        self._capture(self.employee, "j-a")
        self._forget_sent()
        self._capture(self.colleague, "j-b")
        self.assertEqual([user for user, *_ in self._sent()], [self.colleague])

    def test_a_portal_user_is_sent_nothing(self):
        self._capture(self.portal, "j-portal")
        self.assertEqual(self._sent(), [])

    def test_a_regression_reaches_everyone_it_affected(self):
        incident = self._capture(self.employee, "j-r1")
        self._capture(self.colleague, "j-r2")
        incident.incident_state = "resolved"
        self._forget_sent()
        self._capture(self.colleague, "j-r3")
        sent = {user: journey for user, _kind, journey in self._sent()}
        self.assertEqual(set(sent), {self.employee, self.colleague})
        self.assertNotIn("occurrence", sent[self.employee])
        self.assertEqual(sent[self.colleague]["occurrence"], "j-r3")
        self.assertTrue(sent[self.employee]["details"]["regressed"])

    def test_a_state_change_is_pushed_and_a_fix_announced(self):
        incident = self._capture(self.employee, "j-fix")
        self._capture(self.portal, "j-fix-portal")
        self._forget_sent()
        incident.action_acknowledge()
        self.assertEqual(
            [(user, kind) for user, kind, _ in self._sent()],
            [(self.employee, JOURNEY_NOTIFICATION)],
        )
        self._forget_sent()
        incident.action_resolve()
        sent = self._sent()
        self.assertEqual(
            [(user, kind) for user, kind, _ in sent],
            [
                (self.employee, JOURNEY_NOTIFICATION),
                (self.employee, "simple_notification"),
            ],
        )
        notice = sent[1][2]
        self.assertEqual(notice["title"], "An error you ran into was fixed")
        self.assertEqual(notice["message"], incident.name)

    def test_writing_the_same_state_is_no_news(self):
        incident = self._capture(self.employee, "j-same")
        self._forget_sent()
        incident.write({"incident_state": "new"})
        incident.write({"name": "Renamed"})
        self.assertEqual(self._sent(), [])


@tagged("post_install", "-at_install")
class TestOwnIncident(JourneyCase):
    def test_a_user_finds_the_incident_of_their_own_occurrence(self):
        incident = self._capture(self.employee, "o-own")
        Occurrence = self.env["error.occurrence"].with_user(self.employee)
        self.assertEqual(Occurrence._own_incident("o-own"), incident)
        self.assertEqual(
            Occurrence._own_incident("o-own")._journey()["step"], "recorded"
        )

    def test_nobody_else_does(self):
        self._capture(self.employee, "o-theirs")
        Occurrence = self.env["error.occurrence"].with_user(self.colleague)
        self.assertFalse(Occurrence._own_incident("o-theirs"))

    def test_an_unknown_or_malformed_reference_finds_nothing(self):
        Occurrence = self.env["error.occurrence"].with_user(self.employee)
        for ref in ("o-missing", "", None, 42, ["o-own"]):
            self.assertFalse(Occurrence._own_incident(ref), ref)


@tagged("post_install", "-at_install")
class TestJourneyRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = new_test_user(
            cls.env, "route.employee", groups="base.group_user"
        )
        cls.colleague = new_test_user(
            cls.env, "route.colleague", groups="base.group_user"
        )
        cls.portal = new_test_user(cls.env, "route.portal", groups="base.group_portal")
        Incident = cls.env["error.incident"]
        cls.incident = Incident.browse(
            Incident._capture(_payload(user_id=cls.employee.id, occurrence_ref="r-own"))
        )

    def _ask(self, login, occurrence):
        self.authenticate(login, login)
        return self.call_jsonrpc("/error_incident/journey", {"occurrence": occurrence})

    def test_the_owner_follows_it(self):
        answer = self._ask("route.employee", "r-own")
        self.assertEqual(answer["state"], "found")
        self.assertEqual(answer["incident"], self.incident.id)
        self.assertEqual(answer["step"], "recorded")

    def test_someone_else_cannot_tell_it_from_one_not_written_yet(self):
        self.assertEqual(self._ask("route.colleague", "r-own"), {"state": "pending"})
        self.assertEqual(self._ask("route.colleague", "r-none"), {"state": "pending"})

    def test_a_portal_user_is_not_answered(self):
        self.assertEqual(self._ask("route.portal", "r-own"), {"state": "unavailable"})
