def register(rt):
    rt.register(
        "message://local/alert/command/send",
        "python://urimessage.handlers:alert_send",
        kind="command",
        operation="message.alert.send",
        approval="required",
        side_effects=True,
    )
