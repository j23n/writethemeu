from django.apps import AppConfig


class LettersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'letters'

    def ready(self):
        """Pre-load GeoJSON data on startup for improved performance."""
        try:
            from .services import WahlkreisLocator
            import logging

            logger = logging.getLogger(__name__)
            logger.info("Warming WahlkreisLocator cache on startup...")

            # Initialize to load and cache GeoJSON data
            WahlkreisLocator()

            logger.info("WahlkreisLocator cache warmed successfully")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to warm WahlkreisLocator cache: {e}")
