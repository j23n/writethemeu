from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import normalize_german_state


class Constituency(models.Model):
    """Represents a political constituency in Germany"""

    LEVEL_CHOICES = [
        ('EU', _('European Union')),
        ('FEDERAL', _('Federal')),
        ('STATE', _('State')),
        ('LOCAL', _('Local')),
    ]

    name = models.CharField(max_length=255, help_text="Name of the constituency")
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    legislative_body = models.CharField(
        max_length=255,
        help_text="e.g., 'Bundestag', 'Bayerischer Landtag', 'Gemeinderat München'"
    )
    legislative_period_start = models.DateField(help_text="When current period began")
    legislative_period_end = models.DateField(
        null=True,
        blank=True,
        help_text="When current period ends (null for ongoing)"
    )
    region = models.CharField(
        max_length=100,
        help_text="Geographic identifier (state code, municipality code, etc.)"
    )
    parent_constituency = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_constituencies',
        help_text="For hierarchical relationships (e.g., local within state)"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional API-specific data"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Constituencies"
        ordering = ['level', 'name']
        indexes = [
            models.Index(fields=['level', 'region']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"


class Representative(models.Model):
    """Represents a political representative"""

    constituency = models.ForeignKey(
        Constituency,
        on_delete=models.CASCADE,
        related_name='representatives'
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    party = models.CharField(max_length=100, blank=True)
    role = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., 'Member of Parliament', 'Minister', etc."
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)

    focus_areas = models.TextField(
        blank=True,
        help_text="Comma-separated list of policy focus areas (e.g., 'climate policy, energy transition, transport'). Can be populated from Wikipedia, speeches, or self-reported data."
    )

    term_start = models.DateField(help_text="When this representative's term started")
    term_end = models.DateField(
        null=True,
        blank=True,
        help_text="When this representative's term ends"
    )
    is_active = models.BooleanField(default=True)

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional API-specific data"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['is_active', 'constituency']),
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.party})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_focus_areas_list(self):
        """Return focus areas as a list"""
        if not self.focus_areas:
            return []
        return [area.strip() for area in self.focus_areas.split(',') if area.strip()]

    @property
    def constituency_scope(self) -> str:
        return (self.metadata or {}).get('constituency_scope', 'district')

    @property
    def list_state_normalized(self) -> str | None:
        return (self.metadata or {}).get('list_state_normalized')

    def qualifies_as_constituent(self, verification: 'IdentityVerification') -> bool:
        if not verification or not verification.is_verified:
            return False

        scope = self.constituency_scope

        if scope == 'federal':
            # Bundesliste: any verified German resident counts
            country = (verification.verification_data or {}).get('country', 'Germany')
            return bool(country)  # Assume verification ensures Germany residency

        if scope == 'state':
            rep_state = self.list_state_normalized
            user_state = verification.normalized_state
            if rep_state and user_state:
                return rep_state.lower() == user_state.lower()
            return False

        # Default: constituency-based match
        return (
            verification.constituency_id is not None and
            self.constituency_id == verification.constituency_id
        )


class Tag(models.Model):
    """Keywords/tags for categorizing letters"""

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TopicArea(models.Model):
    """
    Taxonomy mapping policy topics to governmental levels.
    Based on German constitutional division of powers (Grundgesetz).
    """

    LEVEL_CHOICES = [
        ('EU', 'European Union'),
        ('FEDERAL', 'Federal (Bund)'),
        ('STATE', 'State (Land)'),
        ('LOCAL', 'Local (Kommune)'),
        ('MIXED', 'Mixed Competency'),
    ]

    COMPETENCY_TYPE_CHOICES = [
        ('EXCLUSIVE', 'Exclusive Federal'),
        ('CONCURRENT', 'Concurrent Federal/State'),
        ('STATE', 'State (Länder)'),
        ('LOCAL', 'Local (Municipal)'),
    ]

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Policy area name (e.g., 'Defense', 'Education', 'Local Transportation')"
    )

    slug = models.SlugField(max_length=255, unique=True)

    description = models.TextField(
        blank=True,
        help_text="Description of this policy area and what it covers"
    )

    primary_level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        help_text="Primary governmental level responsible for this topic"
    )

    competency_type = models.CharField(
        max_length=20,
        choices=COMPETENCY_TYPE_CHOICES,
        help_text="Type of competency based on Grundgesetz"
    )

    keywords = models.TextField(
        help_text="Comma-separated keywords for matching user queries (e.g., 'train, railway, Deutsche Bahn, intercity')"
    )

    legal_basis = models.CharField(
        max_length=255,
        blank=True,
        help_text="Constitutional basis (e.g., 'Art. 73 GG', 'Art. 74(22) GG', 'Kulturhoheit')"
    )

    parent_topic = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subtopics',
        help_text="Parent topic for hierarchical organization"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['primary_level', 'name']
        verbose_name = 'Topic Area'
        verbose_name_plural = 'Topic Areas'
        indexes = [
            models.Index(fields=['primary_level']),
            models.Index(fields=['competency_type']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_primary_level_display()})"

    def get_keywords_list(self):
        """Return keywords as a list"""
        return [k.strip() for k in self.keywords.split(',') if k.strip()]


