# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI
from .geocoding import AddressGeocoder, WahlkreisLocator
from .constituency import (
    LocationContext,
    ConstituencySuggestionService,
)
from .identity import IdentityVerificationService
from .topics import TopicSuggestionService, CommitteeTopicMappingService

from .representative_sync import RepresentativeSyncService

__all__ = [
    'AbgeordnetenwatchAPI',
    'AddressGeocoder',
    'WahlkreisLocator',
    'LocationContext',
    'ConstituencySuggestionService',
    'RepresentativeSyncService',
    'IdentityVerificationService',
    'TopicSuggestionService',
    'CommitteeTopicMappingService',
]
