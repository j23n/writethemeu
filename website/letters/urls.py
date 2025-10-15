from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Letter URLs
    path('', views.LetterListView.as_view(), name='letter_list'),
    path('letter/<int:pk>/', views.LetterDetailView.as_view(), name='letter_detail'),
    path('letter/new/', views.LetterCreateView.as_view(), name='letter_create'),
    path('letter/<int:pk>/sign/', views.sign_letter, name='sign_letter'),
    path('letter/<int:pk>/report/', views.report_letter, name='report_letter'),

    path('kompetenzen/', views.CompetencyOverviewView.as_view(), name='competency_overview'),

    # Representative URLs
    path('representative/<int:pk>/', views.RepresentativeDetailView.as_view(), name='representative_detail'),
    path('committee/<int:pk>/', views.CommitteeDetailView.as_view(), name='committee_detail'),

    # Information pages
    path('data-sources/', views.data_sources, name='data_sources'),

    # HTMX endpoints
    path('api/analyze-title/', views.analyze_letter_title, name='analyze_title'),
    path('api/search-wahlkreis/', views.search_wahlkreis, name='search_wahlkreis'),

    # Authentication URLs
    path('register/', views.register, name='register'),
    path('register/confirm/', views.registration_pending, name='registration_pending'),
    path('activate/<uidb64>/<token>/', views.activate_account, name='activate_account'),
    path('login/', auth_views.LoginView.as_view(template_name='letters/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='letters/password_reset_form.html',
            email_template_name='letters/emails/password_reset_email.txt',
            subject_template_name='letters/emails/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='letters/password_reset_done.html'
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='letters/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='letters/password_reset_complete.html'
        ),
        name='password_reset_complete',
    ),

    # User Profile URLs
    path('profile/', views.profile, name='profile'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('profile/verify/', views.start_verification, name='start_verification'),
    path('profile/verify/complete/', views.complete_verification, name='complete_verification'),
]
