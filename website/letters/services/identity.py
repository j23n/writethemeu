# ABOUTME: Identity verification service for user address verification.
# ABOUTME: Provides stub implementation for third-party identity providers and self-declaration.

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional

from django.utils import timezone

from .wahlkreis import WahlkreisResolver

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

        # Extract address components
        street = (verification_data.get('street') or '').strip()
        postal_code = (verification_data.get('postal_code') or '').strip()
        city = (verification_data.get('city') or '').strip()
        country = verification_data.get('country', 'DE')

        # Resolve using WahlkreisResolver if we have full address
        federal_wahlkreis_number = None
        state_wahlkreis_number = None
        eu_wahlkreis = 'DE'
        constituencies_to_link = []

        if street and postal_code and city:
            resolver = WahlkreisResolver()
            wahlkreis_result = resolver.resolve(street, postal_code, city, country)

            federal_wahlkreis_number = wahlkreis_result['federal_wahlkreis_number']
            state_wahlkreis_number = wahlkreis_result['state_wahlkreis_number']
            eu_wahlkreis = wahlkreis_result['eu_wahlkreis']
            constituencies_to_link = wahlkreis_result['constituencies']

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
            'federal_wahlkreis_number': federal_wahlkreis_number,
            'state_wahlkreis_number': state_wahlkreis_number,
            'eu_wahlkreis': eu_wahlkreis,
        }

        verification, _ = IdentityVerification.objects.update_or_create(
            user=user,
            defaults=defaults,
        )

        # Link constituencies via M2M
        if constituencies_to_link:
            verification.constituencies.clear()
            for constituency_obj in constituencies_to_link:
                verification.constituencies.add(constituency_obj)
            # Update parliament links after M2M is populated
            verification._update_parliament_links()

        verification.save(update_fields=[
            'provider',
            'status',
            'verification_data',
            'verified_at',
            'expires_at',
            'federal_wahlkreis_number',
            'state_wahlkreis_number',
            'eu_wahlkreis',
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
        verification.verified_at = timezone.now()
        verification.expires_at = None

        verification_data = verification.verification_data or {}
        verification_data['self_declared'] = True
        verification_data['country'] = verification_data.get('country', 'DE')
        if federal_constituency:
            verification_data['federal_constituency_id'] = federal_constituency.id
        if state_constituency:
            verification_data['state_constituency_id'] = state_constituency.id
        verification.verification_data = verification_data

        # Link constituencies via M2M
        verification.constituencies.clear()
        if federal_constituency:
            verification.constituencies.add(federal_constituency)
        if state_constituency:
            verification.constituencies.add(state_constituency)

        verification._update_parliament_links()
        verification.save()
        return verification
