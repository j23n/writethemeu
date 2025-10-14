# ABOUTME: Management command to check translation completeness and report coverage.
# ABOUTME: Analyzes .po files to find untranslated strings and calculate coverage percentage.

from django.core.management.base import BaseCommand
from django.conf import settings
import pathlib


class Command(BaseCommand):
    help = "Check translation completeness for all configured languages"

    def add_arguments(self, parser):
        parser.add_argument(
            '--language',
            type=str,
            help='Check specific language (e.g., "de" or "en")',
        )

    def handle(self, *args, **options):
        locale_paths = settings.LOCALE_PATHS
        languages = settings.LANGUAGES

        target_language = options.get('language')

        if target_language:
            languages_to_check = [(target_language, None)]
        else:
            languages_to_check = languages

        for lang_code, lang_name in languages_to_check:
            self.check_language(locale_paths[0], lang_code, lang_name)

    def check_language(self, locale_path, lang_code, lang_name):
        """Check translation completeness for a single language."""
        po_file = pathlib.Path(locale_path) / lang_code / 'LC_MESSAGES' / 'django.po'

        if not po_file.exists():
            self.stdout.write(self.style.ERROR(
                f"\n{lang_code}: No .po file found at {po_file}"
            ))
            return

        total = 0
        translated = 0
        untranslated = []

        with open(po_file, 'r', encoding='utf-8') as f:
            current_msgid = None
            for line in f:
                line = line.strip()
                if line.startswith('msgid "') and not line.startswith('msgid ""'):
                    current_msgid = line[7:-1]  # Extract string between quotes
                    total += 1
                elif line.startswith('msgstr "'):
                    msgstr = line[8:-1]
                    if msgstr:  # Non-empty translation
                        translated += 1
                    elif current_msgid:
                        untranslated.append(current_msgid)
                    current_msgid = None

        if total == 0:
            self.stdout.write(self.style.WARNING(
                f"\n{lang_code}: No translatable strings found"
            ))
            return

        coverage = (translated / total) * 100
        display_name = lang_name if lang_name else lang_code

        self.stdout.write(self.style.SUCCESS(
            f"\n{display_name} ({lang_code}):"
        ))
        self.stdout.write(f"   Total strings: {total}")
        self.stdout.write(f"   Translated: {translated}")
        self.stdout.write(f"   Untranslated: {len(untranslated)}")
        self.stdout.write(f"   Coverage: {coverage:.1f}%")

        if untranslated:
            self.stdout.write(self.style.WARNING(
                f"\nMissing translations ({len(untranslated)}):"
            ))
            for msgid in untranslated[:10]:  # Show first 10
                self.stdout.write(f"   - {msgid}")
            if len(untranslated) > 10:
                self.stdout.write(f"   ... and {len(untranslated) - 10} more")
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nAll strings translated!"
            ))
