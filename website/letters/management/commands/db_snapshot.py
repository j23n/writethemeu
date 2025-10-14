# ABOUTME: Management command to save and restore SQLite database snapshots.
# ABOUTME: Enables quick database state preservation for testing and development.

import shutil
import pathlib
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from letters.models import Parliament, Constituency, Representative, Committee, TopicArea


class Command(BaseCommand):
    help = "Save or restore SQLite database snapshots to/from fixtures directory"

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(
            dest="subcommand", help="Available subcommands", title="subcommands"
        )

        # Save subcommand
        save_parser = subparsers.add_parser(
            "save", help="Create a snapshot of the current database state"
        )
        save_parser.add_argument(
            "description",
            type=str,
            help='Description of the snapshot (e.g., "with-representatives", "after-sync")',
        )

        # Restore subcommand
        restore_parser = subparsers.add_parser(
            "restore", help="Restore database from a snapshot"
        )
        restore_parser.add_argument(
            "snapshot_file",
            type=str,
            help='Snapshot filename (e.g., "db_snapshot_20241014_123456_with-representatives.sqlite3")',
        )

        # List subcommand
        subparsers.add_parser("list", help="List available snapshots")

    def handle(self, *args, **options):
        subcommand = options.get("subcommand")

        if not subcommand:
            self.print_help("manage.py", "db_snapshot")
            return

        if subcommand == "save":
            self.handle_save(options)
        elif subcommand == "restore":
            self.handle_restore(options)
        elif subcommand == "list":
            self.handle_list(options)
        else:
            raise CommandError(f"Unknown subcommand: {subcommand}")

    def handle_save(self, options):
        """Create a timestamped snapshot of the current database"""
        description = options["description"]

        # Create filename with timestamp and description
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize description for filename
        safe_description = "".join(c if c.isalnum() or c == "-" else "_" for c in description)
        snapshot_filename = f"db_snapshot_{timestamp}_{safe_description}.sqlite3"

        # Determine source database path
        db_path = pathlib.Path(settings.DATABASES["default"]["NAME"])
        if not db_path.exists():
            raise CommandError(f"Database file not found: {db_path}")

        # Create fixtures directory if it doesn't exist
        fixtures_dir = settings.BASE_DIR.parent / "fixtures"
        fixtures_dir.mkdir(exist_ok=True)

        snapshot_path = fixtures_dir / snapshot_filename

        self.stdout.write(self.style.SUCCESS("📸 Creating database snapshot..."))
        self.stdout.write(f"   Source: {db_path}")
        self.stdout.write(f"   Destination: {snapshot_path}")
        self.stdout.write(f"   Description: {description}")

        # Copy the SQLite database file
        shutil.copy2(db_path, snapshot_path)

        self.stdout.write(self.style.SUCCESS("\n✅ Snapshot created successfully!"))
        self.stdout.write(f"   File: {snapshot_filename}")
        self.stdout.write(f"   Size: {snapshot_path.stat().st_size / (1024 * 1024):.2f} MB")

        # Show current database stats
        self.stdout.write(self.style.SUCCESS("\n📊 Snapshot contains:"))
        self.stdout.write(f"   🏛️  Parliaments: {Parliament.objects.count()}")
        self.stdout.write(f"   📍 Constituencies: {Constituency.objects.count()}")
        self.stdout.write(f"   👤 Representatives: {Representative.objects.count()}")
        self.stdout.write(f"   🏢 Committees: {Committee.objects.count()}")
        self.stdout.write(f"   🏷️  Topic Areas: {TopicArea.objects.count()}")

    def handle_restore(self, options):
        """Restore database from a snapshot"""
        snapshot_file = options["snapshot_file"]

        # Locate snapshot file
        fixtures_dir = settings.BASE_DIR.parent / "fixtures"
        snapshot_path = fixtures_dir / snapshot_file

        if not snapshot_path.exists():
            raise CommandError(f"Snapshot file not found: {snapshot_path}")

        # Determine target database path
        db_path = pathlib.Path(settings.DATABASES["default"]["NAME"])

        self.stdout.write(self.style.WARNING("⚠️  Restoring database snapshot..."))
        self.stdout.write(f"   Source: {snapshot_path}")
        self.stdout.write(f"   Destination: {db_path}")
        self.stdout.write(f"   Size: {snapshot_path.stat().st_size / (1024 * 1024):.2f} MB")

        # Confirm overwrite
        self.stdout.write(
            self.style.WARNING(
                "\n⚠️  This will OVERWRITE your current database!"
            )
        )
        confirm = input("Type 'restore' to confirm: ")

        if confirm != "restore":
            self.stdout.write(self.style.ERROR("Restore cancelled."))
            return

        # Backup current database before overwriting
        if db_path.exists():
            backup_path = db_path.parent / f"{db_path.stem}_backup_before_restore{db_path.suffix}"
            self.stdout.write(f"\n📦 Backing up current database to: {backup_path.name}")
            shutil.copy2(db_path, backup_path)

        # Restore the snapshot
        shutil.copy2(snapshot_path, db_path)

        self.stdout.write(self.style.SUCCESS("\n✅ Database restored successfully!"))

        # Show restored database stats
        self.stdout.write(self.style.SUCCESS("\n📊 Restored database contains:"))
        self.stdout.write(f"   🏛️  Parliaments: {Parliament.objects.count()}")
        self.stdout.write(f"   📍 Constituencies: {Constituency.objects.count()}")
        self.stdout.write(f"   👤 Representatives: {Representative.objects.count()}")
        self.stdout.write(f"   🏢 Committees: {Committee.objects.count()}")
        self.stdout.write(f"   🏷️  Topic Areas: {TopicArea.objects.count()}")

    def handle_list(self, options):
        """List available snapshots"""
        fixtures_dir = settings.BASE_DIR.parent / "fixtures"

        if not fixtures_dir.exists():
            self.stdout.write(self.style.WARNING("No fixtures directory found."))
            return

        # Find all snapshot files
        snapshots = sorted(fixtures_dir.glob("db_snapshot_*.sqlite3"), reverse=True)

        if not snapshots:
            self.stdout.write(self.style.WARNING("No snapshots found."))
            return

        self.stdout.write(self.style.SUCCESS(f"\n📁 Available snapshots ({len(snapshots)}):"))
        self.stdout.write("")

        for snapshot in snapshots:
            size_mb = snapshot.stat().st_size / (1024 * 1024)
            mtime = datetime.fromtimestamp(snapshot.stat().st_mtime)
            self.stdout.write(f"  • {snapshot.name}")
            self.stdout.write(f"    Size: {size_mb:.2f} MB, Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            self.stdout.write("")
