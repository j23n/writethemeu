from django.contrib import admin
from .models import (
    Constituency,
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


@admin.register(Constituency)
class ConstituencyAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'legislative_body', 'legislative_period_start', 'legislative_period_end']
    list_filter = ['level', 'legislative_period_start']
    search_fields = ['name', 'legislative_body', 'region']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Representative)
class RepresentativeAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'party', 'constituency', 'is_active', 'term_start', 'term_end']
    list_filter = ['is_active', 'constituency__level', 'party']
    search_fields = ['first_name', 'last_name', 'party', 'constituency__name']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['constituency']


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
    list_display = ['name', 'parliament', 'topic_area', 'member_count', 'created_at']
    list_filter = ['parliament', 'topic_area']
    search_fields = ['name', 'description', 'parliament']
    readonly_fields = ['created_at', 'updated_at', 'member_count']
    raw_id_fields = ['topic_area']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'parliament', 'description')
        }),
        ('Topic Mapping', {
            'fields': ('topic_area',),
            'description': 'Link this committee to a TopicArea in our taxonomy'
        }),
        ('Metadata', {
            'fields': ('metadata', 'created_at', 'updated_at', 'member_count'),
            'classes': ('collapse',)
        }),
    )

    def member_count(self, obj):
        return obj.memberships.count()
    member_count.short_description = 'Members'


@admin.register(CommitteeMembership)
class CommitteeMembershipAdmin(admin.ModelAdmin):
    list_display = ['representative', 'committee', 'role', 'is_active', 'start_date', 'end_date']
    list_filter = ['role', 'committee__parliament']
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
    list_filter = ['status', 'published_at', 'representative__constituency__level']
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
    list_display = ['user', 'status', 'provider', 'constituency', 'verified_at', 'expires_at']
    list_filter = ['status', 'provider', 'verified_at']
    search_fields = ['user__username', 'city', 'postal_code']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user', 'constituency']


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
