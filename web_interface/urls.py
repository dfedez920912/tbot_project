from django.urls import path, include
from django.views.generic import RedirectView
from . import views

app_name = 'web_interface'

urlpatterns = [
    path('', RedirectView.as_view(url='login/')),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('logs/', views.logs_view, name='logs'),
    
    # Configuración
    path('config/telegram/', views.config_telegram_view, name='config_telegram'),
    path('monitor/telegram/', views.monitor_telegram_view, name='monitor_telegram'),
    path('config/email/', views.config_email_view, name='config_email'),
    path('config/cron/', views.dashboard_view, name='config_cron'),
    path('config/todus/', views.dashboard_view, name='config_todus'),
    path('config/ad/', views.config_ad_view, name='config_ad'),  # ← Añade esta línea
    path('users/', views.users_view, name='users'),  # ← Vista de usuarios
    
    # servicios
    path('services/', views.services_view, name='services'),
    path('services/telegram/start/', views.telegram_start, name='telegram_start'),
    path('services/telegram/stop/', views.telegram_stop, name='telegram_stop'),
    path('services/telegram/status/', views.telegram_status, name='telegram_status'),
    path('services/telegram/toggle/', views.toggle_telegram, name='toggle_telegram'),
    path('services/telegram/set_auto_start/', views.set_auto_start_linux, name='set_auto_start_linux'),
    
    # Notificaciones
    path('notid/email/', views.config_email_view, name='notif_email'),
    path('notif/todus/', views.dashboard_view, name='notif_todus'),
]