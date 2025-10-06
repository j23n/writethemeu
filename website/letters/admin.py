from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import (
    Parliament,
    ParliamentTerm,
    Representative,
    Tag,
    TopicArea,
    Committee,
    CommitteeMembership,
    Letter,
    Signature,
    IdentityVerification,
    Report,
)


@admin.register(Parliament)
class ParliamentAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'legislative_body', 'region']
    list_filter = ['level', 'region']
    search_fields = ['name', 'legislative_body', 'region']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ParliamentTerm)
class ParliamentTermAdmin(admin.ModelAdmin):
    list_display = ['name', 'parliament', 'start_date', 'end_date']
    list_filter = ['parliament__level', 'start_date']
    search_fields = ['name', 'parliament__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['parliament']


class CommitteeMembershipInlineForRepresentative(admin.TabularInline):
    model = CommitteeMembership
    fk_name = 'representative'
    raw_id_fields = ['committee']
    extra = 0


class CommitteeMembershipInlineForCommittee(admin.TabularInline):
    model = CommitteeMembership
    fk_name = 'committee'
    raw_id_fields = ['representative']
    extra = 0


@admin.register(Representative)
class RepresentativeAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'party', 'parliament', 'parliament_term', 'election_mode', 'is_active', 'term_start', 'term_end']
    list_filter = ['is_active', 'parliament__level', 'party', 'parliament_term__name', 'election_mode']
    search_fields = ['first_name', 'last_name', 'party', 'parliament__name', 'parliament_term__name']
    readonly_fields = ['created_at', 'updated_at', 'photo_updated_at', 'photo_preview']
    raw_id_fields = ['parliament', 'parliament_term']
    filter_horizontal = ['constituencies', 'topic_areas']
    inlines = [CommitteeMembershipInlineForRepresentative]

    fieldsets = (
        (None, {
            'fields': ('first_name', 'last_name', 'party', 'parliament', 'parliament_term', 'election_mode', 'is_active')
        }),
        (_('Mandate Details'), {
            'fields': ('term_start', 'term_end', 'role', 'email', 'phone', 'website')
        }),
        (_('Focus Areas'), {
            'fields': ('focus_areas', 'topic_areas', 'constituencies')
        }),
        (_('Photo'), {
            'fields': ('photo_preview', 'photo_path', 'photo_updated_at'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def photo_preview(self, obj):
        if obj.photo_url:
            return mark_safe(f'<img src="{obj.photo_url}" style="max-height: 200px;" />')
        return _('No photo')
    photo_preview.short_description = _('Photo')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TopicArea)
class TopicAreaAdmin(admin.ModelAdmin):
    list_display = ['name', 'primary_level', 'competency_type', 'legal_basis', 'parent_topic', 'committee_count']
    list_filter = ['primary_level', 'competency_type']
    search_fields = ['name', 'description', 'keywords', 'legal_basis']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at', 'committee_count']
    raw_id_fields = ['parent_topic']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description')
        }),
        ('Governmental Classification', {
            'fields': ('primary_level', 'competency_type', 'legal_basis', 'parent_topic')
        }),
        ('Keywords for Matching', {
            'fields': ('keywords',),
            'description': 'Comma-separated keywords that users might use when describing their concern. '
                          'Example: "train, railway, Deutsche Bahn, intercity, ICE"'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'committee_count'),
            'classes': ('collapse',)
        }),
    )

    def committee_count(self, obj):
        return obj.committees.count()
    committee_count.short_description = 'Linked Committees'


@admin.register(Committee)
class CommitteeAdmin(admin.ModelAdmin):
    list_display = ['name', 'parliament_term', 'topic_area_list', 'member_count', 'created_at']
    list_filter = ['parliament_term__parliament__level', 'topic_areas']
    search_fields = ['name', 'description', 'parliament_term__parliament__name', 'topic_areas__name']
    readonly_fields = ['created_at', 'updated_at', 'member_count']
    filter_horizontal = ['topic_areas']
    inlines = [CommitteeMembershipInlineForCommittee]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'parliament_term', 'description')
        }),
        ('Topic Mapping', {
            'fields': ('topic_areas',),
            'description': 'Link this committee to TopicAreas in our taxonomy'
        }),
        ('Metadata', {
            'fields': ('keywords', 'metadata', 'created_at', 'updated_at', 'member_count'),
            'classes': ('collapse',)
        }),
    )

    def member_count(self, obj):
        return obj.memberships.count()
    member_count.short_description = 'Members'

    def topic_area_list(self, obj):
        names = obj.topic_areas.values_list('name', flat=True)
        return ', '.join(names) or '-'
    topic_area_list.short_description = _('Topic Areas')


@admin.register(CommitteeMembership)
class CommitteeMembershipAdmin(admin.ModelAdmin):
    list_display = ['representative', 'committee', 'role', 'is_active', 'start_date', 'end_date']
    list_filter = ['role', 'committee__parliament_term__parliament__name']
    search_fields = ['representative__first_name', 'representative__last_name', 'committee__name']
    readonly_fields = ['created_at', 'updated_at', 'is_active']
    raw_id_fields = ['representative', 'committee']

    fieldsets = (
        ('Membership', {
            'fields': ('representative', 'committee', 'role', 'additional_roles')
        }),
        ('Time Period', {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'representative', 'status', 'published_at', 'signature_count']
    list_filter = ['status', 'published_at', 'representative__parliament__level']
    search_fields = ['title', 'body', 'author__username', 'representative__last_name']
    readonly_fields = ['created_at', 'updated_at', 'signature_count', 'verified_signature_count']
    raw_id_fields = ['author', 'representative']
    filter_horizontal = ['tags']

    def signature_count(self, obj):
        return obj.signature_count
    signature_count.short_description = 'Signatures'


@admin.register(Signature)
class SignatureAdmin(admin.ModelAdmin):
    list_display = ['user', 'letter', 'signed_at', 'is_verified']
    list_filter = ['signed_at', 'user__identity_verification__status']
    search_fields = ['user__username', 'letter__title']
    readonly_fields = ['signed_at']
    raw_id_fields = ['user', 'letter']


@admin.register(IdentityVerification)
class IdentityVerificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'status', 'provider', 'constituency', 'parliament', 'parliament_term', 'verified_at', 'expires_at']
    list_filter = ['status', 'provider', 'parliament__level', 'verified_at', 'parliament_term__name']
    search_fields = ['user__username', 'city', 'postal_code', 'state', 'parliament__name', 'parliament_term__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user', 'parliament', 'parliament_term', 'constituency']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['letter', 'reason', 'status', 'reporter', 'created_at', 'reviewed_by']
    list_filter = ['status', 'reason', 'created_at']
    search_fields = ['letter__title', 'reporter__username', 'description']
    readonly_fields = ['created_at']
    raw_id_fields = ['letter', 'reporter', 'reviewed_by']

    fieldsets = (
        ('Report Details', {
            'fields': ('letter', 'reporter', 'reason', 'description', 'created_at')
        }),
        ('Moderation', {
            'fields': ('status', 'moderator_notes', 'reviewed_by', 'reviewed_at')
        }),
    )