class Committee(models.Model):
    """
    Parliamentary committees (Ausschüsse) at various governmental levels.
    Committees are policy-focused groups where representatives work on specific topics.
    """

    name = models.CharField(
        max_length=255,
        help_text="Committee name (e.g., 'Ausschuss für Umwelt und Verbraucherschutz')"
    )

    parliament = models.CharField(
        max_length=100,
        help_text="Parliament this committee belongs to (e.g., 'Bundestag', 'EU-Parlament', 'Bayern')"
    )

    description = models.TextField(
        blank=True,
        help_text="Description of the committee's responsibilities"
    )

    topic_area = models.ForeignKey(
        TopicArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='committees',
        help_text="Related TopicArea in our taxonomy"
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional API data (api_id, abgeordnetenwatch_url, etc.)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['parliament', 'name']
        unique_together = [['name', 'parliament']]
        indexes = [
            models.Index(fields=['parliament']),
            models.Index(fields=['topic_area']),
        ]

    def __str__(self):
        return f"{self.name} ({self.parliament})"


class CommitteeMembership(models.Model):
    """
    Links representatives to the committees they serve on.
    Tracks role (member, alternate, chair) and time period.
    """

    ROLE_CHOICES = [
        ('member', 'Member'),
        ('alternate_member', 'Alternate Member'),
        ('chair', 'Chair/Vorsitz'),
        ('deputy_chair', 'Deputy Chair/Stellv. Vorsitz'),
        ('foreperson', 'Foreperson/Obfrau/Obmann'),
    ]

    representative = models.ForeignKey(
        Representative,
        on_delete=models.CASCADE,
        related_name='committee_memberships'
    )

    committee = models.ForeignKey(
        Committee,
        on_delete=models.CASCADE,
        related_name='memberships'
    )

    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        help_text="Role in the committee"
    )

    additional_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="Additional roles (from API committee_roles_additional field)"
    )

    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="When membership started"
    )

    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="When membership ended (null for active)"
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional API data"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['representative', 'committee']
        unique_together = [['representative', 'committee']]
        indexes = [
            models.Index(fields=['representative']),
            models.Index(fields=['committee']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.representative.full_name} - {self.committee.name} ({self.role})"

    @property
    def is_active(self):
        """Check if membership is currently active"""
        return self.end_date is None


class Letter(models.Model):
    """Open letters written by users to representatives"""

    STATUS_CHOICES = [
        ('DRAFT', _('Draft')),
        ('PUBLISHED', _('Published')),
        ('FLAGGED', _('Flagged for Review')),
        ('REMOVED', _('Removed')),
    ]

    title = models.CharField(max_length=255)
    body = models.TextField()
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='letters'
    )
    representative = models.ForeignKey(
        Representative,
        on_delete=models.CASCADE,
        related_name='letters'
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='letters')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PUBLISHED')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['representative', '-published_at']),
        ]

    def __str__(self):
        return self.title

    @property
    def signature_count(self):
        return self.signatures.count()

    @property
    def verified_signature_count(self):
        verified, other_verified, _ = self.signature_breakdown()
        return verified + other_verified

    def signature_breakdown(self):
        """Return tuple of (constituent, other_verified, unverified) signature counts."""
        now = timezone.now()

        signatures = list(
            self.signatures.select_related('user', 'user__identity_verification')
        )

        total_verified = 0
        constituent_count = 0
        for signature in signatures:
            verification = getattr(signature.user, 'identity_verification', None)
            if not verification or verification.status != 'VERIFIED':
                continue
            if verification.expires_at and verification.expires_at <= now:
                continue

            total_verified += 1
            if self.representative.qualifies_as_constituent(verification):
                constituent_count += 1

        other_verified = total_verified - constituent_count
        unverified = len(signatures) - total_verified

        return constituent_count, other_verified, unverified


