from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from . import channels


def channel_required(view_func):
    """Every page except login/channel-select needs an active TEST/LIVE channel."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if channels.current(request) is None:
            return redirect("analytics:channel_select")
        return view_func(request, *args, **kwargs)

    return wrapper
