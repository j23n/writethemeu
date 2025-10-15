from typing import Dict, List, Optional, Set

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import normalize_german_state


class Parliament(models.Model):
    """Represents a political parliament (Bundestag, Landtag, council, etc.)."""

    LEVEL_CHOICES = [
        ('EU', _('European Union')),
        ('FEDERAL', _('Federal')),
        ('STATE', _('State')),
        ('LOCAL', _('Local')),
    ]

    name = models.CharField(max_length=255, help_text=_('Name of the parliament'))
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    legislative_body = models.CharField(
        max_length=255,
        help_text=_("e.g., 'Bundestag', 'Bayerischer Landtag', 'Gemeinderat München'")
    )
    region = models.CharField(
        max_length=100,
        help_text=_('Geographic identifier (state code, municipality code, etc.)')
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        help_text=_('For hierarchical relationships (e.g., local within state)')
    )
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text=_('Last time this was synced from external API'))

    class Meta:
        ordering = ['level', 'name']
        verbose_name = _('Parliament')
        verbose_name_plural = _('Parliaments')
        indexes = [models.Index(fields=['level', 'region'])]

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"


class ParliamentTerm(models.Model):
    """Specific legislative term for a parliament (e.g., 20. Bundestag)."""

    parliament = models.ForeignKey(
        Parliament,
        on_delete=models.CASCADE,
        related_name='terms'
    )
    name = models.CharField(max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text=_('Last time this was synced from external API'))

    class Meta:
        ordering = ['parliament__level', 'parliament__name', 'name']
        indexes = [models.Index(fields=['parliament', 'name'])]

    def __str__(self):
        return f"{self.name} ({self.parliament.name})"


class Constituency(models.Model):
    """Set of voters represented together (direct seat or list-based)."""

    SCOPE_CHOICES = [
        ('FEDERAL_DISTRICT', _('Federal electoral district')),
        ('FEDERAL_STATE_LIST', _('Bundestag state list')),
        ('FEDERAL_LIST', _('Bundestag federal list')),
        ('STATE_DISTRICT', _('State electoral district')),
        ('STATE_REGIONAL_LIST', _('State regional list')),
        ('STATE_LIST', _('State wide list')),
        ('EU_AT_LARGE', _('EU at large')),
    ]

    parliament_term = models.ForeignKey(
        ParliamentTerm,
        on_delete=models.CASCADE,
        related_name='constituencies'
    )
    name = models.CharField(max_length=255)
    external_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    scope = models.CharField(max_length=30, choices=SCOPE_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text=_('Last time this was synced from external API'))

    class Meta:
        ordering = ['parliament_term__parliament__level', 'name']
        unique_together = [('parliament_term', 'name', 'scope')]

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"


