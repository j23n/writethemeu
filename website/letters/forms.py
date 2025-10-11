from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .constants import normalize_german_state
from .models import Letter, Representative, Signature, Report, Tag, Constituency, IdentityVerification


class UserRegisterForm(UserCreationForm):
    """Form for user registration"""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _('An account with this email already exists. If you registered before, please check your inbox for the activation link or reset your password.')
            )
        return email


class LetterForm(forms.ModelForm):
    """Form for creating and editing letters"""

    class Meta:
        model = Letter
        fields = ['title', 'body', 'representative']
        labels = {
            'title': _('Title'),
            'body': _('Letter Body'),
            'representative': _('To Representative'),
        }
        help_texts = {
            'title': _('Describe your concern briefly'),
            'body': _('Write your letter here. Markdown formatting (e.g. **bold**, _italic_) is supported.'),
        }
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Letter title')}),
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': _('Write your letter here...')
            }),
            'representative': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        base_queryset = (
            Representative.objects.filter(is_active=True)
            .select_related('parliament', 'parliament_term')
            .prefetch_related('constituencies')
        )
        filtered_queryset = base_queryset

        target_constituencies = []
        target_states = set()

        if self.user and hasattr(self.user, 'identity_verification'):
            verification = getattr(self.user, 'identity_verification', None)
            if verification and verification.is_verified:
                for constituency in verification.get_constituencies():
                    if constituency not in target_constituencies:
                        target_constituencies.append(constituency)
                    metadata_state = (constituency.metadata or {}).get('state') if constituency.metadata else None
                    normalized_metadata_state = normalize_german_state(metadata_state) if metadata_state else None
                    if normalized_metadata_state:
                        target_states.add(normalized_metadata_state)
                if verification.normalized_state:
                    target_states.add(verification.normalized_state)

        constituency_filter = Q()
        for constituency in target_constituencies:
            constituency_filter |= Q(constituencies=constituency)

        state_filter = Q()
        for state in target_states:
            state_filter |= Q(constituencies__metadata__state=state)
            state_filter |= Q(parliament__region__iexact=state)

        combined_filter = constituency_filter | state_filter
        eu_filter = Q(parliament__level='EU')

        if combined_filter:
            filtered_queryset = base_queryset.filter(combined_filter | eu_filter).distinct()
        else:
            filtered_queryset = base_queryset

        self.fields['representative'].queryset = filtered_queryset



class SignatureForm(forms.ModelForm):
    """Form for signing a letter"""

    class Meta:
        model = Signature
        fields = ['comment']
        labels = {
            'comment': _('Comment (optional)'),
        }
        help_texts = {
            'comment': _('Add a personal note to your signature'),
        }
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Optional: Add your comment...')
            })
        }


class ReportForm(forms.ModelForm):
    """Form for reporting a letter"""

    class Meta:
        model = Report
        fields = ['reason', 'description']
        labels = {
            'reason': _('Reason'),
            'description': _('Description'),
        }
        help_texts = {
            'description': _('Please provide details about why you are reporting this letter'),
        }
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('Please describe the issue...')
            })
        }


class LetterSearchForm(forms.Form):
    """Form for searching/filtering letters"""

    q = forms.CharField(
        required=False,
        label=_('Search'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Search letters...')
        })
    )

    tag = forms.CharField(
        required=False,
        label=_('Tag'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Filter by tag...')
        })
    )

    representative = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput()
    )


class SelfDeclaredConstituencyForm(forms.Form):
    """Allow users to self-declare their constituencies."""

    federal_constituency = forms.ModelChoiceField(
        queryset=Constituency.objects.none(),
        required=False,
        label=_('Bundestag constituency'),
        help_text=_('Pick your Bundestag direct mandate constituency (Wahlkreis).'),
        empty_label=_('Select constituency')
    )
    state_constituency = forms.ModelChoiceField(
        queryset=Constituency.objects.none(),
        required=False,
        label=_('State parliament constituency'),
        help_text=_('Optionally pick your Landtag constituency if applicable.'),
        empty_label=_('Select constituency')
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        federal_qs = Constituency.objects.filter(
            parliament_term__parliament__level='FEDERAL',
            scope__in=['FEDERAL_DISTRICT']
        ).select_related('parliament_term__parliament').order_by('name')
        state_qs = Constituency.objects.filter(
            parliament_term__parliament__level='STATE',
            scope__in=['STATE_DISTRICT', 'STATE_REGIONAL_LIST', 'STATE_LIST']
        ).select_related('parliament_term__parliament').order_by(
            'parliament_term__parliament__name', 'name'
        )

        self.fields['federal_constituency'].queryset = federal_qs
        self.fields['state_constituency'].queryset = state_qs
        self.fields['federal_constituency'].widget.attrs.update({
            'class': 'form-select filterable-select',
            'data-live-search': 'true'
        })
        self.fields['state_constituency'].widget.attrs.update({
            'class': 'form-select filterable-select',
            'data-live-search': 'true'
        })

        if self.user and hasattr(self.user, 'identity_verification'):
            verification = getattr(self.user, 'identity_verification', None)
            if verification:
                if verification.federal_constituency_id:
                    self.fields['federal_constituency'].initial = verification.federal_constituency_id
                elif (
                    verification.constituency_id
                    and verification.constituency
                    and verification.constituency.parliament.level == 'FEDERAL'
                ):
                    self.fields['federal_constituency'].initial = verification.constituency_id

                if verification.state_constituency_id:
                    self.fields['state_constituency'].initial = verification.state_constituency_id

    def clean(self):
        cleaned_data = super().clean()
        federal = cleaned_data.get('federal_constituency')
        state = cleaned_data.get('state_constituency')

        if not federal and not state:
            raise forms.ValidationError(
                _('Please select at least one constituency to save your profile.')
            )

        return cleaned_data


class IdentityVerificationForm(forms.Form):
    """Form for collecting full address for identity verification."""

    street_address = forms.CharField(
        max_length=255,
        required=False,
        label=_('Straße und Hausnummer'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('z.B. Unter den Linden 77')
        })
    )
    postal_code = forms.CharField(
        max_length=20,
        required=False,
        label=_('Postleitzahl'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('z.B. 10117')
        })
    )
    city = forms.CharField(
        max_length=100,
        required=False,
        label=_('Stadt'),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('z.B. Berlin')
        })
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Pre-fill with existing address if available
        if self.user and hasattr(self.user, 'identity_verification'):
            verification = getattr(self.user, 'identity_verification', None)
            if verification:
                if verification.street_address:
                    self.fields['street_address'].initial = verification.street_address
                if verification.postal_code:
                    self.fields['postal_code'].initial = verification.postal_code
                if verification.city:
                    self.fields['city'].initial = verification.city

    def clean(self):
        cleaned_data = super().clean()
        street_address = cleaned_data.get('street_address')
        postal_code = cleaned_data.get('postal_code')
        city = cleaned_data.get('city')

        # Check if any field is provided
        has_any = any([street_address, postal_code, city])
        has_all = all([street_address, postal_code, city])

        if has_any and not has_all:
            raise forms.ValidationError(
                _('Bitte geben Sie eine vollständige Adresse ein (Straße, PLZ und Stadt) oder lassen Sie alle Felder leer.')
            )

        return cleaned_data
