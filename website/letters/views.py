import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.http import HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _, gettext

from .models import Letter, Signature, Report, Representative, Tag, IdentityVerification, TopicArea, Committee
from .forms import (
    LetterForm,
    SignatureForm,
    ReportForm,
    LetterSearchForm,
    UserRegisterForm
)
from .services import IdentityVerificationService, ConstituencySuggestionService


# Letter Views

class LetterListView(ListView):
    """Public view to browse all published letters"""
    model = Letter
    template_name = 'letters/letter_list.html'
    context_object_name = 'letters'
    paginate_by = 20

    def get_queryset(self):
        queryset = Letter.objects.filter(status='PUBLISHED').select_related(
            'author', 'representative', 'representative__parliament'
        ).prefetch_related('tags').annotate(
            signature_count_annotated=Count('signatures')
        )

        # Search functionality
        search_query = self.request.GET.get('q')
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(body__icontains=search_query) |
                Q(representative__first_name__icontains=search_query) |
                Q(representative__last_name__icontains=search_query)
            )

        # Tag filter
        tag = self.request.GET.get('tag')
        if tag:
            queryset = queryset.filter(tags__slug=tag)

        # Representative filter
        rep_id = self.request.GET.get('representative')
        if rep_id:
            queryset = queryset.filter(representative_id=rep_id)

        return queryset.order_by('-published_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = LetterSearchForm(self.request.GET)
        context['popular_tags'] = Tag.objects.annotate(
            letter_count=Count('letters')
        ).order_by('-letter_count')[:10]
        return context


class LetterDetailView(DetailView):
    """Public view to see a single letter with signatures"""
    model = Letter
    template_name = 'letters/letter_detail.html'
    context_object_name = 'letter'

    def get_queryset(self):
        return Letter.objects.filter(status='PUBLISHED').select_related(
            'author', 'representative', 'representative__parliament'
        ).prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        letter = self.object

        # Get signatures with verification status
        signatures = letter.signatures.select_related(
            'user', 'user__identity_verification'
        ).order_by('-signed_at')

        context['signatures'] = signatures
        context['signature_form'] = SignatureForm()

        constituent_count, other_verified_count, unverified_count = (
            letter.signature_breakdown()
        )

        context['constituent_signature_count'] = constituent_count
        context['other_verified_signature_count'] = other_verified_count
        context['unverified_signature_count'] = unverified_count
        context['total_verified_signature_count'] = constituent_count + other_verified_count
        primary_constituency = letter.representative.primary_constituency
        context['constituency'] = primary_constituency.name if primary_constituency else letter.representative.parliament.name

        # Check if current user has signed
        if self.request.user.is_authenticated:
            context['user_has_signed'] = signatures.filter(
                user=self.request.user
            ).exists()
        else:
            context['user_has_signed'] = False

        return context


class LetterCreateView(LoginRequiredMixin, CreateView):
    """View for authenticated users to create letters"""
    model = Letter
    form_class = LetterForm
    template_name = 'letters/letter_form.html'
    success_url = reverse_lazy('letter_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user

        initial = kwargs.setdefault('initial', {})

        # Pre-select representative if provided in query params
        rep_id = self.request.GET.get('rep')
        if rep_id:
            initial['representative'] = rep_id

        # Pre-fill postal code from verification
        verification = getattr(self.request.user, 'identity_verification', None)
        if verification and verification.is_verified and verification.postal_code:
            initial.setdefault('postal_code', verification.postal_code)

        return kwargs

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.status = 'PUBLISHED'

        response = super().form_valid(form)

        Signature.objects.get_or_create(
            user=self.request.user,
            letter=self.object
        )

        messages.success(
            self.request,
            _('Your letter has been published and your signature has been added!')
        )

        return response


@login_required
def sign_letter(request, pk):
    """View to sign a letter"""
    letter = get_object_or_404(Letter, pk=pk, status='PUBLISHED')

    # Check if user already signed
    if Signature.objects.filter(user=request.user, letter=letter).exists():
        messages.warning(request, _('You have already signed this letter.'))
        return redirect('letter_detail', pk=pk)

    if request.method == 'POST':
        form = SignatureForm(request.POST)
        if form.is_valid():
            signature = form.save(commit=False)
            signature.user = request.user
            signature.letter = letter
            signature.save()
            messages.success(request, _('Your signature has been added!'))
            return redirect('letter_detail', pk=pk)

    return redirect('letter_detail', pk=pk)


@login_required
def report_letter(request, pk):
    """Allow authenticated users to report a published letter."""
    letter = get_object_or_404(Letter, pk=pk, status='PUBLISHED')

    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.letter = letter
            report.reporter = request.user
            report.save()
            messages.success(request, _('Thank you for your report. Our team will review it.'))
            return redirect('letter_detail', pk=pk)
    else:
        form = ReportForm()

    return render(
        request,
        'letters/report_letter.html',
        {
            'letter': letter,
            'form': form,
        }
    )


# User Authentication Views

def register(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('letter_list')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, gettext('Welcome, %(username)s! Your account has been created.') % {'username': user.username})
            return redirect('letter_list')
    else:
        form = UserRegisterForm()

    return render(request, 'letters/register.html', {'form': form})


@login_required
def profile(request):
    """User profile view"""
    user = request.user

    # Get user's letters
    user_letters = Letter.objects.filter(author=user).order_by('-published_at')

    # Get user's signatures
    user_signatures = Signature.objects.filter(user=user).select_related(
        'letter', 'letter__representative'
    ).order_by('-signed_at')

    # Get verification status
    try:
        verification = user.identity_verification
    except IdentityVerification.DoesNotExist:
        verification = None

    context = {
        'user_letters': user_letters,
        'user_signatures': user_signatures,
        'verification': verification,
    }

    return render(request, 'letters/profile.html', context)


@login_required
def start_verification(request):
    """Start identity verification process"""
    if hasattr(request.user, 'identity_verification'):
        messages.info(request, 'You have already initiated verification.')
        return redirect('profile')

    # Initialize verification service
    result = IdentityVerificationService.initiate_verification(request.user)

    # In stub mode, just create a pending verification
    IdentityVerification.objects.create(
        user=request.user,
        status='PENDING',
        provider=result['provider']
    )

    messages.info(
        request,
        'Identity verification initiated. In production, you would be redirected to the verification provider.'
    )
    return redirect('profile')


@login_required
def complete_verification(request):
    """Complete verification (stub endpoint)"""
    # STUB: In production, this would be called by the verification provider

    verification_data = {
        'street_address': '123 Main St',
        'postal_code': '10115',
        'city': 'Berlin',
        'state': 'Berlin',
        'verified': True,
        'provider': 'stub_provider',
    }

    verification = IdentityVerificationService.complete_verification(
        request.user,
        verification_data
    )

    if verification and verification.is_verified:
        messages.success(request, 'Your identity has been verified! (Stub mode)')
    else:
        messages.error(
            request,
            'Verification failed. Please try again or contact support.'
        )
    return redirect('profile')


# Letter Creation Suggestions (HTMX endpoints)

@require_http_methods(["POST"])
def analyze_letter_title(request):
    """
    HTMX endpoint: Analyzes letter title and returns suggestions for:
    - Topic areas
    - Representatives
    - Keywords
    - Similar letters
    """
    title = request.POST.get('title', '').strip()
    postal_code = request.POST.get('postal_code', '').strip()

    if not title or len(title) < 10:
        return render(request, 'letters/partials/suggestions.html', {
            'message': 'Please enter at least 10 characters to get suggestions'
        })

    user_location = {}
    if postal_code:
        user_location['postal_code'] = postal_code

    if request.user.is_authenticated and hasattr(request.user, 'identity_verification'):
        verification = getattr(request.user, 'identity_verification', None)
        if verification and verification.is_verified:
            if verification.city:
                user_location.setdefault('city', verification.city)
            if verification.state:
                user_location.setdefault('state', verification.state)

    # Analyze with ConstituencySuggestionService
    suggestion_result = ConstituencySuggestionService.suggest_from_concern(
        title,
        user_location=user_location or None
    )

    # Get similar letters based on title using whole phrase and significant keywords
    search_terms = [term for term in re.findall(r"\w+", title) if len(term) >= 4]

    search_query = Q(title__icontains=title) | Q(body__icontains=title)
    for term in search_terms:
        search_query |= Q(title__icontains=term) | Q(body__icontains=term)

    similar_letters = (
        Letter.objects.filter(status='PUBLISHED')
        .filter(search_query)
        .select_related('author', 'representative')
        .annotate(similar_signature_count=Count('signatures'))
        .order_by('-similar_signature_count', '-published_at')
        .distinct()[:5]
    )

    topic_keywords = []
    for topic in suggestion_result.get('matched_topics', [])[:2]:
        topic_keywords.extend(topic.get_keywords_list()[:5])

    keywords = suggestion_result.get('keywords', [])
    keywords = list(dict.fromkeys(keywords + topic_keywords + search_terms))[:10]

    context = {
        'title': title,
        'suggestion_result': suggestion_result,
        'similar_letters': similar_letters,
        'keywords': keywords,
    }

    return render(request, 'letters/partials/suggestions.html', context)


# Representative Detail View

class RepresentativeDetailView(DetailView):
    """Public view to see representative information"""
    model = Representative
    template_name = 'letters/representative_detail.html'
    context_object_name = 'representative'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'parliament', 'parliament_term'
        ).prefetch_related(
            'topic_areas',
            'committee_memberships__committee__parliament_term__parliament',
            'committee_memberships__committee__topic_areas'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rep = self.object

        # Get letters to this representative
        letters_to_rep = (
            Letter.objects.filter(representative=rep, status='PUBLISHED')
            .select_related('author')
            .prefetch_related('tags')
            .annotate(sig_count=Count('signatures'))
            .order_by('-published_at')
        )

        context['letters_to_rep'] = letters_to_rep

        # Get committee memberships
        committee_memberships = rep.committee_memberships.select_related(
            'committee__parliament_term__parliament'
        ).prefetch_related('committee__topic_areas').order_by('committee__name')

        context['committee_memberships'] = list(committee_memberships)
        context['topic_areas'] = rep.topic_areas.order_by('name')

        # Get abgeordnetenwatch profile link
        abgeordnetenwatch_url = rep.metadata.get('abgeordnetenwatch_url')
        if not abgeordnetenwatch_url:
            abgeordnetenwatch_url = (
                rep.metadata.get('mandate', {})
                .get('politician', {})
                .get('abgeordnetenwatch_url')
            )
        context['abgeordnetenwatch_url'] = abgeordnetenwatch_url or ''

        # Get Wikipedia link (from metadata if available)
        wikipedia_url = rep.metadata.get('wikipedia_url')
        if not wikipedia_url:
            links = (
                rep.metadata.get('mandate', {})
                .get('politician', {})
                .get('links', [])
            )
            for link in links:
                label = (link.get('label') or '').lower()
                url = link.get('url') or link.get('href')
                if 'wikipedia' in label and url:
                    wikipedia_url = url
                    break
        context['wikipedia_url'] = wikipedia_url or ''

        return context


class CommitteeDetailView(DetailView):
    """Public view to show committee details and its members."""
    model = Committee
    template_name = 'letters/committee_detail.html'
    context_object_name = 'committee'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'parliament_term__parliament'
        ).prefetch_related('topic_areas')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        committee = self.object
        memberships = committee.memberships.select_related(
            'representative__parliament',
            'representative__parliament_term'
        ).prefetch_related(
            'representative__topic_areas',
            'representative__constituencies'
        ).order_by('representative__last_name', 'representative__first_name')
        context['memberships'] = memberships
        return context
