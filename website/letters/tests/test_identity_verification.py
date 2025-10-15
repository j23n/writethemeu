# ABOUTME: Tests for identity verification functionality
# ABOUTME: Tests verification linking, forms, and profile address management

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from letters.forms import IdentityVerificationForm
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
        self.assertEqual(verification.constituency, self.constituency_state)
        self.assertEqual(verification.federal_constituency, self.constituency_state)
        self.assertIsNone(verification.state_constituency)
        self.assertEqual(verification.parliament, self.parliament)
        self.assertEqual(verification.verification_type, 'THIRD_PARTY')
        self.assertTrue(verification.is_third_party)
        self.assertTrue(self.list_rep.qualifies_as_constituent(verification))

    def test_representative_constituent_matching(self):
        verification = IdentityVerification.objects.create(
            user=self.user,
            status='VERIFIED',
            constituency=self.constituency_direct,
            federal_constituency=self.constituency_direct,
            verification_type='THIRD_PARTY',
            verified_at=timezone.now(),
        )

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


class IdentityVerificationFormTests(TestCase):
    """Test the IdentityVerificationForm for full address collection."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='password123',
            email='testuser@example.com',
        )

    def test_form_requires_all_address_fields_together(self):
        """Test that form validation requires all address fields if any is provided."""
        # Only street provided - should fail
        form = IdentityVerificationForm(
            data={
                'street_address': 'Unter den Linden 77',
                'postal_code': '',
                'city': '',
            },
            user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Bitte geben Sie eine vollständige Adresse ein', str(form.errors))

        # Only PLZ provided - should fail
        form = IdentityVerificationForm(
            data={
                'street_address': '',
                'postal_code': '10117',
                'city': '',
            },
            user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Bitte geben Sie eine vollständige Adresse ein', str(form.errors))

        # Only city provided - should fail
        form = IdentityVerificationForm(
            data={
                'street_address': '',
                'postal_code': '',
                'city': 'Berlin',
            },
            user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Bitte geben Sie eine vollständige Adresse ein', str(form.errors))

    def test_form_accepts_all_address_fields(self):
        """Test that form is valid when all address fields are provided."""
        form = IdentityVerificationForm(
            data={
                'street_address': 'Unter den Linden 77',
                'postal_code': '10117',
                'city': 'Berlin',
            },
            user=self.user
        )
        self.assertTrue(form.is_valid())

    def test_form_accepts_empty_address(self):
        """Test that form is valid when all address fields are empty."""
        form = IdentityVerificationForm(
            data={
                'street_address': '',
                'postal_code': '',
                'city': '',
            },
            user=self.user
        )
        self.assertTrue(form.is_valid())



class TestIdentityVerificationWithoutAddress(ParliamentFixtureMixin, TestCase):
    """Test that IdentityVerification works without address fields."""

    def test_verification_works_without_address_fields(self):
        """IdentityVerification should work with only constituency foreign keys"""
        user = User.objects.create_user(username='testuser', password='testpass')

        verification = IdentityVerification.objects.create(
            user=user,
            status='SELF_DECLARED',
            verification_type='SELF_DECLARED',
            federal_constituency=self.constituency_direct
        )

        self.assertTrue(verification.is_verified)
        self.assertEqual(verification.federal_constituency, self.constituency_direct)
        constituencies = verification.get_constituencies()
        self.assertEqual(len(constituencies), 1)
        self.assertEqual(constituencies[0], self.constituency_direct)
