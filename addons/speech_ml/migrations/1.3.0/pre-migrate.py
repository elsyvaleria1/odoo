def migrate(cr, version):
    cr.execute(
        "UPDATE ir_attachment_reading SET read_by = 'ml_transcription'"
        " WHERE read_by = 'ai_transcription'"
    )
