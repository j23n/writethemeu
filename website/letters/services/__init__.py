# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

# Import remaining classes from monolith for backward compatibility
from .._services_monolith import (
    AddressGeocoder,
    WahlkreisLocator,
    LocatedConstituencies,
    LocationContext,
    ConstituencyLocator,
    ConstituencySuggestionService,
    RepresentativeSyncService,
    IdentityVerificationService,
    TopicSuggestionService,
    CommitteeTopicMappingService,
)

__all__ = [
    'AbgeordnetenwatchAPI',
    'AddressGeocoder',
    'WahlkreisLocator',
    'LocatedConstituencies',
    'LocationContext',
    'ConstituencyLocator',
    'ConstituencySuggestionService',
    'RepresentativeSyncService',
    'IdentityVerificationService',
    'TopicSuggestionService',
    'CommitteeTopicMappingService',
]
