from markupsafe import Markup

from odoo import models
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _timesheet_create_task_prepare_values(self, project):
        res = super()._timesheet_create_task_prepare_values(project)
        if not (self.calendar_event_id and self.calendar_booking_ids):
            return res
        user_ids = tag_ids = False
        if self.calendar_booking_ids.appointment_type_id.schedule_based_on == "users":
            user_ids = self.calendar_booking_ids.staff_user_id.ids
        else:
            resource_names = self.calendar_event_id.resource_ids.mapped("name")
            domain = Domain.OR(
                Domain("name", "=ilike", resource_name)
                for resource_name in resource_names
            )
            existing_tags = self.env["project.tags"].search(domain)
            existing_tags_names = {tag.name.lower() for tag in existing_tags}
            new_tags_names = {
                resource_name
                for resource_name in resource_names
                if resource_name.lower() not in existing_tags_names
            }
            tag_ids = [Command.set(existing_tags.ids)] + [
                Command.create({"name": name}) for name in new_tags_names
            ]
            _debug.logic(
                "resource_tags",
                line=self,
                resources=len(resource_names),
                existing=existing_tags,
                created=len(new_tags_names),
            )

        responses = self.calendar_booking_ids.appointment_response_ids
        answers = self.calendar_booking_ids.appointment_answer_input_ids
        questions = (
            responses.with_context(active_test=False).predefined_question_ids
            | answers.question_id
        )
        if not responses:
            questions = self.calendar_booking_ids.appointment_type_id.question_ids
        formatted_answers = []
        answers_by_question = answers.grouped("question_id")
        for question in questions:
            answer_value = "/"
            if question_answers := answers_by_question.get(question):
                answer_value = ", ".join(
                    answer.value_char_box
                    or answer.value_text_box
                    or answer.suggested_answer_id.value
                    or "/"
                    for answer in question_answers
                )
            formatted_answers.append(
                Markup("<dt><h3>%s</h3></dt><dd>%s</dd><br/>")
                % (question.title, answer_value)
            )
        description = Markup("<dl>%s</dl>") % Markup("").join(formatted_answers)
        _debug.pipeline(
            "task_values_from_booking",
            line=self,
            event=self.calendar_event_id,
            questions=questions,
            answered=len(answers),
            from_type_defaults=not responses,
        )

        res.update(
            {
                "partner_id": self.order_id.partner_shipping_id.id,
                "user_ids": user_ids,
                "tag_ids": tag_ids,
                "description": description,
                "calendar_event_id": self.calendar_event_id.id,
                "date_start": self.calendar_event_id.start,
                "date_end": self.calendar_event_id.stop,
                "planned_hours": self.calendar_event_id.duration,
            }
        )
        return res

    def _timesheet_create_task(self, project):
        task = super()._timesheet_create_task(project)
        if not (self.calendar_event_id and self.calendar_booking_ids):
            return task
        if self.calendar_event_id.attendee_ids:
            partner_ids = self.calendar_event_id.attendee_ids.mapped("partner_id")
            _debug.lifecycle(
                "attendees_subscribed", task=task, event=self.calendar_event_id
            )
            task.message_subscribe(partner_ids.ids)
        return task
