# web_interface/views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from web_interface.models import LogEntry  # ✅ Correcto
from telegram_bot.models import TelegramUser  # Asume modelo de usuarios
from django.utils import timezone
from datetime import timedelta

@login_required
def dashboard(request):
    # Estadísticas
    total_users = TelegramUser.objects.count()
    active_users = TelegramUser.objects.filter(last_active__gte=timezone.now() - timedelta(days=7)).count()
    total_logs = LogEntry.objects.count()
    recent_logs = LogEntry.objects.order_by('-timestamp')[:10]

    context = {
        'total_users': total_users,
        'active_users': active_users,
        'total_logs': total_logs,
        'recent_logs': recent_logs,
    }
    return render(request, 'web_interface/dashboard.html', context)

@login_required
def logs_view(request):
    logs = LogEntry.objects.all().order_by('-timestamp')
    return render(request, 'web_interface/logs.html', {'logs': logs})

@login_required
def users_view(request):
    users = TelegramUser.objects.all()
    return render(request, 'web_interface/users.html', {'users': users})