from collections import defaultdict

from zeep import Client
from zeep.exceptions import Fault
from zeep.wsse.username import UsernameToken

from odoo import models
from odoo.libs.debug_log import DebugLog

MONSTER_WSDL_URI = (
    "https://schemas.monster.com/Current/WSDL/MonsterBusinessGateway.wsdl"
)

_debug = DebugLog(__name__)


class HrRecruitmentPlatform(models.Model):
    _inherit = "hr.recruitment.platform"

    def _post_api_call(self, data) -> dict:
        if (
            self.id
            != self.env.ref(
                "hr_recruitment_integration_monster.hr_recruitment_platform_monster"
            ).id
        ):
            return super()._post_api_call(data)

        if not (
            username := self.env.company.sudo().hr_recruitment_monster_username
        ) or not (password := self.env.company.sudo().hr_recruitment_monster_password):
            _debug.logic(
                "monster_post_refused",
                reason="no_credentials_on_the_company",
                platform=self,
                company=self.env.company,
            )
            return {
                "status": "failure",
                "status_message": self.env._(
                    "Monster.com credentials are not set. "
                    "Please set them in the company settings or ask your administrator."
                ),
            }
        monster_soap_client = Client(
            MONSTER_WSDL_URI,
            wsse=UsernameToken(
                username=username,
                password=password,
            ),
        )

        for _i in range(3):
            try:
                _debug.lifecycle(
                    "monster_update_jobs",
                    platform=self,
                    attempt=_i + 1,
                    job_action=data.get("jobAction"),
                    job_ref_code=data.get("jobRefCode"),
                )
                monster_response = monster_soap_client.service.UpdateJobs(Job=data)
            except TimeoutError:
                _debug.logic(
                    "monster_attempt_timed_out",
                    platform=self,
                    attempt=_i + 1,
                )
                continue
            except KeyError, ValueError:
                _debug.logic(
                    "monster_post_refused",
                    reason="response_shape_changed",
                    platform=self,
                )
                return {
                    "status": "failure",
                    "status_message": self.env._(
                        "Critical error: Monster.com service has changed. "
                        "Please contact customer support."
                    ),
                }
            except Fault:
                _debug.logic(
                    "monster_post_refused",
                    reason="soap_fault_credentials_rejected",
                    platform=self,
                )
                return {
                    "status": "failure",
                    "status_message": self.env._(
                        "Authentication error: Monster.com credentials are invalid."
                    ),
                }
            else:
                break
        else:
            _debug.logic(
                "monster_post_refused",
                reason="three_attempts_timed_out",
                platform=self,
            )
            return {
                "status": "failure",
                "status_message": self.env._(
                    "Service not available: Monster.com service is not available. "
                    "Please try again later."
                ),
            }

        if data["jobAction"] == "delete":
            status = "deleted"
        else:
            status = "success"

        message_dict = defaultdict(list)
        for job_response in monster_response["body"]["JobResponse"]:
            if (
                job_response["Status"]["ReturnCode"]["_value_1"] != "0"
                and status != "expired"
            ):
                status = "failure"

            for log_dict in job_response["Status"]["Descriptions"]["Description"]:
                message_dict[log_dict["descriptionType"]].append(log_dict["_value_1"])
                if "no active Job with JobRefCode" in log_dict["_value_1"]:
                    status = "expired"

        _debug.pipeline(
            "monster_response_read",
            platform=self,
            job_action=data["jobAction"],
            responses=len(monster_response["body"]["JobResponse"]),
            status=status,
            description_levels=len(message_dict),
        )
        message = "\n".join(
            [
                f"{error_level}: {message}"
                for error_level, message_list in message_dict.items()
                for message in message_list
            ]
        )

        return {
            "status": status,
            "status_message": message,
        }
