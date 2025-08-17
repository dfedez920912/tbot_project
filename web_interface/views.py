from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from .models import LogEntry
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import LogEntry  # ← Importa el modelo aquí, no hay problema
from .utils import log_event  # ← Ahora seguro gracias al import diferido

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            log_event('INFO', f'Usuario {username} inició sesión.', 'login')
            # Redirigir a 'next' si existe
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('web_interface:dashboard')
        else:
            messages.error(request, 'Credenciales inválidas.')
            log_event('WARNING', f'Intento fallido de login para {username}.', 'login')
    return render(request, 'web_interface/login.html')

def logs_view(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # ← Solicitud AJAX: devolver JSON
        logs = LogEntry.objects.all().order_by('-timestamp')

        # Filtros
        level = request.GET.get('level')
        source = request.GET.get('source')
        search = request.GET.get('search')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')

        if level:
            logs = logs.filter(level=level)
        if source:
            logs = logs.filter(source__icontains=source)
        if search:
            logs = logs.filter(message__icontains=search)
        if from_date:
            logs = logs.filter(timestamp__date__gte=from_date)
        if to_date:
            logs = logs.filter(timestamp__date__lte=to_date)

        # Paginación
        paginator = Paginator(logs, int(request.GET.get('page_size', 25)))
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Serializar datos
        data = {
            'logs': [
                {
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'level': log.level,
                    'message': log.message,
                    'source': log.source,
                } for log in page_obj
            ],
            'pagination': {
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'num_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'total': paginator.count,
            }
        }
        return JsonResponse(data)

    # ← Solicitud normal: renderizar plantilla
    levels = LogEntry.LEVEL_CHOICES
    sources = LogEntry.objects.values_list('source', flat=True).distinct()
    return render(request, 'web_interface/logs.html', {
        'levels': levels,
        'sources': list(sources),
    })

@login_required
def dashboard_view(request):
    return render(request, 'web_interface/dashboard.html')

def logout_view(request):
    username = request.user.username
    logout(request)
    log_event('INFO', f'Usuario {username} cerró sesión.', 'login')
    return redirect('web_interface:login')