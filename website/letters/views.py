import logging
import re
from collections import OrderedDict

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Count
from django.views.generic import ListView, DetailView, CreateView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _, gettext
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import Letter, Signature, Representative, Tag, IdentityVerification, TopicArea, Committee, Constituency
from .forms import (
    LetterForm,
    SignatureForm,
    ReportForm,
    LetterSearchForm,
    UserRegisterForm,
    SelfDeclaredConstituencyForm,
)
from .services import IdentityVerificationService, ConstituencySuggestionService
from .services.wahlkreis import WahlkreisResolver

logger = logging.getLogger('letters.services')


def _send_activation_email(user, request):
    """Send double opt-in activation email containing confirmation link."""

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_link = request.build_absolute_uri(
        reverse('activate_account', args=[uid, token])
    )

    context = {
        'activation_link': activation_link,
        'username': user.username,
    }

    subject = gettext('Confirm your WriteThem.eu account')
    message = render_to_string('letters/emails/account_activation_email.txt', context)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@writethem.eu')

    send_mail(subject, message, from_email, [user.email], fail_silently=False)


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
            user = form.save(commit=False)
            user.is_active = False
            user.email = form.cleaned_data['email'].strip()
            user.save()

            _send_activation_email(user, request)

            messages.success(
                request,
                gettext('Please confirm your email address. We sent you a link to activate your account.')
            )
            return redirect('registration_pending')
    else:
        form = UserRegisterForm()

    return render(request, 'letters/register.html', {'form': form})


def registration_pending(request):
    """Show instructions after registration until user activates account."""

    return render(request, 'letters/account_activation_sent.html')


def activate_account(request, uidb64, token):
    """Activate user accounts after email confirmation."""

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save()
            messages.success(
                request,
                gettext('Your account has been activated. You can now log in.')
            )
        else:
            messages.info(request, gettext('Your account is already active.'))
        return redirect('login')

    return render(request, 'letters/account_activation_invalid.html', status=400)


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

    if request.method == 'POST':
        constituency_form = SelfDeclaredConstituencyForm(request.POST, user=user)

        if constituency_form.is_valid():
            IdentityVerificationService.self_declare(
                user=user,
                federal_constituency=constituency_form.cleaned_data['federal_constituency'],
                state_constituency=constituency_form.cleaned_data['state_constituency'],
            )
            messages.success(
                request,
                _('Your constituency information has been updated.')
            )
            return redirect('profile')
    else:
        constituency_form = SelfDeclaredConstituencyForm(user=user)

    context = {
        'user_letters': user_letters,
        'user_signatures': user_signatures,
        'verification': verification,
        'constituency_form': constituency_form,
    }

    return render(request, 'letters/profile.html', context)


@login_required
def delete_account(request):
    """Allow users to delete their account while preserving authored letters."""

    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        messages.success(
            request,
            gettext('Your account has been deleted. Your published letters remain available to the public.')
        )
        return redirect('letter_list')

    return render(request, 'letters/account_delete_confirm.html')


