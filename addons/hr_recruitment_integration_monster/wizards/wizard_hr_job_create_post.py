from datetime import datetime

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.tools import consteq

_debug = DebugLog(__name__)


class WizardHrJobCreatePost(models.TransientModel):
    _inherit = "wizard.hr.job.create.post"

    def _prepare_monster_data(self):
        def convert_hours_to_monster_id():
            if self.job_id.schedule_id.schedule_type == "flexible":
                return 6
            hours = self.job_id.schedule_id.hours_per_week
            if hours < 10:
                return 1
            if hours < 20:
                return 2
            if hours < 40:
                return 3
            if hours == 40:
                return 4
            return 5

        def convert_status_to_monster_id():
            # pay per diem
            if self.job_id.payment_interval == "daily":
                return 3
            if self.job_id.schedule_id.is_fulltime:
                return 2
            return 1

        self.check_singleton()
        data = {
            "jobAction": "addOrUpdate",
            "JobInformation": {
                "JobTitle": self.job_id.name,
                "PhysicalAddress": {
                    "StreetAddress": self.job_id.address_id.street,
                    "City": self.job_id.address_id.city,
                    "State": self.job_id.address_id.state_id.name,
                    "CountryCode": self.job_id.address_id.country_code,
                    "PostalCode": self.job_id.address_id.zip,
                },
                "JobBody": self.post_html,
                "Contact": {
                    "Name": self.job_id.user_id.name,
                    "CompanyName": self.job_id.company_id.name,
                    "Address": {
                        "StreetAddress": self.job_id.company_id.street,
                        "City": self.job_id.company_id.city,
                        "State": self.job_id.company_id.state_id.name,
                        "CountryCode": self.job_id.company_id.country_code,
                        "PostalCode": self.job_id.company_id.zip,
                    },
                },
            },
            "JobPostings": {
                "JobPosting": {  # n.b. a list of job postings dict is allowed
                    "BoardName": {
                        # monsterId 1 is monster.com and 178 is jobsearch.demo.monster.com
                        "monsterId": 1
                        if not consteq(
                            str(
                                self.job_id.company_id.sudo().hr_recruitment_monster_username
                            ),
                            "xrtpjobsx01",
                        )
                        else 178
                    },
                    "Location": {
                        "City": self.job_id.address_id.city,
                        "State": self.job_id.address_id.state_id.name,
                        "CountryCode": self.job_id.address_id.country_code,
                        "PostalCode": self.job_id.address_id.zip,
                    },
                },
            },
        }

        if self.api_data:
            data["jobRefCode"] = self.api_data["jobRefCode"]
        else:
            last_post = self.env["hr.job.post"].search(
                domain=[
                    (
                        "platform_id",
                        "=",
                        self.env.ref(
                            "hr_recruitment_integration_monster.hr_recruitment_platform_monster"
                        ).id,
                    ),
                    ("job_id", "=", self.job_id.id),
                    ("api_data", "!=", False),
                ],
                order="id desc",
                limit=1,
            )
            if last_post:
                occurrence_str = str(
                    int(last_post.api_data["jobRefCode"].rsplit("_", 1)[1]) + 1
                )
            else:
                occurrence_str = "1"

            _debug.logic(
                "monster_job_ref_code",
                wizard=self,
                job=self.job_id,
                # the occurrence counter is read off the LAST post's ref code
                # by splitting on the final underscore, so a hand-edited or
                # differently shaped code restarts the sequence at 1
                by="incremented_from_last_post" if last_post else "first_post",
                previous=last_post.api_data["jobRefCode"] if last_post else False,
                occurrence=occurrence_str,
            )
            data["jobRefCode"] = "_".join(
                [str(self.job_id.id), datetime.now().strftime("%Y%m%d"), occurrence_str]
            )

        if self.job_id.industry_id and (
            industry_id := self.job_id.industry_id.monster_id
        ):
            # not taking multiple industries into account because only one will be selected by monster
            data["JobPostings"]["JobPosting"]["Industries"] = {
                "Industry": [
                    {
                        "IndustryName": {
                            "monsterId": industry_id,
                        },
                    },
                ],
            }

        if self.job_id.schedule_id:
            data["JobInformation"]["WorkHours"] = {
                "monsterId": convert_hours_to_monster_id(),
            }
            data["JobInformation"]["JobStatus"] = {
                "monsterId": convert_status_to_monster_id(),
            }

        if self.job_id.contract_type_id and self.job_id.contract_type_id.monster_id:
            data["JobInformation"]["JobType"] = {
                "monsterId": self.job_id.contract_type_id.monster_id,
            }

        if (
            self.job_id.salary_min
            and self.job_id.salary_max
            and self.job_id.payment_interval
            and self.job_id.currency_id
        ):
            monster_currency_id = (
                False
                if not self.job_id.currency_id
                else self.job_id.currency_id.monster_id
            )
            monster_time_unit = {
                "hourly": 2,
                "daily": 6,
                "weekly": 3,
                "biweekly": 5,
                "monthly": 4,
                "yearly": 1,
            }.get(self.job_id.payment_interval)
            if monster_currency_id and monster_time_unit:
                data["JobInformation"]["Salary"] = {
                    "Currency": {
                        "monsterId": monster_currency_id,
                    },
                    "SalaryMin": self.job_id.salary_min,
                    "SalaryMax": self.job_id.salary_max,
                    "CompensationType": {
                        "monsterId": monster_time_unit,
                    },
                }

        if self.apply_method == "email":
            data["JobInformation"]["Contact"]["E-mail"] = self.job_apply_mail

        _debug.pipeline(
            "monster_payload_built",
            wizard=self,
            job=self.job_id,
            job_ref_code=data["jobRefCode"],
            # each of these blocks is added only when its source is set, and
            # a posting missing one is accepted by Monster without comment
            has_industry=bool(data["JobPostings"]["JobPosting"].get("Industries")),
            has_work_hours=bool(data["JobInformation"].get("WorkHours")),
            has_job_type=bool(data["JobInformation"].get("JobType")),
            has_salary=bool(data["JobInformation"].get("Salary")),
            apply_method=self.apply_method,
        )
        return data

    def _post_job(self, responses=None) -> dict:
        self.check_singleton()
        monster = self.env.ref(
            "hr_recruitment_integration_monster.hr_recruitment_platform_monster"
        )
        if monster in self.platform_ids:
            if not responses:
                responses = {}
            data = self._prepare_monster_data()
            responses[monster.id] = monster._post_api_call(data)
            _debug.lifecycle(
                "monster_job_posted",
                wizard=self,
                job=self.job_id,
                job_ref_code=data["jobRefCode"],
                status=responses[monster.id]["status"],
            )
            responses[monster.id]["data"] = {"jobRefCode": data["jobRefCode"]}
        return super()._post_job(responses)
