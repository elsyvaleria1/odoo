from odoo.tests.common import BaseCase

from odoo.addons.calendar_google.utils.calendar_google import GoogleEvent


class TestGoogleEvent(BaseCase):
    def test_google_event_readonly(self):
        event = GoogleEvent()
        with self.assertRaises(TypeError):
            event._events["foo"] = "bar"
        with self.assertRaises(AttributeError):
            event._events.update({"foo": "bar"})
        with self.assertRaises(TypeError):
            dict.update(event._events, {"foo": "bar"})

    def test_duplicate_ids_keep_first_position_and_last_payload(self):
        first = {"id": "a", "summary": "first"}
        last = {"id": "a", "summary": "last"}
        other = {"id": "b"}
        event = GoogleEvent([first, other, last])
        self.assertEqual(list(event._events), ["a", "b"])
        self.assertIs(event._events["a"], last)
        self.assertIs(event._events["b"], other)

    def test_payloads_are_shared_but_the_index_is_readonly(self):
        payload = {"id": "a", "summary": "first"}
        original = GoogleEvent([payload])
        copied = GoogleEvent([original])
        self.assertIs(copied._events["a"], payload)
        payload["summary"] = "updated"
        self.assertEqual(copied.summary, "updated")
        with self.assertRaises(TypeError):
            copied._events["a"] = {}

    def test_missing_id_keeps_the_last_payload(self):
        last = {"summary": "last"}
        event = GoogleEvent([{}, last])
        self.assertEqual(list(event._events), [None])
        self.assertIs(event._events[None], last)

    def test_invalid_inputs_keep_provider_specific_errors(self):
        with self.assertRaisesRegex(
            ValueError, "Only GoogleEvent or iterable of dict are supported"
        ):
            GoogleEvent([object()])
        for event in (GoogleEvent(), GoogleEvent([{"id": "a"}, {"id": "b"}])):
            with (
                self.subTest(event=event),
                self.assertRaisesRegex(ValueError, "Expected singleton"),
            ):
                GoogleEvent([event])
        with self.assertRaises(TypeError):
            GoogleEvent([{"id": []}])