class Representative(models.Model):
    """Represents a political representative."""

    ELECTION_MODE_CHOICES = [
        ('DIRECT', _('Direct mandate')),
        ('STATE_LIST', _('State list mandate')),
        ('STATE_REGIONAL_LIST', _('State regional list mandate')),
        ('FEDERAL_LIST', _('Federal list mandate')),
        ('EU_LIST', _('EU list mandate')),
    ]

    parliament_term = models.ForeignKey(
        ParliamentTerm,
        on_delete=models.CASCADE,
        related_name='representatives'
    )
    parliament = models.ForeignKey(
        Parliament,
        on_delete=models.CASCADE,
        related_name='representatives'
    )
    election_mode = models.CharField(max_length=25, choices=ELECTION_MODE_CHOICES)
    external_id = models.CharField(max_length=100, unique=True)
    constituencies = models.ManyToManyField(
        Constituency,
        blank=True,
        related_name='representatives'
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    party = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    focus_areas = models.TextField(blank=True)
    photo_path = models.CharField(max_length=255, blank=True)
    photo_updated_at = models.DateTimeField(null=True, blank=True)
    topic_areas = models.ManyToManyField(
        'letters.TopicArea',
        blank=True,
        related_name='representatives'
    )
    term_start = models.DateField(null=True, blank=True)
    term_end = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text=_('Last time this was synced from external API'))

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['is_active', 'parliament_term']),
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.party})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def primary_constituency(self):
        """Return the first linked constituency (cached per instance)."""
        constituencies = getattr(self, '_constituency_cache', None)
        if constituencies is None:
            constituencies = list(self.constituencies.all())
            self._constituency_cache = constituencies
        return constituencies[0] if constituencies else None

    def get_metadata_value(self, key: str, default=None):
        metadata = self.metadata or {}
        return metadata.get(key, default)

    def get_focus_areas_list(self):
        if self.focus_areas:
            return [area.strip() for area in self.focus_areas.split(',') if area.strip()]
        return self.focus_topics

    @property
    def photo_url(self):
        if self.photo_path:
            from django.conf import settings
            return settings.MEDIA_URL + self.photo_path
        return ''

    @property
    def biography(self) -> str:
        value = self.get_metadata_value('biography', '')
        if isinstance(value, str):
            return value.strip()
        return ''

    @property
    def focus_topics(self) -> List[str]:
        value = self.get_metadata_value('focus_topics', [])
        if isinstance(value, list):
            return [topic for topic in value if isinstance(topic, str) and topic.strip()]
        if isinstance(value, str):
            return [topic.strip() for topic in value.split(',') if topic.strip()]
        return []

    @property
    def contact_links(self) -> List[Dict[str, str]]:
        links = self.get_metadata_value('links', [])
        cleaned: List[Dict[str, str]] = []
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                url = link.get('url')
                if not url:
                    continue
                label = link.get('label') or link.get('type') or url
                cleaned.append({'label': label, 'url': url})
        return cleaned

    def qualifies_as_constituent(self, verification: 'IdentityVerification') -> bool:
        if not verification or not verification.is_verified:
            return False

        constituencies = getattr(self, '_constituency_cache', None)
        if constituencies is None:
            constituencies = list(self.constituencies.all())
            self._constituency_cache = constituencies

        if self.parliament.level == 'EU':
            return bool(verification.get_constituencies())

        verification_constituencies = verification.get_constituencies()
        verification_constituency_ids = {c.id for c in verification_constituencies}

        if verification_constituency_ids and any(c.id in verification_constituency_ids for c in constituencies):
            return True

        normalized_state = verification.normalized_state
        verification_states = verification.get_constituency_states()

        rep_states = {
            normalize_german_state(c.metadata.get('state'))
            for c in constituencies
            if c.metadata and c.metadata.get('state')
        }

        if self.election_mode == 'FEDERAL_LIST':
            return bool(verification.get_constituencies())

        if self.election_mode in {'STATE_LIST', 'STATE_REGIONAL_LIST'}:
            if verification_states & rep_states:
                return True
            if normalized_state and normalized_state in rep_states:
                return True

        if self.election_mode == 'DIRECT':
            if verification_states & rep_states:
                return True
            if normalized_state and normalized_state in rep_states:
                return True

        return False


class Tag(models.Model):
    """Keywords/tags for categorizing letters."""

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TopicArea(models.Model):
    """Policy taxonomy used for committee/topic matching."""

    LEVEL_CHOICES = [
        ('EU', 'European Union'),
        ('FEDERAL', 'Federal (Bund)'),
        ('STATE', 'State (Land)'),
        ('LOCAL', 'Local (Kommune)'),
    ]

    COMPETENCY_TYPE_CHOICES = [
        ('EXCLUSIVE', 'Ausschließliche Gesetzgebung'),
        ('CONCURRENT', 'Konkurrierende Gesetzgebung'),
        ('DEVIATION', 'Abweichungsgesetzgebung'),
        ('JOINT', 'Gemeinschaftsaufgaben'),
        ('RESIDUAL', 'Länderkompetenz'),
        ('SHARED', 'Geteilte Zuständigkeit'),
    ]

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    primary_level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    competency_type = models.CharField(max_length=20, choices=COMPETENCY_TYPE_CHOICES)
    keywords = models.TextField()
    legal_basis = models.CharField(max_length=255)
    legal_basis_url = models.URLField()
    parent_topic = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subtopics'
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
        return [k.strip() for k in self.keywords.split(',') if k.strip()]