class Signature(models.Model):
    """Represents a user's signature on a letter"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='signatures'
    )
    letter = models.ForeignKey(
        Letter,
        on_delete=models.CASCADE,
        related_name='signatures'
    )

    signed_at = models.DateTimeField(auto_now_add=True)

    # Optional comment when signing
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = ['user', 'letter']
        ordering = ['-signed_at']
        indexes = [
            models.Index(fields=['letter', '-signed_at']),
        ]

    def __str__(self):
        return f"{self.user.username} signed '{self.letter.title}'"

    @property
    def is_verified(self):
        """Check if the user has a verified identity"""
        try:
            return self.user.identity_verification.is_verified
        except IdentityVerification.DoesNotExist:
            return False

    @property
    def verification(self):
        """Return the related IdentityVerification or None if missing."""
        try:
            return self.user.identity_verification
        except IdentityVerification.DoesNotExist:
            return None

    @property
    def is_verified_constituent(self):
        """True when the signer is a verified constituent of the letter's representative."""
        verification = self.verification
        return self.letter.representative.qualifies_as_constituent(verification)

    @property
    def is_verified_non_constituent(self):
        """True when the signer is verified but lives in a different constituency."""
        verification = self.verification
        return bool(verification and verification.is_verified and not self.is_verified_constituent)

    @property
    def display_name(self):
        """Return display name with PPI redaction for public view"""
        verification = getattr(self.user, 'identity_verification', None)
        if verification and verification.is_verified:
            # Show first name and last initial for verified users
            if self.user.first_name and self.user.last_name:
                return f"{self.user.first_name} {self.user.last_name[0]}."
            return self.user.username
        # Show only username for unverified users
        return self.user.username


class IdentityVerification(models.Model):
    """Tracks identity verification status for users"""

    VERIFICATION_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('FAILED', 'Failed'),
        ('EXPIRED', 'Expired'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='identity_verification'
    )

    # Verification provider (stubbed for now)
    provider = models.CharField(
        max_length=100,
        default='stub_provider',
        help_text="Identity verification provider"
    )

    status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='PENDING'
    )

    # Address information from verification
    street_address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)

    # Mapped constituency
    constituency = models.ForeignKey(
        Constituency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_residents',
        help_text="Constituency determined from address"
    )

    # Verification metadata
    verification_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional verification provider data"
    )

    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'user']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"

    @property
    def is_verified(self):
        return self.status == 'VERIFIED' and (
            self.expires_at is None or self.expires_at > timezone.now()
        )

    @property
    def normalized_state(self):
        return normalize_german_state(self.state)


class Report(models.Model):
    """Reports flagging letters for moderation"""

    REASON_CHOICES = [
        ('SPAM', 'Spam'),
        ('OFFENSIVE', 'Offensive Content'),
        ('MISINFORMATION', 'Misinformation'),
        ('OTHER', 'Other'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('REVIEWED', 'Reviewed'),
        ('DISMISSED', 'Dismissed'),
        ('ACTION_TAKEN', 'Action Taken'),
    ]

    letter = models.ForeignKey(
        Letter,
        on_delete=models.CASCADE,
        related_name='reports'
    )
    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports_made',
        null=True,
        blank=True,
        help_text="User who made the report (null for anonymous)"
    )

    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField(help_text="Details of the report")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    moderator_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports_reviewed'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['letter', '-created_at']),
        ]

    def __str__(self):
        return f"Report on '{self.letter.title}' - {self.get_reason_display()}"
