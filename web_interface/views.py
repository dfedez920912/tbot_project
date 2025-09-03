import os
import json
import logging
import requests
import threading
import psutil
import asyncio
import subprocess
import sys
import re
import time
from datetime import datetime
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from pathlib import Path
from collections import OrderedDict
from dotenv import dotenv_values, load_dotenv, set_key
from decouple import AutoConfig, config as decouple_config
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Importaciones desde ad_connector
from ad_connector.ad_operations import (
    get_ad_config,
    fetch_ad_users,
    check_group_membership,
    get_ad_group_config,
    is_ad_admin_group_enabled,
    fetch_ad_users_for_import,
    get_users_in_ad_group,
)

from telegram_bot.handlers import run_bot

# ← Variable global para controlar el hilo
telegram_bot_thread = None
bot_running = False

# Importaciones locales
from .models import LogEntry, AppSetting
from .utils import log_event


# ← Ruta absoluta al proyecto
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

# ← Ruta al archivo de estado
STATUS_FILE = Path(__file__).parent.parent / 'telegram_bot' / 'services_status.json'


# ← Definir el evento global ANTES de cualquier función que lo use
stop_bot_event = threading.Event()

# ← Variable global para el hilo del bot
bot_thread = None


# ← Comando base
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANAGE_PY = f'{sys.executable} {os.path.join(PROJECT_DIR, "manage.py")}'

# ← Tareas disponibles
CRON_JOBS = {
    'sync_users': {
        'command': f'{MANAGE_PY} sync_users',
        'description': 'Sincroniza usuarios del AD con la base de datos'
    },
    'password_expiration': {
        'command': f'{MANAGE_PY} password_expiration',
        'description': 'Envía alertas de vencimiento de contraseñas'
    }
}


def get_crontab():
    """Lee el crontab del usuario actual."""
    try:
        result = os.popen('crontab -l 2>/dev/null').read()
        lines = result.strip().split('\n') if result.strip() else []
        jobs = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            for job_name, job in CRON_JOBS.items():
                if job['command'] in line:
                    jobs.append({
                        'name': job_name,
                        'schedule': ' '.join(parts[:5]),
                        'command': job['command'],
                        'enabled': True
                    })
                    break
        return jobs
    except Exception as e:
        print(f"Error leyendo crontab: {e}")
        return []

def save_crontab(jobs):
    """Guarda las tareas en el crontab."""
    try:
        lines = []
        for job in jobs:
            if job['enabled']:
                lines.append(f"{job['schedule']} {job['command']}")
        cron_content = '\n'.join(lines) + '\n'
        with open('/tmp/my_cron', 'w') as f:
            f.write(cron_content)
        os.system('crontab /tmp/my_cron')
        os.remove('/tmp/my_cron')
        return True
    except Exception as e:
        print(f"Error guardando crontab: {e}")
        return False

@login_required
def cron_view(request):
    """Vista para gestionar tareas programadas."""
    crontab_jobs = get_crontab()
    jobs_dict = {job['name']: job for job in crontab_jobs}

    # ← Añadir tareas que no están en crontab
    for job_name in CRON_JOBS:
        if job_name not in jobs_dict:
            default_schedule = '0 */6 * * *' if job_name == 'sync_users' else '0 8 * * *'
            jobs_dict[job_name] = {
                'name': job_name,
                'schedule': default_schedule,
                'command': CRON_JOBS[job_name]['command'],
                'enabled': False
            }

    return render(request, 'web_interface/cron.html', {
        'jobs': jobs_dict,
        'current_page': 'cron'  # ← Para activar el sidebar
    })

@csrf_exempt
@login_required
def edit_cron_job(request, job):
    """Muestra el modal de edición."""
    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    if job not in CRON_JOBS:
        return JsonResponse({'status': 'error', 'message': 'Tarea no válida'}, status=400)

    jobs = get_crontab()
    current_job = next((j for j in jobs if j['name'] == job), None)

    if not current_job:
        current_job = {
            'name': job,
            'schedule': '0 */6 * * *' if job == 'sync_users' else '0 8 * * *',
            'command': CRON_JOBS[job]['command'],
            'enabled': False
        }

    return render(request, 'web_interface/partials/cron_edit_modal.html', {
        'job': current_job
    })

