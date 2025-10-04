from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .constants import normalize_german_state
from .models import Letter, Representative, Signature, Report, Tag


class UserRegisterForm(UserCreationForm):
    """Form for user registration"""
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']


class LetterForm(forms.ModelForm):
    """Form for creating and editing letters"""

    postal_code = forms.CharField(
        required=False,
        max_length=10,
        label=_('Postal code (PLZ)'),
        help_text=_('Use your PLZ to narrow down representatives from your parliament.'),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g. 10115')})
    )

    tags = forms.CharField(
        required=False,
        help_text=_('Comma-separated tags (e.g., "climate, transport, education")'),
        widget=forms.TextInput(attrs={'placeholder': _('climate, transport, education')})
    )

    class Meta:
        model = Letter
        fields = ['title', 'body', 'representative', 'tags']
        labels = {
            'title': _('Title'),
            'body': _('Letter Body'),
            'representative': _('To Representative'),
        }
        help_texts = {
            'title': _('Describe your concern briefly'),
            'body': _('Write your letter here'),
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

        from .services import ConstituencyLocator

        base_queryset = (
            Representative.objects.filter(is_active=True)
            .select_related('parliament', 'parliament_term')
            .prefetch_related('constituencies')
        )
        filtered_queryset = base_queryset

        target_constituencies = []
        target_state = None

        if self.user and hasattr(self.user, 'identity_verification'):
            verification = getattr(self.user, 'identity_verification', None)
            if verification and verification.is_verified:
                if not self.data and verification.postal_code:
                    self.fields['postal_code'].initial = verification.postal_code
                if verification.constituency:
                    target_constituencies.append(verification.constituency)
                if verification.normalized_state:
                    target_state = verification.normalized_state

        postal_code_value = None
        if self.data:
            postal_code_value = self.data.get('postal_code')
        elif 'postal_code' in self.initial:
            postal_code_value = self.initial.get('postal_code')

        if postal_code_value:
            located = ConstituencyLocator.locate(postal_code_value)
            for constituency in filter(None, (located.local, located.state, located.federal)):
                target_constituencies.append(constituency)
                if not target_state:
                    state_hint = normalize_german_state(constituency.metadata.get('state')) if constituency.metadata else None
                    if state_hint:
                        target_state = state_hint

        constituency_filter = Q()
        for constituency in target_constituencies:
            constituency_filter |= Q(constituencies=constituency)

        state_filter = Q()
        if target_state:
            state_filter |= Q(constituencies__metadata__state=target_state)
            state_filter |= Q(parliament__region__iexact=target_state)

        combined_filter = constituency_filter | state_filter
        eu_filter = Q(parliament__level='EU')

        if combined_filter:
            filtered_queryset = base_queryset.filter(combined_filter | eu_filter).distinct()
        else:
            filtered_queryset = base_queryset

        self.fields['representative'].queryset = filtered_queryset

        # Pre-populate tags field if editing
        if self.instance.pk:
            self.fields['tags'].initial = ', '.join(
                tag.name for tag in self.instance.tags.all()
            )

    def save(self, commit=True):
        letter = super().save(commit=False)

        if commit:
            letter.save()

            # Handle tags
            letter.tags.clear()
            tags_input = self.cleaned_data.get('tags', '')
            if tags_input:
                tag_names = [name.strip() for name in tags_input.split(',') if name.strip()]
                for tag_name in tag_names:
                    tag, _ = Tag.objects.get_or_create(
                        name=tag_name,
                        defaults={'slug': tag_name.lower().replace(' ', '-')}
                    )
                    letter.tags.add(tag)

        return letter



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
