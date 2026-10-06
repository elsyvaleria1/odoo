HEALTH_CHECK_ENDPOINT = "/2010-04-01/Accounts.json"
SERVICE_XMLID = "integration_twilio.service_twilio"


def _rehome_twilio_service(cr) -> None:
    # `integration` seeded the service until this module took it over; its row
    # stays in every database that had `integration`, and the seed loaded
    # here would collide with its unique code
    cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'integration_twilio'
         WHERE module = 'integration' AND name = 'service_twilio'
           AND NOT EXISTS (SELECT 1 FROM ir_model_data
                            WHERE module = 'integration_twilio' AND name = 'service_twilio')
        """
    )
    cr.execute(
        """
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        SELECT 'integration_twilio', 'service_twilio', 'integration.service', s.id, TRUE
          FROM integration_service s
         WHERE s.code = 'twilio'
           AND NOT EXISTS (SELECT 1 FROM ir_model_data
                            WHERE module = 'integration_twilio' AND name = 'service_twilio')
         LIMIT 1
        """
    )


def _update_twilio_service(env) -> None:
    # the seed is noupdate: a row inherited from `integration` keeps its old
    # name and no probe until told
    service = env.ref(SERVICE_XMLID, raise_if_not_found=False)
    if not service:
        return
    if service.name == "Twilio SMS":
        service.name = "Twilio"
    if not service.health_check_endpoint:
        service.write(
            {
                "health_check_enabled": True,
                "health_check_endpoint": HEALTH_CHECK_ENDPOINT,
            }
        )


def pre_init_hook(env) -> None:
    _rehome_twilio_service(env.cr)
    _update_twilio_service(env)


def uninstall_hook(env) -> None:
    # the vault credentials and the receivers this module made go with it: a
    # reinstall would otherwise find its credential names taken
    configs = (
        env["integration.twilio.config"].with_context(active_test=False).search([])
    )
    credentials = configs.credential_id
    configs.write({"credential_id": False})
    credentials.unlink()
    env["integration.receiver"].with_context(active_test=False).search(
        [("res_purpose", "in", ["twilio_sms_status", "twilio_sms_inbound"])]
    ).unlink()
