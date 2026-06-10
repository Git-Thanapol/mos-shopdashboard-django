from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.analytics.facts import refresh_facts
from apps.core import channels
from apps.core.decorators import channel_required

from . import importer
from .forms import MasterItemForm, TagForm, TagGroupForm
from .models import MasterItem, ProductTag, Tag, TagGroup

PAGE_SIZE = 100


# ---------------------------------------------------------------- master items
def _master_queryset(request):
    qs = MasterItem.objects.filter(channel=channels.current(request))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(sku__icontains=q) | Q(name__icontains=q))
    cat = request.GET.get("cat", "").strip()
    if cat:
        qs = qs.filter(type=cat)
    return qs.order_by("sku")


def _master_page_context(request):
    qs = _master_queryset(request)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    types = (
        MasterItem.objects.filter(channel=channels.current(request))
        .exclude(type="")
        .values_list("type", flat=True)
        .distinct()
        .order_by("type")
    )
    return {
        "page": page,
        "types": types,
        "q": request.GET.get("q", ""),
        "cat": request.GET.get("cat", ""),
        "total": qs.count(),
    }


@channel_required
def master_items(request):
    ctx = _master_page_context(request)
    ctx["create_form"] = MasterItemForm()
    return render(request, "catalog/master_items.html", ctx)


@channel_required
def master_rows(request):
    return render(request, "catalog/_master_table.html", _master_page_context(request))


@channel_required
@require_POST
def master_create(request):
    form = MasterItemForm(request.POST)
    channel = channels.current(request)
    if form.is_valid():
        if MasterItem.objects.filter(channel=channel, sku=form.cleaned_data["sku"]).exists():
            messages.error(request, f"SKU {form.cleaned_data['sku']} มีอยู่แล้วในช่องทางนี้")
        else:
            item = form.save(commit=False)
            item.channel = channel
            item.updated_by = request.user
            item.save()
            refresh_facts()
            messages.success(request, f"เพิ่มสินค้า {item.sku} แล้ว")
    else:
        messages.error(request, "ข้อมูลไม่ถูกต้อง: " + "; ".join(f"{k}: {v[0]}" for k, v in form.errors.items()))
    return redirect("catalog:master_items")


@channel_required
def master_edit(request, pk):
    item = get_object_or_404(MasterItem, pk=pk, channel=channels.current(request))
    if request.method == "POST":
        form = MasterItemForm(request.POST, instance=item)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            refresh_facts()
            return render(request, "catalog/_master_row.html", {"item": obj})
        return render(request, "catalog/_master_row_edit.html", {"item": item, "form": form})
    return render(request, "catalog/_master_row_edit.html", {"item": item, "form": MasterItemForm(instance=item)})


@channel_required
def master_row(request, pk):
    item = get_object_or_404(MasterItem, pk=pk, channel=channels.current(request))
    return render(request, "catalog/_master_row.html", {"item": item})


@channel_required
@require_POST
def master_delete(request, pk):
    item = get_object_or_404(MasterItem, pk=pk, channel=channels.current(request))
    item.delete()
    refresh_facts()
    return HttpResponse("")  # htmx removes the row


@channel_required
@require_POST
def master_import_xlsx(request):
    file = request.FILES.get("file")
    if not file:
        messages.error(request, "กรุณาเลือกไฟล์")
        return redirect("catalog:master_items")
    try:
        result = importer.import_master_xlsx(file, channels.current(request), request.user)
        refresh_facts()
        messages.success(
            request,
            f"นำเข้าสำเร็จ: เพิ่ม {result['added']} แก้ไข {result['updated']} ข้าม {result['skipped']} รายการ",
        )
    except Exception as e:  # surfaced to the user — no silent failures (UX plan §1.8)
        messages.error(request, f"นำเข้าไม่สำเร็จ: {e}")
    return redirect("catalog:master_items")


@channel_required
@require_POST
def master_import_sheet(request):
    if channels.current(request) != channels.Channel.LIVE:
        messages.error(request, "นำเข้าจาก Google Sheet ได้เฉพาะช่องทางร้านค้าจริงเท่านั้น")
        return redirect("catalog:master_items")
    try:
        result = importer.import_master_google_sheet(request.user)
        refresh_facts()
        messages.success(
            request,
            f"นำเข้าจาก Google Sheet สำเร็จ: เพิ่ม {result['added']} แก้ไข {result['updated']} รายการ",
        )
    except Exception as e:
        messages.error(request, f"นำเข้าไม่สำเร็จ: {e}")
    return redirect("catalog:master_items")


