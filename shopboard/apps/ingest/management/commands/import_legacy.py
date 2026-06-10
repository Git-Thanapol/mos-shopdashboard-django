"""One-off migration of the legacy local_data tree (plan §8).

- Shop folders under LEGACY_DATA_DIR (default /legacy_data) become LIVE shops;
  the legacy root sales/ and ads/ folders are skipped (same as the old app).
- Every sales/ads file goes through the normal ingest pipeline so history gets
  full computed columns + file provenance.
- master_item.xlsx (if present) is imported into the LIVE master.
"""
import os
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from apps.analytics.facts import refresh_facts
from apps.catalog import importer as master_importer
from apps.core.channels import Channel
from apps.ingest import services
from apps.ingest.models import AdSpend, SalesLine, Shop, UploadedFile

SUPPORTED = {".csv", ".xlsx", ".xls"}


class Command(BaseCommand):
    help = "Import the legacy shop_dashboard local_data tree into the LIVE channel."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", default=os.environ.get("LEGACY_DATA_DIR", "/legacy_data"))
        parser.add_argument("--skip-master", action="store_true")

    def handle(self, *args, **options):
        root = Path(options["data_dir"])
        if not root.exists():
            self.stderr.write(f"data dir not found: {root}")
            return

        shop_dirs = [d for d in sorted(root.iterdir()) if d.is_dir() and d.name not in ("sales", "ads")]
        self.stdout.write(f"shops: {[d.name for d in shop_dirs]}")

        total = {"files": 0, "dup": 0, "err": 0}
        for shop_dir in shop_dirs:
            shop, _ = Shop.objects.get_or_create(channel=Channel.LIVE, name=shop_dir.name)
            for kind, sub in ((UploadedFile.Kind.SALES, "sales"), (UploadedFile.Kind.ADS, "ads")):
                folder = shop_dir / sub
                if not folder.exists():
                    continue
                for path in sorted(folder.iterdir()):
                    if path.suffix.lower() not in SUPPORTED:
                        continue
                    with path.open("rb") as fh:
                        try:
                            uf = services.register_upload(shop, kind, File(fh, name=path.name), path.name)
                        except services.DuplicateFile:
                            total["dup"] += 1
                            continue
                    uf = services.ingest_file(uf, refresh=False)
                    total["files"] += 1
                    if uf.status == UploadedFile.Status.ERROR:
                        total["err"] += 1
                        self.stderr.write(f"  ERROR {shop.name}/{sub}/{path.name}: {uf.error_message}")
                    else:
                        self.stdout.write(f"  ok {shop.name}/{sub}/{path.name}: {uf.row_count} rows")

        if not options["skip_master"]:
            master_path = root / "master_item.xlsx"
            if master_path.exists():
                with master_path.open("rb") as fh:
                    res = master_importer.import_master_xlsx(fh, Channel.LIVE)
                self.stdout.write(f"master: {res}")

        refresh_facts()

        self.stdout.write(self.style.SUCCESS(
            f"done. files={total['files']} dup={total['dup']} err={total['err']} | "
            f"sales_lines={SalesLine.objects.count()} ad_rows={AdSpend.objects.count()}"
        ))
