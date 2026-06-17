def register(rt):
    rt.register(
        "webrtc://local/session/{session}/command/start",
        "python://uriwebrtc.handlers:session_start",
        kind="command",
        operation="webrtc.session.start",
        approval="required",
        side_effects=True,
    )
    rt.register(
        "webrtc://local/session/{session}/data/command/send",
        "python://uriwebrtc.handlers:data_send",
        kind="command",
        operation="webrtc.data.send",
        approval="required",
        side_effects=True,
    )
