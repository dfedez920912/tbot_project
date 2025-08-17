from django.shortcuts import render, redirect
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
            return redirect('web_interface:dashboard')  # ← Con namespace
        else:
            messages.error(request, 'Credenciales inválidas.')
            log_event('WARNING', f'Intento fallido de login para {username}.', 'login')
    return render(request, 'web_interface/login.html')

@login_required
def dashboard_view(request):
    return render(request, 'web_interface/dashboard.html')

def logout_view(request):
    username = request.user.username
    logout(request)
    log_event('INFO', f'Usuario {username} cerró sesión.', 'login')
    return redirect('login')