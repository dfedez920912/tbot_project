import os
import json
import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.paginator import Paginator
from dotenv import dotenv_values, set_key

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

# Importaciones locales
from .models import LogEntry, AppSetting
from .utils import log_event

logger = logging.getLogger(__name__)

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
    return render(request, 'web_interface/dashboard.html')


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