from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core import channels
from apps.core.decorators import channel_required


@login_required
def channel_select(request):
    return render(request, "analytics/channel_select.html", {"channels": channels.Channel})


@login_required
@require_POST
def channel_activate(request):
    value = request.POST.get("channel", "")
    if value in channels.Channel.values:
        channels.activate(request, value)
        return redirect("analytics:home")
    return redirect("analytics:channel_select")


@channel_required
def home(request):
    # Placeholder shell — replaced by the real dashboard in phase 5
    return render(request, "analytics/home.html")
