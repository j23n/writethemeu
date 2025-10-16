# ABOUTME: Tests for identity verification functionality
# ABOUTME: Tests verification linking, forms, and profile address management

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from letters.models import IdentityVerification
from letters.services import IdentityVerificationService
from letters.tests.test_fixtures import ParliamentFixtureMixin


class IdentityVerificationTests(ParliamentFixtureMixin, TestCase):
    """Identity verifications should link back to the new constituency model."""

    def test_complete_verification_links_constituency(self):
        verification = IdentityVerificationService.complete_verification(
            self.user,
            {
                'provider': 'stub',
                'postal_code': '10115',
                'city': 'Berlin',
                'state': 'Berlin',
                'country': 'DE',
            },
        )

        self.assertIsNotNone(verification)
        # Without a street address, WahlkreisResolver won't find constituencies
        self.assertIsNone(verification.constituency)
        self.assertIsNone(verification.federal_constituency)
        self.assertIsNone(verification.state_constituency)
        self.assertEqual(verification.verification_type, 'THIRD_PARTY')
        self.assertTrue(verification.is_third_party)
        # Verify EU wahlkreis is still set to default
        self.assertEqual(verification.eu_wahlkreis, 'DE')

    def test_representative_constituent_matching(self):
        verification = IdentityVerification.objects.create(
            user=self.user,
            status='VERIFIED',
            verification_type='THIRD_PARTY',
            verified_at=timezone.now(),
        )
        # Link constituency via M2M
        verification.constituencies.add(self.constituency_direct)

        self.assertTrue(self.direct_rep.qualifies_as_constituent(verification))
        self.assertTrue(self.list_rep.qualifies_as_constituent(verification))

    def test_self_declare_links_constituencies(self):
        verification = IdentityVerificationService.self_declare(
            self.user,
            federal_constituency=self.constituency_direct,
            state_constituency=self.state_constituency_direct,
        )

        self.assertEqual(verification.status, 'SELF_DECLARED')
        self.assertEqual(verification.verification_type, 'SELF_DECLARED')
        self.assertTrue(verification.is_self_declared)
        self.assertIn(self.constituency_direct, verification.get_constituencies())
        self.assertIn(self.state_constituency_direct, verification.get_constituencies())
        self.assertTrue(self.direct_rep.qualifies_as_constituent(verification))

    @patch('letters.services.wahlkreis.WahlkreisResolver.resolve')
    def test_complete_verification_with_full_address_populates_wahlkreis_fields(self, mock_resolve):
        """Test that Wahlkreis fields are populated when full address is provided"""
        # Set up test constituency with wahlkreis_id
        self.constituency_direct.wahlkreis_id = '075'
        self.constituency_direct.save()

        # Mock WahlkreisResolver to return test data
        mock_resolve.return_value = {
            'federal_wahlkreis_number': '075',
            'state_wahlkreis_number': '075',
            'eu_wahlkreis': 'DE',
            'constituencies': [self.constituency_direct, self.constituency_state]
        }

        verification = IdentityVerificationService.complete_verification(
            self.user,
            {
                'provider': 'stub',
                'street': 'Unter den Linden 1',
                'postal_code': '10117',
                'city': 'Berlin',
                'country': 'DE',
            },
        )

        self.assertIsNotNone(verification)
        # Verify Wahlkreis fields are populated
        self.assertEqual(verification.federal_wahlkreis_number, '075')
        self.assertEqual(verification.state_wahlkreis_number, '075')
        self.assertEqual(verification.eu_wahlkreis, 'DE')
        # Verify constituencies M2M is populated
        constituencies = verification.get_constituencies()
        self.assertEqual(len(constituencies), 2)
        self.assertIn(self.constituency_direct, constituencies)
        self.assertIn(self.constituency_state, constituencies)
        # Verify backward compatibility fields are still set
        self.assertEqual(verification.federal_constituency, self.constituency_direct)
        self.assertEqual(verification.state_constituency, self.constituency_state)


class TestIdentityVerificationWithoutAddress(ParliamentFixtureMixin, TestCase):
    """Test that IdentityVerification works without address fields."""

    def test_verification_works_without_address_fields(self):
        """IdentityVerification should work with M2M constituencies"""
        user = User.objects.create_user(username='testuser', password='testpass')

        verification = IdentityVerification.objects.create(
            user=user,
            status='SELF_DECLARED',
            verification_type='SELF_DECLARED',
        )
        # Link constituency via M2M
        verification.constituencies.add(self.constituency_direct)

        self.assertTrue(verification.is_verified)
        self.assertEqual(verification.federal_constituency, self.constituency_direct)
        constituencies = verification.get_constituencies()
        self.assertEqual(len(constituencies), 1)
        self.assertEqual(constituencies[0], self.constituency_direct)
