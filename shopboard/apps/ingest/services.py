"""File ingest pipeline: register upload → parse → bulk-insert lines → status.

Incremental by design (plan §3.1): each file ingests once (sha256 dedup per
shop+kind), deleting a file cascades to its rows. No TRUNCATE anywhere.
"""
from pathlib import Path

from django.db import transaction

from apps.analytics.facts import refresh_facts

from . import parsers
from .models import AdSpend, SalesLine, Shop, UploadedFile

BATCH = 1000


class DuplicateFile(Exception):
    pass


def register_upload(shop: Shop, kind: str, django_file, original_name: str, user=None) -> UploadedFile:
    sha = parsers.file_sha256(django_file)
    if UploadedFile.objects.filter(shop=shop, kind=kind, sha256=sha).exists():
        raise DuplicateFile(f"ไฟล์ {original_name} ถูกนำเข้าแล้ว (เนื้อหาซ้ำ)")
    return UploadedFile.objects.create(
        shop=shop,
        kind=kind,
        file=django_file,
        original_name=original_name,
        sha256=sha,
        uploaded_by=user,
    )


def ingest_file(uf: UploadedFile, refresh: bool = True) -> UploadedFile:
    suffix = Path(uf.original_name).suffix.lower()
    try:
        with uf.file.open("rb") as fh:
            if uf.kind == UploadedFile.Kind.SALES:
                rows = parsers.parse_sales(fh, suffix)
                objs = [
                    SalesLine(file=uf, shop=uf.shop, channel=uf.shop.channel, **r) for r in rows
                ]
                with transaction.atomic():
                    SalesLine.objects.bulk_create(objs, batch_size=BATCH)
                dates = [o.date for o in objs if o.date]
            else:
                rows = parsers.parse_ads(fh, suffix)
                objs = [
                    AdSpend(file=uf, shop=uf.shop, channel=uf.shop.channel, **r) for r in rows
                ]
                with transaction.atomic():
                    AdSpend.objects.bulk_create(objs, batch_size=BATCH)
                dates = [o.date for o in objs]

        uf.row_count = len(objs)
        uf.date_min = min(dates) if dates else None
        uf.date_max = max(dates) if dates else None
        uf.status = UploadedFile.Status.PROCESSED
        uf.error_message = ""
    except Exception as e:
        uf.status = UploadedFile.Status.ERROR
        uf.error_message = str(e)
    uf.save()

    if refresh and uf.status == UploadedFile.Status.PROCESSED:
        refresh_facts()
    return uf


def delete_file(uf: UploadedFile):
    """Deleting a file removes its rows (FK CASCADE) and the stored file."""
    storage, name = uf.file.storage, uf.file.name
    uf.delete()
    if name and storage.exists(name):
        storage.delete(name)
    refresh_facts()
