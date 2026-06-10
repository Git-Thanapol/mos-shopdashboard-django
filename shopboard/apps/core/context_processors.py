from . import channels


def channel(request):
    value = channels.current(request)
    return {
        "active_channel": value,
        "is_test_channel": value == channels.Channel.TEST,
        "channel_label": channels.Channel(value).label if value else "",
    }
