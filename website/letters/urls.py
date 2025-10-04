from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Letter URLs
    path('', views.LetterListView.as_view(), name='letter_list'),
    path('letter/<int:pk>/', views.LetterDetailView.as_view(), name='letter_detail'),
    path('letter/new/', views.LetterCreateView.as_view(), name='letter_create'),
    path('letter/<int:pk>/sign/', views.sign_letter, name='sign_letter'),
    path('letter/<int:pk>/report/', views.report_letter, name='report_letter'),

    # Representative URLs
    path('representative/<int:pk>/', views.RepresentativeDetailView.as_view(), name='representative_detail'),

    # HTMX endpoints
    path('api/analyze-title/', views.analyze_letter_title, name='analyze_title'),

    # Authentication URLs
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='letters/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # User Profile URLs
    path('profile/', views.profile, name='profile'),
    path('profile/verify/', views.start_verification, name='start_verification'),
    path('profile/verify/complete/', views.complete_verification, name='complete_verification'),
]