class CompetencyOverviewView(TemplateView):
    """Public primer explaining German competency distribution and listing topic areas."""

    template_name = 'letters/competency_overview.html'

    LEVEL_LABELS = OrderedDict([
        ('EU', 'Europäische Union'),
        ('FEDERAL', 'Bund'),
        ('STATE', 'Länder'),
        ('LOCAL', 'Kommunen'),
    ])

    COMPETENCY_LABELS = {
        'EXCLUSIVE': 'Ausschließliche Kompetenz',
        'CONCURRENT': 'Konkurrierende Kompetenz',
        'STATE': 'Landeskompetenz',
        'LOCAL': 'Kommunale Kompetenz',
        'SHARED': 'Geteilte Kompetenz',
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        topics = TopicArea.objects.all().order_by('primary_level', 'name')
        simple_topics = []
        for level_code, level_label in self.LEVEL_LABELS.items():
            level_topics = [topic for topic in topics if topic.primary_level == level_code]
            if not level_topics:
                continue
            simple_topics.append({
                'label': level_label,
                'topics': level_topics,
            })

        competency_overview = [
            {
                'title': 'Bund',
                'description': 'Der Bund kümmert sich um Themen, die das ganze Land betreffen – etwa Sicherheits-, Außen- oder Sozialpolitik.',
                'examples': [
                    {
                        'question': 'Wer entscheidet über die Höhe der gesetzlichen Rente?',
                        'answer': 'Bundestag und Bundesregierung. Sozialversicherungen sind bundesweit geregelt.'
                    },
                    {
                        'question': 'Wer beschließt ein neues Tempolimit auf Autobahnen?',
                        'answer': 'Der Bund. Bundesstraßen und Autobahnen liegen in seiner Verantwortung.'
                    },
                    {
                        'question': 'Wer darf Soldat:innen in einen Auslandseinsatz schicken?',
                        'answer': 'Nur der Bundestag. Auslandseinsätze der Bundeswehr müssen dort beschlossen werden.'
                    },
                ],
            },
            {
                'title': 'Länder',
                'description': 'Die Bundesländer gestalten Bildung, Kultur und Polizei eigenständig – deshalb unterscheidet sich manches von Land zu Land.',
                'examples': [
                    {
                        'question': 'Wer entscheidet, wann die Sommerferien beginnen?',
                        'answer': 'Jedes Bundesland legt den Ferienplan selbst fest.'
                    },
                    {
                        'question': 'Wer bestimmt, welche Fächer im Abitur geprüft werden?',
                        'answer': 'Die Kultusministerien der Länder setzen Lehrpläne und Prüfungsordnungen.'
                    },
                    {
                        'question': 'Wer regelt die Aufgaben der Landespolizei?',
                        'answer': 'Das jeweilige Landesparlament – Polizeigesetze sind Ländersache.'
                    },
                ],
            },
            {
                'title': 'Kommunen',
                'description': 'Gemeinden und Städte gestalten das direkte Lebensumfeld – von Straßen bis zur Kinderbetreuung.',
                'examples': [
                    {
                        'question': 'Wer entscheidet, ob eine Schlaglochstraße saniert wird?',
                        'answer': 'Der Stadtrat bzw. Gemeinderat. Kommunen planen und finanzieren ihre Straßen.'
                    },
                    {
                        'question': 'Wer baut einen neuen Kindergarten?',
                        'answer': 'Die Kommune vor Ort. Sie organisiert Gebäude, Personal und Plätze.'
                    },
                    {
                        'question': 'Wer legt den örtlichen Busfahrplan fest?',
                        'answer': 'Kommunale Verkehrsverbünde und Stadträte gestalten den Nahverkehr.'
                    },
                ],
            },
            {
                'title': 'Europäische Union',
                'description': 'Die EU setzt gemeinsame Standards, wenn alle Mitgliedstaaten betroffen sind – etwa beim Binnenmarkt oder beim Klimaschutz.',
                'examples': [
                    {
                        'question': 'Wer sorgt dafür, dass EU-weit Roaming-Gebühren weggefallen sind?',
                        'answer': 'Das Europäische Parlament und der EU-Ministerrat. Sie haben die entsprechenden Regeln beschlossen.'
                    },
                    {
                        'question': 'Wer verhandelt Handelsabkommen wie das mit Kanada?',
                        'answer': 'Die Europäische Kommission im Auftrag der EU-Mitgliedstaaten.'
                    },
                    {
                        'question': 'Wer legt europaweite CO₂-Grenzwerte für Autos fest?',
                        'answer': 'EU-Institutionen setzen gemeinsame Umweltstandards, die dann in jedem Mitgliedstaat gelten.'
                    },
                ],
            },
        ]

        competency_matrix = [
            {
                'primary_level': 'Bund',
                'competency_type': 'Ausschließliche Kompetenz',
                'description': 'Nur der Bund entscheidet. Die Länder dürfen hier keine eigenen Gesetze erlassen.',
                'legal_basis': 'Art. 71, 73 GG',
                'examples': 'Außenpolitik, Verteidigung, Währung, Luftverkehr',
            },
            {
                'primary_level': 'Bund',
                'competency_type': 'Konkurrierende Kompetenz',
                'description': 'Bund hat Vorrang. Länder können nur tätig werden, wenn der Bund es nicht geregelt hat.',
                'legal_basis': 'Art. 72, 74 GG',
                'examples': 'Strafrecht, Arbeitsrecht, Umweltschutz, Straßenverkehr',
            },
            {
                'primary_level': 'Länder',
                'competency_type': 'Ausschließliche Kompetenz',
                'description': 'Alles, was nicht dem Bund zusteht, regeln die Länder eigenständig.',
                'legal_basis': 'Art. 70 GG',
                'examples': 'Schulbildung, Kultur, Polizei, Hochschulen, Rundfunk',
            },
            {
                'primary_level': 'Länder',
                'competency_type': 'Konkurrierende Kompetenz',
                'description': 'Länder können Gesetze erlassen, solange der Bund nicht aktiv geworden ist.',
                'legal_basis': 'Art. 72 Abs. 1 GG',
                'examples': 'Naturschutz (mit Abweichungsmöglichkeit), Jagdwesen',
            },
            {
                'primary_level': 'Kommunen',
                'competency_type': 'Ausschließliche Kompetenz',
                'description': 'Kommunale Selbstverwaltung: Vor Ort wird entschieden, wie Infrastruktur und Service aussehen.',
                'legal_basis': 'Art. 28 Abs. 2 GG',
                'examples': 'Stadtwerke, Bauleitplanung, lokale Ordnung, Kindergärten',
            },
            {
                'primary_level': 'Europäische Union',
                'competency_type': 'Ausschließliche Kompetenz',
                'description': 'Nur die EU darf tätig werden; Mitgliedstaaten handeln nur auf EU-Mandat.',
                'legal_basis': 'AEUV Art. 3',
                'examples': 'Binnenmarkt, Handelspolitik, Zollunion, Wettbewerb',
            },
            {
                'primary_level': 'Europäische Union',
                'competency_type': 'Geteilte Kompetenz',
                'description': 'EU und Mitgliedstaaten entscheiden gemeinsam – wer zuerst regelt, hat Vorrang.',
                'legal_basis': 'AEUV Art. 4',
                'examples': 'Umweltpolitik, Agrarpolitik, Verbraucherschutz',
            },
        ]

        context.update({
            'topics_by_level': simple_topics,
            'competency_overview': competency_overview,
            'competency_matrix': competency_matrix,
        })
        return context


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


@login_required
@require_http_methods(["POST"])
def search_wahlkreis(request):
    """
    HTMX endpoint: Search for Wahlkreis by address.
    Returns HTML fragment with constituency data or error message.
    """
    street_address = request.POST.get('street_address', '').strip()
    postal_code = request.POST.get('postal_code', '').strip()
    city = request.POST.get('city', '').strip()

    # Validate required fields
    if not all([street_address, postal_code, city]):
        return render(request, 'letters/partials/wahlkreis_search_result.html', {
            'success': False,
            'error': 'Please provide street address, postal code, and city.'
        })

    # Build full address string
    address = f"{street_address}, {postal_code} {city}"

    # Find constituencies using WahlkreisResolver
    try:
        resolver = WahlkreisResolver()
        result = resolver.resolve(address=address, country='DE')
        constituencies = result['constituencies']

        if not constituencies:
            logger.warning(
                f'Address search found no constituencies for {address}'
            )
            return render(request, 'letters/partials/wahlkreis_search_result.html', {
                'success': False,
                'error': 'Could not find constituencies for this address. Please select manually.'
            })

        # Find federal and state constituencies
        federal_constituency = None
        state_constituency = None

        for constituency in constituencies:
            if constituency.scope == 'FEDERAL_DISTRICT' and not federal_constituency:
                federal_constituency = constituency
            elif constituency.scope in ['STATE_LIST', 'STATE_DISTRICT'] and not state_constituency:
                state_constituency = constituency

        # Get display name from metadata if available
        wahlkreis_name = 'Unknown'
        land_name = 'Unknown'

        if federal_constituency and federal_constituency.metadata:
            wahlkreis_name = federal_constituency.name
            land_name = federal_constituency.metadata.get('state', 'Unknown')

        return render(request, 'letters/partials/wahlkreis_search_result.html', {
            'success': True,
            'wahlkreis_name': wahlkreis_name,
            'land_name': land_name,
            'federal_constituency_id': federal_constituency.id if federal_constituency else None,
            'state_constituency_id': state_constituency.id if state_constituency else None,
        })

    except Exception as e:
        logger.exception('Unexpected error during wahlkreis search')
        return render(request, 'letters/partials/wahlkreis_search_result.html', {
            'success': False,
            'error': 'Search temporarily unavailable. Please select Wahlkreise manually.'
        })


# Letter Creation Suggestions (HTMX endpoints)

@login_required
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

    if not title or len(title) < 10:
        return render(request, 'letters/partials/suggestions.html', {
            'message': 'Please enter at least 10 characters to get suggestions'
        })

    user_location = {}
    if request.user.is_authenticated and hasattr(request.user, 'identity_verification'):
        verification = getattr(request.user, 'identity_verification', None)
        if verification and verification.is_verified:
            constituencies = verification.get_constituencies()
            if constituencies:
                user_location['constituencies'] = constituencies
            constituency_states = verification.get_constituency_states()
            if constituency_states:
                user_location.setdefault('state', next(iter(constituency_states)))

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
        'location_available': bool(user_location),
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


def data_sources(request):
    """Display data sources and attribution information."""
    # Hardcoded list of states with constituency data available
    available_states = [
        {
            'code': 'BW',
            'name': 'Baden-Württemberg',
            'attribution': '© Statistisches Landesamt Baden-Württemberg',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2021,
            'count': 70,
            'source_url': 'https://www.statistik-bw.de',
            'note': '',
        },
        {
            'code': 'BY',
            'name': 'Bavaria',
            'attribution': '© Bayerisches Landesamt für Statistik',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2023,
            'count': 91,
            'source_url': 'https://www.statistik.bayern.de',
            'note': '',
        },
        {
            'code': 'BE',
            'name': 'Berlin',
            'attribution': '© Amt für Statistik Berlin-Brandenburg',
            'license': 'CC BY 3.0 DE',
            'license_url': 'https://creativecommons.org/licenses/by/3.0/de/',
            'election_year': 2023,
            'count': 78,
            'source_url': 'https://www.statistik-berlin-brandenburg.de',
            'note': '',
        },
        {
            'code': 'HB',
            'name': 'Bremen',
            'attribution': '© Statistisches Landesamt Bremen',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2023,
            'count': 5,
            'source_url': 'https://www.statistik.bremen.de',
            'note': '',
        },
        {
            'code': 'NI',
            'name': 'Lower Saxony',
            'attribution': '© Landesamt für Statistik Niedersachsen',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2022,
            'count': 87,
            'source_url': 'https://www.statistik.niedersachsen.de',
            'note': '',
        },
        {
            'code': 'NW',
            'name': 'North Rhine-Westphalia',
            'attribution': '© IT.NRW',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2022,
            'count': 128,
            'source_url': 'https://www.it.nrw',
            'note': '',
        },
        {
            'code': 'ST',
            'name': 'Saxony-Anhalt',
            'attribution': '© Statistisches Landesamt Sachsen-Anhalt',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2021,
            'count': 43,
            'source_url': 'https://statistik.sachsen-anhalt.de',
            'note': '',
        },
        {
            'code': 'SH',
            'name': 'Schleswig-Holstein',
            'attribution': '© Statistisches Amt für Hamburg und Schleswig-Holstein',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2022,
            'count': 35,
            'source_url': 'https://www.statistik-nord.de',
            'note': '',
        },
        {
            'code': 'TH',
            'name': 'Thuringia',
            'attribution': '© Thüringer Landesamt für Statistik',
            'license': 'Datenlizenz Deutschland – Namensnennung – Version 2.0',
            'license_url': 'https://www.govdata.de/dl-de/by-2-0',
            'election_year': 2024,
            'count': 44,
            'source_url': 'https://statistik.thueringen.de',
            'note': '',
        },
    ]

    # States without direct downloads
    unavailable_states = [
        {
            'name': 'Brandenburg',
            'contact': 'Ministerium des Innern und für Kommunales, Potsdam',
            'note': 'No state-wide Landtagswahl download. Municipal data available for some cities (e.g., Potsdam).'
        },
        {
            'name': 'Hamburg',
            'contact': 'WFS Service available',
            'note': 'Data available via WFS service (requires GIS tools). Excellent detail with ~1,300 Stimmbezirke.'
        },
        {
            'name': 'Hesse',
            'contact': 'presse@statistik.hessen.de',
            'note': 'Geodata not publicly available. Contact Hessisches Statistisches Landesamt to request.'
        },
        {
            'name': 'Mecklenburg-Vorpommern',
            'contact': 'LAIV-MV',
            'note': 'Shapefiles referenced but require contact with LAIV-MV for downloads.'
        },
        {
            'name': 'Rhineland-Palatinate',
            'contact': 'Landeswahlleiter via wahlen.rlp.de',
            'note': 'Only PDF maps available. No machine-readable geodata.'
        },
        {
            'name': 'Saarland',
            'contact': 'landeswahlleitung@innen.saarland.de',
            'note': 'Special system with only 3 large regional constituencies. Contact required.'
        },
        {
            'name': 'Saxony',
            'contact': 'WMS Service',
            'note': 'WMS service only (visualization, not vector data). May need to contact Statistisches Landesamt.'
        },
    ]

    context = {
        'available_states': available_states,
        'unavailable_states': unavailable_states,
    }

    return render(request, 'letters/data_sources.html', context)