class Committee(models.Model):
    """Parliamentary committees (Ausschüsse)."""

    name = models.CharField(max_length=255)
    external_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    parliament_term = models.ForeignKey(
        ParliamentTerm,
        on_delete=models.CASCADE,
        related_name='committees'
    )
    description = models.TextField(blank=True)
    keywords = models.TextField(blank=True, help_text='Comma-separated keywords extracted from name and description')
    topic_areas = models.ManyToManyField(
        TopicArea,
        blank=True,
        related_name='committees'
    )
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text=_('Last time this was synced from external API'))

    class Meta:
        ordering = ['parliament_term__parliament__name', 'name']
        unique_together = [('parliament_term', 'name')]
        indexes = [
            models.Index(fields=['parliament_term']),
            models.Index(fields=['external_id']),
        ]

    def __str__(self):
        return f"{self.name} ({self.parliament_term})"

    def get_keywords_list(self):
        """Return keywords as a list."""
        if not self.keywords:
            return []
        return [k.strip() for k in self.keywords.split(',') if k.strip()]


class CommitteeMembership(models.Model):
    """Links representatives to the committees they serve on."""

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
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    additional_roles = models.JSONField(default=list, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text=_('Last time this was synced from external API'))

    class Meta:
        ordering = ['representative', 'committee']
        unique_together = [('representative', 'committee')]
        indexes = [
            models.Index(fields=['representative']),
            models.Index(fields=['committee']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.representative.full_name} - {self.committee.name} ({self.role})"

    @property
    def is_active(self):
        return self.end_date is None


class Letter(models.Model):
    """Open letters written by users to representatives."""

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
        on_delete=models.SET_NULL,
        related_name='letters',
        null=True,
        blank=True,
    )
    representative = models.ForeignKey(Representative, on_delete=models.CASCADE, related_name='letters')
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
    def author_display_name(self):
        
        if self.author:
            full_name = self.author.get_full_name()
            return full_name or self.author.username
        return _('Deleted user')

    @property
    def verified_signature_count(self):
        verified, other_verified, _ = self.signature_breakdown()
        return verified + other_verified

    def signature_breakdown(self):
        """Return tuple of (constituent, other_verified, unverified) signature counts."""
        now = timezone.now()
        signatures = self.signatures.select_related('user', 'user__identity_verification')

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
        unverified = signatures.count() - total_verified
        return constituent_count, other_verified, unverified


