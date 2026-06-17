def register(rt):
    rt.register(
        "chat://local/message/command/send",
        "python://urichat.handlers:message_send",
        kind="command",
        operation="chat.message.send",
        approval="required",
        side_effects=True,
    )
    rt.register(
        "chat://local/uri/command/execute",
        "python://urichat.handlers:uri_execute",
        kind="command",
        operation="chat.uri.execute",
        approval="required",
        side_effects=True,
    )
