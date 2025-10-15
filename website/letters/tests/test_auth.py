# ABOUTME: Tests for user authentication, registration, and account management
# ABOUTME: Covers registration flow, account deletion, and password reset

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from letters.models import (
    Constituency,
    Letter,
    Parliament,
    ParliamentTerm,
    Representative,
    Signature,
)


class AccountRegistrationTests(TestCase):
    """Ensure registration uses double opt-in and activation flow works."""

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_registration_requires_email_confirmation(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newbie',
                'email': 'newbie@example.com',
                'first_name': 'New',
                'last_name': 'User',
                'password1': 'SupersafePassword123',
                'password2': 'SupersafePassword123',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('registration_pending'))
        self.assertTemplateUsed(response, 'letters/account_activation_sent.html')

        user = User.objects.get(username='newbie')
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        activation_response = self.client.get(
            reverse('activate_account', args=[uid, token]),
            follow=True,
        )

        self.assertRedirects(activation_response, reverse('login'))
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class AccountDeletionTests(TestCase):
    """Deleting an account removes signatures but keeps authored letters."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='deleteme',
            password='password123',
            email='deleteme@example.com',
        )

        self.other_user = User.objects.create_user(
            username='other',
            password='password123',
            email='other@example.com',
        )

        self.parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE',
        )
        self.term = ParliamentTerm.objects.create(
            parliament=self.parliament,
            name='20. Wahlperiode',
        )
        self.constituency = Constituency.objects.create(
            parliament_term=self.term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
        )
        self.representative = Representative.objects.create(
            parliament=self.parliament,
            parliament_term=self.term,
            election_mode='DIRECT',
            external_id='rep-del-test',
            first_name='Alex',
            last_name='Muster',
            party='Partei',
        )
        self.representative.constituencies.add(self.constituency)

        self.letter = Letter.objects.create(
            title='Keep parks clean',
            body='Please invest in clean parks.',
            author=self.user,
            representative=self.representative,
        )
        Signature.objects.create(user=self.user, letter=self.letter)
        Signature.objects.create(user=self.other_user, letter=self.letter)

    def test_account_deletion_preserves_letters_and_removes_signatures(self):
        self.client.login(username='deleteme', password='password123')

        response = self.client.post(reverse('delete_account'), follow=True)

        self.assertRedirects(response, reverse('letter_list'))
        self.assertFalse(User.objects.filter(username='deleteme').exists())

        letter = Letter.objects.get(pk=self.letter.pk)
        self.assertIsNone(letter.author)
        self.assertFalse(Signature.objects.filter(user__username='deleteme').exists())
        # Other signatures should remain intact
        self.assertTrue(Signature.objects.filter(user__username='other', letter=letter).exists())


class PasswordResetFlowTests(TestCase):
    """Users can request a password reset and set a new password via the emailed token."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='resetuser',
            password='OldPassword123',
            email='reset@example.com',
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_email_and_confirm(self):
        response = self.client.post(
            reverse('password_reset'),
            {'email': 'reset@example.com'},
            follow=True,
        )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertTemplateUsed(response, 'letters/password_reset_done.html')
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        reset_confirm_url = reverse('password_reset_confirm', args=[uid, token])

        # Django requires a GET request first which redirects to a set-password URL
        get_response = self.client.get(reset_confirm_url, follow=True)

        # Extract the actual set-password URL from the redirect
        set_password_url = get_response.redirect_chain[-1][0]

        # Now POST the new password to the set-password URL
        response = self.client.post(
            set_password_url,
            {'new_password1': 'NewPassword456', 'new_password2': 'NewPassword456'},
            follow=True,
        )

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.assertTemplateUsed(response, 'letters/password_reset_complete.html')

        login_success = self.client.login(username='resetuser', password='NewPassword456')
        self.assertTrue(login_success)