class Signature(models.Model):
    """Represents a user's signature on a letter."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='signatures')
    letter = models.ForeignKey(Letter, on_delete=models.CASCADE, related_name='signatures')
    signed_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = ['user', 'letter']
        ordering = ['-signed_at']
        indexes = [models.Index(fields=['letter', '-signed_at'])]

    def __str__(self):
        return f"{self.user.username} signed '{self.letter.title}'"

    @property
    def is_verified(self):
        try:
            return self.user.identity_verification.is_verified
        except IdentityVerification.DoesNotExist:
            return False

    @property
    def verification(self):
        try:
            return self.user.identity_verification
        except IdentityVerification.DoesNotExist:
            return None

    @property
    def is_verified_constituent(self):
        verification = self.verification
        return self.letter.representative.qualifies_as_constituent(verification)

    @property
    def is_verified_non_constituent(self):
        verification = self.verification
        return bool(verification and verification.is_verified and not self.is_verified_constituent)

    @property
    def display_name(self):
        verification = getattr(self.user, 'identity_verification', None)
        if verification and verification.is_verified:
            if self.user.first_name and self.user.last_name:
                return f"{self.user.first_name} {self.user.last_name[0]}."
            return self.user.username
        return self.user.username


class IdentityVerification(models.Model):
    """Tracks identity verification status for users."""

    VERIFICATION_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified (third party)'),
        ('SELF_DECLARED', 'Self-declared'),
        ('FAILED', 'Failed'),
        ('EXPIRED', 'Expired'),
    ]

    VERIFICATION_TYPE_CHOICES = [
        ('THIRD_PARTY', 'Third-party Provider'),
        ('SELF_DECLARED', 'Self-declared'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='identity_verification')
    provider = models.CharField(max_length=100, default='stub_provider')
    status = models.CharField(max_length=20, choices=VERIFICATION_STATUS_CHOICES, default='PENDING')
    parliament = models.ForeignKey(
        Parliament,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_residents'
    )
    parliament_term = models.ForeignKey(
        ParliamentTerm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_residents'
    )
    constituency = models.ForeignKey(
        Constituency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_residents'
    )
    federal_constituency = models.ForeignKey(
        Constituency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='federal_verified_residents'
    )
    state_constituency = models.ForeignKey(
        Constituency,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='state_verified_residents'
    )
    verification_data = models.JSONField(default=dict, blank=True)
    verification_type = models.CharField(
        max_length=20,
        choices=VERIFICATION_TYPE_CHOICES,
        default='THIRD_PARTY'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'user'])]

    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"

    @property
    def is_verified(self):
        if self.status not in {'VERIFIED', 'SELF_DECLARED'}:
            return False
        return (
            self.expires_at is None or self.expires_at > timezone.now()
        )

    @property
    def is_self_declared(self) -> bool:
        return self.status == 'SELF_DECLARED'

    @property
    def is_third_party(self) -> bool:
        return self.verification_type == 'THIRD_PARTY' and self.status == 'VERIFIED'

    @property
    def normalized_state(self):
        """Get normalized state from linked constituencies"""
        states = self.get_constituency_states()
        return next(iter(states)) if states else None

    def link_constituency(self, constituency: Constituency, scope: Optional[str] = None) -> None:
        """Attach the verification to a specific constituency and infer parliament links."""
        if not constituency:
            return

        scope = scope or constituency.scope

        if scope in {'FEDERAL_DISTRICT', 'STATE_DISTRICT'}:
            self.constituency = constituency
        elif not self.constituency:
            self.constituency = constituency

        if scope and scope.startswith('FEDERAL'):
            self.federal_constituency = constituency
        if scope and scope.startswith('STATE'):
            self.state_constituency = constituency

        self._update_parliament_links()

    def _update_parliament_links(self) -> None:
        for constituency in self.get_constituencies():
            self.parliament_term = constituency.parliament_term
            self.parliament = constituency.parliament_term.parliament
            return
        if self.parliament_term:
            self.parliament = self.parliament_term.parliament

    def save(self, *args, **kwargs):
        self._update_parliament_links()
        super().save(*args, **kwargs)

    def get_constituencies(self) -> List[Constituency]:
        """Return distinct constituencies linked to this verification."""
        constituencies: List[Constituency] = []
        seen: Set[int] = set()
        for attr in ('constituency', 'federal_constituency', 'state_constituency'):
            constituency = getattr(self, attr, None)
            if constituency and constituency.id not in seen:
                constituencies.append(constituency)
                seen.add(constituency.id)
        return constituencies

    def constituency_ids(self) -> List[int]:
        return [c.id for c in self.get_constituencies()]

    def get_constituency_states(self) -> Set[str]:
        states: Set[str] = set()
        for constituency in self.get_constituencies():
            metadata_state = (constituency.metadata or {}).get('state') if constituency.metadata else None
            if metadata_state:
                normalized_state = normalize_german_state(metadata_state)
                if normalized_state:
                    states.add(normalized_state)
        return states


class Report(models.Model):
    """Reports flagging letters for moderation."""

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

    letter = models.ForeignKey(Letter, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports_made',
        null=True,
        blank=True,
        help_text='User who made the report (null for anonymous)'
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField()
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


class GeocodeCache(models.Model):
    """Cache geocoding results to minimize API calls."""

    address_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA256 hash of normalized address for fast lookup"
    )
    street = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default='DE')

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    success = models.BooleanField(
        default=True,
        help_text="False if geocoding failed, to avoid repeated failed lookups"
    )
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Geocode Cache Entry"
        verbose_name_plural = "Geocode Cache Entries"
        ordering = ['-created_at']

    def __str__(self):
        if self.latitude and self.longitude:
            return f"{self.city} ({self.latitude}, {self.longitude})"
        return f"{self.city} (failed)"