# ---------------------------------------------------------------------- tags
def _tags_context(request, selected_group=None, selected_tag=None):
    groups = TagGroup.objects.annotate(tag_count=Count("tags")).all()
    if selected_group is None:
        gid = request.GET.get("group")
        selected_group = TagGroup.objects.filter(pk=gid).first() if gid else groups.first()
    tags = (
        Tag.objects.filter(group=selected_group).annotate(product_count=Count("product_tags"))
        if selected_group
        else Tag.objects.none()
    )
    if selected_tag is None:
        tid = request.GET.get("tag")
        selected_tag = Tag.objects.filter(pk=tid, group=selected_group).first() if tid else None
    return {
        "groups": groups,
        "selected_group": selected_group,
        "tags": tags,
        "selected_tag": selected_tag,
        "group_form": TagGroupForm(),
        "tag_form": TagForm(),
    }


@channel_required
def tags_page(request):
    ctx = _tags_context(request)
    if ctx["selected_tag"]:
        ctx.update(_assign_context(request, ctx["selected_tag"]))
    return render(request, "catalog/tags.html", ctx)


def _assign_context(request, tag):
    channel = channels.current(request)
    q = request.GET.get("sku_q", "").strip()
    items = MasterItem.objects.filter(channel=channel).order_by("sku")
    if q:
        items = items.filter(Q(sku__icontains=q) | Q(name__icontains=q))
    assigned = set(
        ProductTag.objects.filter(tag=tag, channel=channel).values_list("sku", flat=True)
    )
    return {"assign_items": items[:300], "assigned_skus": assigned, "sku_q": q}


@channel_required
@require_POST
def group_create(request):
    form = TagGroupForm(request.POST)
    if form.is_valid():
        group = form.save()
        messages.success(request, f"เพิ่มกลุ่ม {group.name} แล้ว")
        return redirect(f"/settings/tags/?group={group.pk}")
    messages.error(
        request,
        "เพิ่มกลุ่มไม่สำเร็จ: " + "; ".join(e for errs in form.errors.values() for e in errs),
    )
    return redirect("catalog:tags")


@channel_required
@require_POST
def group_update(request, pk):
    group = get_object_or_404(TagGroup, pk=pk)
    name = request.POST.get("name", "").strip()
    if name:
        group.name = name
    if "color" in request.POST:
        group.color = request.POST["color"]
    group.is_visible = request.POST.get("is_visible", "on") == "on"
    group.save()
    return redirect(f"{request.POST.get('next', '/settings/tags/')}?group={group.pk}")


@channel_required
@require_POST
def group_delete(request, pk):
    get_object_or_404(TagGroup, pk=pk).delete()
    messages.success(request, "ลบกลุ่มแท็กแล้ว")
    return redirect("catalog:tags")


@channel_required
@require_POST
def tag_create(request, group_pk):
    group = get_object_or_404(TagGroup, pk=group_pk)
    form = TagForm(request.POST)
    if form.is_valid():
        tag = form.save(commit=False)
        tag.group = group
        if not tag.color:
            tag.color = group.color
        try:
            tag.save()
        except Exception:
            messages.error(request, "ชื่อแท็กซ้ำในกลุ่มนี้")
    return redirect(f"/settings/tags/?group={group.pk}")


@channel_required
@require_POST
def tag_update(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    name = request.POST.get("name", "").strip()
    if name:
        tag.name = name
    if request.POST.get("color"):
        tag.color = request.POST["color"]
    tag.save()
    return redirect(f"/settings/tags/?group={tag.group_id}&tag={tag.pk}")


@channel_required
@require_POST
def tag_delete(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    gid = tag.group_id
    tag.delete()
    messages.success(request, "ลบแท็กแล้ว")
    return redirect(f"/settings/tags/?group={gid}")


@channel_required
@require_POST
def tag_toggle_sku(request, pk):
    """Checkbox toggle: assign/unassign one SKU to a tag (HTMX)."""
    tag = get_object_or_404(Tag, pk=pk)
    channel = channels.current(request)
    sku = request.POST.get("sku", "").strip()
    if not sku:
        return HttpResponse(status=400)
    if request.POST.get("checked") == "true":
        ProductTag.objects.get_or_create(tag=tag, channel=channel, sku=sku)
    else:
        ProductTag.objects.filter(tag=tag, channel=channel, sku=sku).delete()
    count = ProductTag.objects.filter(tag=tag, channel=channel).count()
    return HttpResponse(f"ใช้กับสินค้า {count} รายการ")
