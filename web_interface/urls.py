from django.urls import path, include
from django.views.generic import RedirectView
from . import views

app_name = 'web_interface'

urlpatterns = [
    path('', RedirectView.as_view(url='login/')),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('config/telegram/', views.dashboard_view, name='config_telegram'),
    path('config/email/', views.dashboard_view, name='config_email'),
    path('config/cron/', views.dashboard_view, name='config_cron'),
    path('config/todus/', views.dashboard_view, name='config_todus'),
    path('config/ad/', views.dashboard_view, name='config_ad'),
    path('logs/', views.logs_view, name='logs'),
]