@csrf_exempt
@login_required
def save_cron_job(request):
    """Guarda o actualiza una tarea."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        job_name = data.get('job')
        enabled = data.get('enabled', False)
        schedule = data.get('schedule', '')

        if job_name not in CRON_JOBS:
            return JsonResponse({'status': 'error', 'message': 'Tarea no válida'}, status=400)

        if enabled and not re.match(r'^(\*|[0-5]?\d)\s+(\*|[01]?\d|2[0-3])\s+(\*|[12]?\d|3[01])\s+(\*|[1-9]|1[0-2])\s+(\*|[0-6])$', schedule):
            return JsonResponse({'status': 'error', 'message': 'Formato de cron inválido'}, status=400)

        jobs = get_crontab()
        job_found = False
        for job in jobs:
            if job['name'] == job_name:
                job['enabled'] = enabled
                if enabled:
                    job['schedule'] = schedule
                job_found = True
                break

        if not job_found and enabled:
            jobs.append({
                'name': job_name,
                'schedule': schedule,
                'command': CRON_JOBS[job_name]['command'],
                'enabled': True
            })

        if save_crontab(jobs):
            return JsonResponse({
                'status': 'success',
                'message': f'Tarea {"habilitada" if enabled else "deshabilitada"} correctamente.'
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'No se pudo guardar el crontab.'}, status=500)

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def get_status():
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    "telegram_running": data.get("telegram_running", False),
                    "telegram_start_time": data.get("telegram_start_time"),
                    "telegram_auto_start": data.get("telegram_auto_start", False)
                }
        except json.JSONDecodeError as e:
            logger.error(f"Error al leer {STATUS_FILE}: {e}")
    return {
        "telegram_running": False,
        "telegram_start_time": None,
        "telegram_auto_start": False
    }


def update_status(telegram_running=None, telegram_start_time=None, telegram_auto_start=None):
    """Actualiza el estado del bot en services_status.json"""
    try:
        status = get_status()
        if telegram_running is not None:
            status['telegram_running'] = telegram_running
        if telegram_start_time is not None:
            status['telegram_start_time'] = telegram_start_time
        if telegram_auto_start is not None:
            status['telegram_auto_start'] = telegram_auto_start

        # ← Asegurar que el directorio exista
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=4)

        return True
    except Exception as e:
        logger.error(f"Error al actualizar estado: {e}")
        return False

# ← Importar run_bot_sync desde handlers.py
try:
    from telegram_bot.handlers import run_bot_sync
    RUN_BOT_AVAILABLE = True
except Exception as e:
    logger.exception("No se pudo importar run_bot_sync")
    RUN_BOT_AVAILABLE = False
    run_bot_sync = None



@csrf_exempt
@login_required
def set_auto_start_enable(request):
    """Habilita el inicio automático del bot."""
    if request.method == 'POST':
        try:
            # ← Crear o actualizar el servicio systemd
            service_content = """[Unit]
