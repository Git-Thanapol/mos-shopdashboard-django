from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404
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


def superuser_required(view_func):
    """404, not 403 — non-superusers shouldn't learn the page exists."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return view_func(request, *args, **kwargs)

    return wrapper
