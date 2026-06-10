from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core import channels
from apps.core.decorators import channel_required

from . import services
from .models import Shop, UploadedFile


def _shops(request):
    return Shop.objects.filter(channel=channels.current(request), is_active=True)


@channel_required
def file_manager(request):
    shops = _shops(request)
    shop_id = request.GET.get("shop")
    shop = shops.filter(pk=shop_id).first() if shop_id else shops.first()
    files = shop.files.all() if shop else UploadedFile.objects.none()
    return render(
        request,
        "ingest/file_manager.html",
        {"shops": shops, "shop": shop, "files": files},
    )


@channel_required
def import_history(request):
    files = (
        UploadedFile.objects.filter(shop__channel=channels.current(request))
        .select_related("shop", "uploaded_by")[:300]
    )
    return render(request, "ingest/import_history.html", {"files": files})


@channel_required
@require_POST
def shop_create(request):
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "กรุณากรอกชื่อร้าน")
        return redirect("ingest:file_manager")
    shop, created = Shop.objects.get_or_create(channel=channels.current(request), name=name)
    if created:
        messages.success(request, f"เพิ่มร้าน {name} แล้ว")
    else:
        messages.warning(request, f"ร้าน {name} มีอยู่แล้ว")
    return redirect(f"/data/files/?shop={shop.pk}")


@channel_required
@require_POST
def shop_delete(request, pk):
    shop = get_object_or_404(Shop, pk=pk, channel=channels.current(request))
    n_files = shop.files.count()
    shop.delete()
    messages.success(request, f"ลบร้านและไฟล์ {n_files} ไฟล์แล้ว")
    return redirect("ingest:file_manager")


@channel_required
@require_POST
def upload(request, shop_pk, kind):
    """Dropzone target — ingests immediately, returns the file-row partial (HTMX)."""
    shop = get_object_or_404(Shop, pk=shop_pk, channel=channels.current(request))
    kind = kind.upper()
    if kind not in UploadedFile.Kind.values:
        return HttpResponse(status=400)

    results = []
    for f in request.FILES.getlist("files"):
        try:
            uf = services.register_upload(shop, kind, f, f.name, request.user)
            uf = services.ingest_file(uf)
            results.append(uf)
        except services.DuplicateFile as e:
            messages.warning(request, str(e))
    if request.headers.get("HX-Request"):
        return render(request, "ingest/_file_rows.html", {"files": results, "shop": shop})
    return redirect(f"/data/files/?shop={shop.pk}")


@channel_required
@require_POST
def file_delete(request, pk):
    uf = get_object_or_404(UploadedFile, pk=pk, shop__channel=channels.current(request))
    services.delete_file(uf)
    return HttpResponse("")


@channel_required
def file_detail(request, pk):
    uf = get_object_or_404(UploadedFile, pk=pk, shop__channel=channels.current(request))
    return render(request, "ingest/_file_detail.html", {"f": uf})