Description=TBot Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory={project_dir}
ExecStart={python_path} manage.py run_bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target""".format(
                project_dir=settings.BASE_DIR,
                python_path=sys.executable  # ← Usa el mismo Python que Django
            )

            # ← Guardar el servicio temporalmente
            temp_service = '/tmp/tbot_telegram.service'
            with open(temp_service, 'w') as f:
                f.write(service_content.strip())

            # ← Mover y habilitar el servicio
            os.system('sudo mv /tmp/tbot_telegram.service /etc/systemd/system/')
            os.system('sudo systemctl daemon-reload')
            os.system('sudo systemctl enable tbot_telegram.service')
            os.system('sudo systemctl start tbot_telegram.service')

            # ← Actualizar estado
            update_status(telegram_auto_start=True)

            return JsonResponse({
                'status': 'success',
                'message': 'Inicio automático habilitado y servicio iniciado.'
            })
        except Exception as e:
            logger.exception("Error al habilitar inicio automático")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@csrf_exempt
@login_required
def set_auto_start_disable(request):
    """Deshabilita el inicio automático del bot."""
    if request.method == 'POST':
        try:
            # ← Detener y deshabilitar el servicio
            os.system('sudo systemctl stop tbot_telegram.service')
            os.system('sudo systemctl disable tbot_telegram.service')
            os.system('sudo systemctl daemon-reload')

            # ← Actualizar estado
            update_status(telegram_auto_start=False)

            return JsonResponse({
                'status': 'success',
                'message': 'Inicio automático desactivado.'
            })
        except Exception as e:
            logger.exception("Error al deshabilitar inicio automático")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def telegram_start(request):
    status = get_status()
    if status["telegram_running"]:
        return JsonResponse({'status': 'error', 'message': 'El bot ya está en ejecución.'}, status=400)

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        return JsonResponse({'status': 'error', 'message': 'Falta el token del bot en .env'}, status=500)

    if not RUN_BOT_AVAILABLE:
        return JsonResponse({'status': 'error', 'message': 'No se puede iniciar el bot: módulo no disponible.'}, status=500)

    def run_bot_safe():
        try:
            # ← Ejecutar run_bot_sync en este hilo
            run_bot_sync(token, stop_event=stop_bot_event)
        except Exception as e:
            logger.exception(f"Error en run_bot: {str(e)}")
        finally:
            # ← Resetear el evento
            stop_bot_event.clear()
            # ← Actualizar estado
            update_status(telegram_running=False, telegram_start_time=None)
            global bot_thread
            bot_thread = None

    # ← Actualizar estado: iniciando
    current_time = time.time()
    update_status(
        telegram_running=True,
        telegram_start_time=current_time,
        telegram_auto_start=status["telegram_auto_start"]
    )

    global bot_thread
    bot_thread = threading.Thread(target=run_bot_safe, daemon=True)
    bot_thread.start()

    logger.info("Bot de Telegram iniciado desde la API.")
    return JsonResponse({'status': 'success', 'message': 'Bot de Telegram iniciado.'})

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def telegram_stop(request):
    status = get_status()
    if not status["telegram_running"]:
        return JsonResponse({'status': 'error', 'message': 'El bot ya está detenido.'}, status=400)

    # ← Activar el evento para detener el bot
    global stop_bot_event
    stop_bot_event.set()

    logger.info("Señal de detención enviada al bot de Telegram.")
    return JsonResponse({'status': 'success', 'message': 'Señal de detención enviada. El bot se detendrá pronto.'})

@require_http_methods(["GET"])
@login_required
def telegram_status(request):
    status = get_status()
    uptime = None
    if status["telegram_running"] and status["telegram_start_time"]:
        uptime_seconds = time.time() - status["telegram_start_time"]
        hours = int(uptime_seconds // 3600)
        mins = int((uptime_seconds % 3600) // 60)
        secs = int(uptime_seconds % 60)
        uptime = f"{hours}h {mins}m {secs}s"

    return JsonResponse({
        'status': 'success',
        'data': {
            'running': status["telegram_running"],
            'start_time': status["telegram_start_time"],
            'auto_start': status["telegram_auto_start"],
            'uptime': uptime
        }
    })

# ← Función para guardar el JSON manteniendo el orden original
def save_messages_with_order(messages_file, updated_messages, original_order):
    """
    Guarda el JSON manteniendo el orden original de las claves.
    """
    ordered_data = OrderedDict()

    # ← Recorrer el orden original y reconstruir el JSON
    for key in original_order:
        if key in updated_messages:
            ordered_data[key] = updated_messages[key]
        else:
            # ← Si la clave no fue modificada, intentar mantenerla
            pass

    # ← Asegurar que todas las claves del orden original estén presentes
    with open(messages_file, 'r', encoding='utf-8') as f:
        original_data = json.load(f, object_pairs_hook=OrderedDict)

    for key in original_order:
        if key in original_data:
            ordered_data[key] = updated_messages.get(key, original_data[key])

    # ← Escribir con indentación
    with open(messages_file, 'w', encoding='utf-8') as f:
        json.dump(ordered_data, f, ensure_ascii=False, indent=4)
        
        
# --- VISTAS DE AUTENTICACIÓN ---

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            log_event('INFO', f'Usuario {username} inició sesión.', 'login')
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('web_interface:dashboard')
        else:
            messages.error(request, 'Credenciales inválidas.')
            log_event('WARNING', f'Intento fallido de login para {username}.', 'login')
    return render(request, 'web_interface/login.html')


@login_required
def dashboard_view(request):
    return render(request, 'web_interface/dashboard.html', {
        'current_page': 'dashboard'
    })

@login_required
def get_stats(request):
    """Devuelve métricas del sistema en formato JSON."""
    try:
        # ← CPU
        cpu_percent = psutil.cpu_percent(interval=1)

        # ← RAM
        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        ram_used_gb = ram.used / (1024**3)
        ram_total_gb = ram.total / (1024**3)

        # ← Red (LAN)
        net = psutil.net_io_counters()
        net_bytes_sent = net.bytes_sent
        net_bytes_recv = net.bytes_recv
        time.sleep(1)
        net = psutil.net_io_counters()
        upload_speed = (net.bytes_sent - net_bytes_sent) / 1.0
        download_speed = (net.bytes_recv - net_bytes_recv) / 1.0

        def format_speed(bps):
            if bps < 1024:
                return f"{bps:.1f} B/s"
            elif bps < 1024**2:
                return f"{bps / 1024:.1f} KB/s"
            else:
                return f"{bps / (1024**2):.1f} MB/s"

        return JsonResponse({
            'cpu_percent': round(cpu_percent, 1),
            'ram_percent': round(ram_percent, 1),
            'ram_used': round(ram_used_gb, 2),
            'ram_total': round(ram_total_gb, 2),
            'download_speed': format_speed(download_speed),
            'upload_speed': format_speed(upload_speed)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    

@login_required
def logout_view(request):
    username = request.user.username
    logout(request)
    log_event('INFO', f'Usuario {username} cerró sesión.', 'login')
    return redirect('web_interface:login')


# --- VISTA DE CONFIGURACIÓN DE AD ---

@login_required
def config_ad_view(request):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    config = dotenv_values(env_path)

    if request.GET.get('action') == 'test_connection':
        try:
            users = fetch_ad_users(retries=1)
            return JsonResponse({
                'success': True,
                'message': f'Conexión exitosa. {len(users)} usuarios obtenidos.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error de conexión: {str(e)}'
            })

    if request.method == 'POST':
        keys_to_update = [
            'AD_SERVER', 'AD_PORT', 'AD_USE_SSL', 'AD_USER', 'AD_SEARCH_BASE',
            'AD_DOMAIN', 'AD_PASSWORD_POLICY_DAYS', 'SESSION_DURATION'
        ]
        for key in keys_to_update:
            value = request.POST.get(key)
            if value is not None:
                set_key(env_path, key, value)
        config = dotenv_values(env_path)
        log_event('INFO', 'Configuración de AD actualizada desde la interfaz web.', 'config_ad')
        return JsonResponse({'status': 'success', 'message': 'Configuración guardada.'})

    ad_config = get_ad_config()
    return render(request, 'web_interface/config_ad.html', {
        'config': config,
        'ad_config': ad_config,
    })
    
    
# --- VISTA UNIFICADA: USUARIOS ---

@login_required
def users_view(request):
    logger.info(f"users_view llamado con método: {request.method}")
    if request.method == 'POST':
        logger.info(f"POST  {request.POST}")

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    config = dotenv_values(env_path)

    # --- POST: Acciones
    if request.method == 'POST':
        action = request.POST.get('action')
        if not action:
            # Guardar configuración del grupo
            ad_group_val = request.POST.get('AD_GROUP')
            # ← Cambiar de 'in request.POST' a obtener el valor
            enable_auth_value = request.POST.get('enable_ad_admin_auth', 'false')
            enable_auth = enable_auth_value.lower() == 'true'  # ← Convertir a booleano

            logger.info(f"Guardando configuración: AD_GROUP={ad_group_val}, enable_ad_admin_auth={enable_auth}")

            if ad_group_val:
                set_key(env_path, 'AD_GROUP', ad_group_val)

            # Guardar en base de datos
            try:
                from web_interface.models import AppSetting
                AppSetting.set_bool(
                    'AD_ADMIN_GROUP_AUTH',
                    enable_auth,
                    'Habilita autenticación basada en grupo AD'
                )
                logger.info(f"Estado guardado en DB: AD_ADMIN_GROUP_AUTH = {enable_auth}")
            except Exception as e:
                logger.exception("Error al guardar en AppSetting")

            log_event('INFO', 'Configuración de grupo de administradores actualizada.', 'users_view')
            return JsonResponse({'status': 'success', 'message': 'Configuración guardada.'})
        
        elif request.POST.get('action') == 'import_ad_admins':
            try:
                selected_users = json.loads(request.POST.get('users'))
                imported = 0

                for user_data in selected_users:
                    username = user_data.get('username')
                    if not username:
                        continue

                    user, created = User.objects.get_or_create(username=username)
                    if not created and not user.username:
                        user.username = username

                    if created or not user.has_usable_password():
                        user.set_unusable_password()

                    user.first_name = user_data.get('first_name', '')
                    user.last_name = user_data.get('last_name', '')
                    user.email = user_data.get('email', '')
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()

                    if created:
                        imported += 1
                        # ← Log: Usuario AD importado
                        log_event(
                            'INFO',
                            f"Usuario '{username}' importado del grupo AD por '{request.user.username}'.",
                            'users_view'
                        )

                return JsonResponse({'success': True, 'count': imported})
            except Exception as e:
                logger.exception("Error en import_ad_admins")
                return JsonResponse({'success': False, 'message': str(e)}, status=500)


        elif action == 'toggle_user':
            try:
                username = request.POST.get('username')
                if not username:
                    return JsonResponse({'success': False, 'message': 'Usuario requerido.'}, status=400)

                user = User.objects.get(username__iexact=username)
                new_status = not user.is_active
                user.is_active = new_status
                user.save()

                # ← Log: Usuario habilitado/deshabilitado
                status_text = "habilitado" if new_status else "deshabilitado"
                log_event(
                    'INFO',
                    f"Usuario '{username}' {status_text} por '{request.user.username}'.",
                    'users_view'
                )

                return JsonResponse({'success': True})
            except User.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Usuario no encontrado.'}, status=404)
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)


        elif action == 'delete_user':
            try:
                username = request.POST.get('username')
                if not username:
                    return JsonResponse({'success': False, 'message': 'Usuario requerido.'}, status=400)

                user = User.objects.get(username__iexact=username)
                if user.username == 'admin':
                    return JsonResponse({'success': False, 'message': 'No se puede eliminar el usuario admin.'}, status=400)

                deleted_username = user.username
                user.delete()

                # ← Log: Usuario eliminado
                log_event(
                    'WARNING',  # ← Nivel WARNING por ser una acción irreversible
                    f"Usuario '{deleted_username}' eliminado por '{request.user.username}'.",
                    'users_view'
                )

                return JsonResponse({'success': True})
            except User.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Usuario no encontrado.'}, status=404)
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
    # --- GET AJAX: Obtener usuarios del grupo AD ---
    if request.GET.get('action') == 'fetch_ad_admins':
        try:
            raw_users = get_users_in_ad_group()
            admins = []

            for user in raw_users:
                username = user.get('username')
                if not username:
                    continue
                admins.append({
                    'username': username,
                    'name': f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or username,
                    'first_name': user.get('first_name', ''),
                    'last_name': user.get('last_name', ''),
                    'email': user.get('email', '')
                })

            logger.info(f"Usuarios del grupo AD encontrados: {len(admins)}")
            return JsonResponse({'success': True, 'users': admins})
        except Exception as e:
            logger.exception("Error en fetch_ad_admins")
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    # --- Vista normal: Preparar datos ---
    django_users = []
    ad_domain = os.getenv('AD_DOMAIN', '').lower()
    raw_ad_users = get_users_in_ad_group()
    ad_usernames = {u['username'].lower() for u in raw_ad_users if 'username' in u}

    for user in User.objects.all().order_by('username'):
        email_domain = user.email.split('@')[-1].lower() if '@' in user.email else ''
        if email_domain == ad_domain:
            origin = 'AD'
        elif user.username.lower() in ad_usernames and user.username != 'admin':
            origin = 'AD'
        else:
            origin = 'Local'

        origin_class = 'info' if origin == 'AD' else 'primary'
        status_icon = 'check' if user.is_active else 'times'

        django_users.append({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'origin': origin,
            'origin_class': origin_class,
            'status_icon': status_icon,
            'is_active': user.is_active
        })

    ad_group = get_ad_group_config()
    auth_enabled = is_ad_admin_group_enabled()  # ← Lee de DB

    return render(request, 'web_interface/users.html', {
        'django_users': django_users,
        'ad_group': ad_group,
        'auth_enabled': auth_enabled,
        'config': config,
    })

# --- VISTA DE LOGS ---

@login_required
def logs_view(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
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
            page_size = int(request.GET.get('page_size', 25))
            paginator = Paginator(logs, page_size)
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
        except Exception as e:
            logger.exception("Error en logs_view AJAX")
            return JsonResponse({'error': 'Error interno'}, status=500)

    # Solicitud normal
    levels = LogEntry.LEVEL_CHOICES
    sources = LogEntry.objects.values_list('source', flat=True).distinct()
    return render(request, 'web_interface/logs.html', {
        'levels': levels,
        'sources': list(sources),
    })

    # Solicitud normal
    levels = LogEntry.LEVEL_CHOICES
    sources = LogEntry.objects.values_list('source', flat=True).distinct()
    return render(request, 'web_interface/logs.html', {
        'levels': levels,
        'sources': list(sources),
    })


# --- VISTA DE CONFIGURACION EMAIL ---
    
@login_required
def config_email_view(request):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    config = dotenv_values(env_path)

    email_keys = [
        'EMAIL_HOST',
        'EMAIL_PORT',
        'EMAIL_USE_TLS',
        'EMAIL_USE_SSL',
        'EMAIL_HOST_USER',
        'EMAIL_HOST_PASSWORD',
        'EMAIL_SENDER',
        'DEFAULT_FROM_EMAIL'
    ]

    email_config = {key: config.get(key, '') for key in email_keys}

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'test_email':
            try:
                recipient = request.POST.get('recipient')
                if not recipient:
                    return JsonResponse({'status': 'error', 'message': 'Correo de destino requerido.'})

                from email_service.email_sender import enviar_correo

                subject = "Correo de prueba desde TBot Project"
                cuerpo_html = """
                <html>
                <body>
                    <h2>Correo de prueba</h2>
                    <p>Este es un correo de prueba enviado desde la interfaz de configuración de correo.</p>
                    <p><strong>¡La configuración es correcta!</strong></p>
                </body>
                </html>
                """

                try:
                    enviar_correo(destinatarios=[recipient], asunto=subject, cuerpo_html=cuerpo_html)
                    log_event('INFO', f'Correo de prueba enviado exitosamente a {recipient}.', 'config_email')
                    return JsonResponse({'status': 'success', 'message': 'Correo de prueba enviado.'})
                except Exception as e:
                    error_msg = str(e)
                    log_event('ERROR', f'Fallo al enviar correo de prueba a {recipient}: {error_msg}', 'config_email')
                    return JsonResponse({'status': 'error', 'message': f'Error al enviar: {error_msg}'})

            except Exception as e:
                logger.exception("Error inesperado al enviar correo de prueba")
                log_event('CRITICAL', f'Error inesperado en prueba de correo: {str(e)}', 'config_email')
                return JsonResponse({'status': 'error', 'message': f'Error interno: {str(e)}'}, status=500)

        elif action == 'save_config':
            try:
                if not os.path.exists(env_path):
                    open(env_path, 'w').close()

                # ← Usar set_key de python-dotenv
                for key in email_keys:
                    value = request.POST.get(key)
                    if value is not None:
                        set_key(env_path, key, value)

                # ← Recargar variables de entorno
                load_dotenv(env_path, override=True)

                log_event('INFO', 'Configuración de correo actualizada desde la interfaz web.', 'config_email')
                return JsonResponse({'status': 'success', 'message': 'Configuración guardada.'})

            except Exception as e:
                logger.exception("Error al guardar configuración de correo")
                log_event('ERROR', 'Error al guardar configuración de correo desde la interfaz web.', 'config_email')
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        else:
            logger.warning(f"Acción inválida en config_email: {action}")
            log_event('WARNING', 'Acción inválida en config_email: {action}.', 'config_email')
            return JsonResponse({'status': 'error', 'message': 'Acción no válida.'}, status=400)

    # ← Solo en GET: renderizar plantilla
    return render(request, 'web_interface/config_email.html', {
        'config': email_config
    })
    
# --- VISTA DE CONFIGURACION TELEGRAM ---
@login_required
def config_telegram_view(request):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    
    # --- 1. Leer el token de Telegram ---
    config = dotenv_values(env_path)
    telegram_token = config.get('TELEGRAM_BOT_TOKEN', '')

    # --- 2. Leer los mensajes del bot ---
    messages_file = Path(__file__).parent.parent / 'telegram_bot' / 'messages.json'
    messages = {}
    if messages_file.exists():
        with open(messages_file, 'r', encoding='utf-8') as f:
            try:
                messages = json.load(f, object_pairs_hook=OrderedDict)
            except json.JSONDecodeError as e:
                logger.error(f"Error al leer messages.json: {e}")
                messages = {}

    # --- 3. Leer las etiquetas de los mensajes ---
    labels_file = Path(__file__).parent.parent / 'telegram_bot' / 'message_labels.json'
    labels = {}  # ← Definido aquí
    if labels_file.exists():
        with open(labels_file, 'r', encoding='utf-8') as f:
            try:
                labels = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Error al leer message_labels.json: {e}")
                labels = {}

    # ← Procesar mensajes para agrupar por secciones
    processed_messages = []
    current_section = {"title": "Mensajes Generales", "fields": []}

    for key, value in messages.items():
        if key.startswith('_comment_'):
            # ← Guardar la sección anterior si tiene campos
            if current_section["fields"]:
                processed_messages.append(current_section)
            # ← Crear nueva sección
            current_section = {
                "title": value,
                "fields": []
            }
        else:
            current_section["fields"].append({
                "key": key,
                "value": value,
                "label": labels.get(key, key)  # ← Ahora `labels` está definida
            })

    # ← Agregar la última sección
    if current_section["fields"] or not processed_messages:
        processed_messages.append(current_section)

    if request.method == 'POST':
        action = request.POST.get('action')

        # --- Acción: Verificar Token ---
        if action == 'test_token':
            token = request.POST.get('TELEGRAM_BOT_TOKEN')
            if not token:
                return JsonResponse({'status': 'error', 'message': 'Token requerido.'})

            try:
                response = requests.get(f"https://api.telegram.org/bot{token}/getMe")
                data = response.json()
                if data.get('ok'):
                    user = data['result']
                    return JsonResponse({
                        'status': 'success',
                        'message': f'✅ Token válido. Bot: @{user["username"]} ({user["first_name"]})'
                    })
                else:
                    return JsonResponse({'status': 'error', 'message': f'❌ Token inválido: {data.get("description", "Desconocido")}'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'❌ Error de conexión: {str(e)}'})

        # --- Acción: Guardar Configuración ---
        elif action == 'save_config':
            try:
                # ← Guardar el token
                new_token = request.POST.get('TELEGRAM_BOT_TOKEN')
                if new_token:
                    set_key(env_path, 'TELEGRAM_BOT_TOKEN', new_token)

                # ← Guardar los mensajes
                updated_messages = {}
                for section in processed_messages:
                    for field in section['fields']:
                        key = field['key']
                        value = request.POST.get(f'message_{key}')
                        if value is not None:
                            updated_messages[key] = value

                # ← Leer el orden original del archivo
                with open(messages_file, 'r', encoding='utf-8') as f:
                    original_data = json.load(f, object_pairs_hook=OrderedDict)

                # ← Crear nuevo OrderedDict con el mismo orden
                ordered_data = OrderedDict()
                for key, value in original_data.items():
                    if key.startswith('_comment_'):
                        ordered_data[key] = value
                    else:
                        ordered_data[key] = updated_messages.get(key, value)

                # ← Escribir con el orden preservado
                with open(messages_file, 'w', encoding='utf-8') as f:
                    json.dump(ordered_data, f, ensure_ascii=False, indent=4)

                # ← Recargar variables de entorno
                load_dotenv(env_path, override=True)

                log_event('INFO', 'Configuración de Telegram actualizada desde la interfaz web.', 'config_telegram')
                return JsonResponse({'status': 'success', 'message': 'Configuración guardada.'})

            except Exception as e:
                logger.exception("Error al guardar configuración de Telegram")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return render(request, 'web_interface/config_telegram.html', {
        'telegram_token': telegram_token,
        'processed_messages': processed_messages
    })
    
    
@login_required
def monitor_telegram_view(request):
    # ← Usar 'timestamp', no 'created_at'
    logs = LogEntry.objects.filter(source='telegram_bot').order_by('-timestamp')[:100]
    return render(request, 'web_interface/monitor_telegram.html', {
        'logs': logs
    })
    
@login_required
def services_view(request):
    status = get_bot_status()
    # ← Usar .get() para evitar KeyError
    bot_running = status.get("running", False)
    start_time = status.get("start_time", None)
    auto_start = status.get("auto_start", False)  # ← Usa .get() con valor por defecto
    return render(request, 'web_interface/services.html', {
        'bot_running': bot_running,
        'start_time': start_time,
        'auto_start': auto_start
    })


def get_bot_status():
    """Devuelve el estado del bot de Telegram."""
    try:
        # ← Intenta leer el archivo de estado
        status_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'telegram_bot_status.json')
        if os.path.exists(status_file):
            with open(status_file, 'r') as f:
                status = json.load(f)
                # ← Asegurarse de que todas las claves existan
                return {
                    "running": status.get("running", False),
                    "start_time": status.get("start_time", None),
                    "auto_start": status.get("auto_start", False)  # ← Añadido
                }
        else:
            # ← Si no existe el archivo, estado por defecto
            return {
                "running": False,
                "start_time": None,
                "auto_start": False
            }
    except Exception as e:
        logger.exception("Error al leer el estado del bot")
        return {
            "running": False,
            "start_time": None,
            "auto_start": False
        }

    
    
@csrf_exempt
@login_required
def toggle_telegram(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

    try:
        data = json.loads(request.body)
        action = data.get('action')
        logger.info(f"[toggle_telegram] Acción recibida: {action}")

        if action == 'start':
            status = get_status()
            if status["telegram_running"]:
                return JsonResponse({'status': 'error', 'message': 'El bot ya está en ejecución.'})

            token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not token:
                return JsonResponse({'status': 'error', 'message': 'Falta el token del bot en .env'})

            def run_bot_safe():
                try:
                    asyncio.set_event_loop(asyncio.new_event_loop())
                    run_bot(token)
                except Exception as e:
                    logger.exception(f"Error en run_bot: {str(e)}")
                    log_event('CRITICAL', f'Error en run_bot: {str(e)}', 'services')
                finally:
                    # ← Solo marcar como detenido si el hilo termina
                    update_status(telegram_running=False, telegram_start_time=None)

            # ✅ SOLO EL BACKEND ESCRIBE EL start_time
            current_time = time.time()
            update_status(
                telegram_running=True,
                telegram_start_time=current_time,
                telegram_auto_start=status["telegram_auto_start"]
            )

            thread = threading.Thread(target=run_bot_safe, daemon=True)
            thread.start()

            log_event('INFO', 'Bot de Telegram iniciado desde la interfaz web.', 'services')
            return JsonResponse({'status': 'success', 'message': 'Bot de Telegram iniciado.'})

        elif action == 'stop':
            # ✅ SOLO EL BACKEND ACTUALIZA EL ESTADO
            update_status(telegram_running=False, telegram_start_time=None)
            log_event('INFO', 'Bot de Telegram detenido desde la interfaz web.', 'services')
            return JsonResponse({'status': 'success', 'message': 'Bot de Telegram detenido.'})

        else:
            return JsonResponse({'status': 'error', 'message': 'Acción inválida.'})
        return JsonResponse({'status': 'success', 'message': 'Acción realizada.'})
    except Exception as e:
        logger.exception("Error en toggle_telegram")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
@login_required
def set_auto_start_linux(request):
    if request.method == 'POST' and sys.platform == 'linux':
        try:
            data = json.loads(request.body)
            enable = data.get('enable', False)

            service_file = '/etc/systemd/system/tbot_telegram.service'
            project_path = os.path.dirname(os.path.dirname(__file__))
            python_path = sys.executable

            if enable:
                # ← Crear servicio systemd
                service_content = f"""
[Unit]
Description=TBot Telegram Bot
After=network.target

[Service]
Type=simple
User={os.getlogin()}
WorkingDirectory={project_path}
ExecStart={python_path} manage.py run_bot
Restart=always

[Install]
WantedBy=multi-user.target
"""
                with open('/tmp/tbot_telegram.service', 'w') as f:
                    f.write(service_content.strip())

                os.system('sudo mv /tmp/tbot_telegram.service /etc/systemd/system/')
                os.system('sudo systemctl daemon-reexec')
                os.system('sudo systemctl enable tbot_telegram.service')
                os.system('sudo systemctl start tbot_telegram.service')

                set_bot_status(get_bot_status()["running"], auto_start=True)
                return JsonResponse({'status': 'success', 'message': 'Servicio configurado para iniciar con el sistema.'})

            else:
                # ← Deshabilitar servicio
                os.system('sudo systemctl stop tbot_telegram.service')
                os.system('sudo systemctl disable tbot_telegram.service')
                set_bot_status(get_bot_status()["running"], auto_start=False)
                return JsonResponse({'status': 'success', 'message': 'Inicio automático desactivado.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Sistema no compatible o método no permitido.'}, status=400)