# ABOUTME: Identity verification service for user address verification.
# ABOUTME: Provides stub implementation for third-party identity providers and self-declaration.

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional

from django.utils import timezone

from .constituency import ConstituencyLocator, LocatedConstituencies

if TYPE_CHECKING:
    from ..models import Constituency, IdentityVerification


class IdentityVerificationService:
    """Stubbed identity service (kept for API compatibility)."""

    @staticmethod
    def initiate_verification(user, provider='stub_provider') -> Dict[str, str]:
        return {
            'status': 'initiated',
            'provider': provider,
            'verification_url': '/verify/stub/',
            'session_id': 'stub-session',
        }

    @staticmethod
    def complete_verification(user, verification_data: Dict[str, str]) -> Optional[IdentityVerification]:
        from ..models import IdentityVerification

        postal_code = (verification_data.get('postal_code') or '').strip()
        located = ConstituencyLocator.locate_legacy(postal_code) if postal_code else LocatedConstituencies(None, None, None)
        constituency = located.local or located.state or located.federal

        expires_at_value = verification_data.get('expires_at')
        expires_at = None
        if expires_at_value:
            try:
                candidate = datetime.fromisoformat(expires_at_value)
                expires_at = timezone.make_aware(candidate) if timezone.is_naive(candidate) else candidate
            except (TypeError, ValueError):
                expires_at = None

        defaults = {
            'status': 'VERIFIED',
            'provider': verification_data.get('provider', 'stub_provider'),
            'verification_data': verification_data,
            'verified_at': timezone.now(),
            'expires_at': expires_at,
            'verification_type': 'THIRD_PARTY',
        }

        defaults['constituency'] = constituency
        defaults['federal_constituency'] = located.federal
        defaults['state_constituency'] = located.state

        verification, _ = IdentityVerification.objects.update_or_create(
            user=user,
            defaults=defaults,
        )
        verification._update_parliament_links()
        verification.save(update_fields=[
            'provider',
            'status',
            'verification_data',
            'verified_at',
            'expires_at',
            'constituency',
            'federal_constituency',
            'state_constituency',
            'parliament_term',
            'parliament',
            'verification_type',
        ])
        return verification

    @staticmethod
    def self_declare(
        user,
        federal_constituency: Optional[Constituency] = None,
        state_constituency: Optional[Constituency] = None,
    ) -> Optional[IdentityVerification]:
        from ..models import IdentityVerification

        verification, _ = IdentityVerification.objects.get_or_create(
            user=user,
            defaults={'provider': 'self_declared'}
        )

        verification.provider = 'self_declared'
        verification.status = 'SELF_DECLARED'
        verification.verification_type = 'SELF_DECLARED'
        verification.federal_constituency = federal_constituency
        verification.state_constituency = state_constituency
        verification.constituency = federal_constituency or state_constituency
        verification.verified_at = timezone.now()
        verification.expires_at = None

        verification_data = verification.verification_data or {}
        verification_data['self_declared'] = True
        if federal_constituency:
            verification_data['federal_constituency_id'] = federal_constituency.id
        if state_constituency:
            verification_data['state_constituency_id'] = state_constituency.id
        verification.verification_data = verification_data

        verification._update_parliament_links()
        verification.save()
        return verification
