from datetime import datetime, timedelta
from decouple import config
import re
import logging
import os
import json
import asyncio
import threading
from pathlib import Path
from asgiref.sync import sync_to_async
from django.utils import timezone
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
)
from telegram_bot.models import Session

# Importar funciones de la base de datos y AD
from db_handler.db_handler import get_user_by_phone, delete_session
from ad_connector.ad_operations import (
    check_group_membership,
    get_password_expiry,
    cambiar_password_usuario,
    is_user_active
)
# Importar funciones de email
from email_service.email_sender import (
    notificar_cambio_contrasena_usuario,
    notificar_cambio_contrasena_admin
)

from web_interface.utils import log_event

# Ruta al archivo de mensajes
MESSAGES_FILE = Path(__file__).parent / "messages.json"

# Cargar mensajes
def load_messages():
    if MESSAGES_FILE.exists():
        with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

messages = load_messages()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados para los ConversationHandlers
GET_NEW_PASSWORD = 2
GET_PASSWORD_CONFIRMATION = 3
GET_USER_EMAIL = 10
GET_USER_NEW_PASSWORD = 11
GET_USER_PASSWORD_CONFIRMATION = 12
GET_EMAIL = 1

# Duración de la sesión en minutos
SESSION_DURATION = int(os.getenv("SESSION_DURATION", 30))

def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "¡Buenos días! 🌅"
    elif 12 <= hour < 19:
        return "¡Buenas tardes! ☀️"
    else:
        return "¡Buenas noches! 🌙"

def escape_markdown_v2(text: str) -> str:
    escape_chars = r"_*\[\]()~`>#+-=|{}.!\\"
    return re.sub(rf'([{re.escape(escape_chars)}])', r'\\\1', text)

# ---------------- Funciones de sesión ------------------
async def verify_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        user = update.effective_user
        session = await sync_to_async(Session.objects.get)(session_id=str(user.id))
        now = timezone.now()
        if now > session.last_updated:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=messages.get("session_expiry","Tu sesión ha expirado. 🙏 Por favor, autentícate nuevamente aquí: [Autenticar](https://t.me/INCA_PASS_BOT?start=start)"),
                parse_mode="Markdown"
            )
            return False
        else:
            session.last_updated = timezone.now() + timedelta(minutes=SESSION_DURATION)
            await sync_to_async(session.save)()
            return True
    except Session.DoesNotExist:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=messages.get("session_inactive","❌ No tienes una sesión activa. Por favor, inicia sesión [/start - 🚀 Iniciar Bot]"),
            parse_mode="Markdown"
        )
        return False
    except Exception as e:
        await sync_to_async(log_event)('ERROR', f"Error verificando la sesión: {str(e)}", 'telegram_bot')
        return False

async def terminate_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = str(update.effective_user.id)
        deleted_count = await delete_session(user_id)
        if deleted_count > 0:
            await sync_to_async(log_event)('INFO', f"Sesión eliminada para el usuario {user_id}", 'telegram_bot')
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=messages.get("bot_terminated","🤖 Sesión terminada. ¡Hasta pronto!")
            )
        else:
            await sync_to_async(log_event)('WARNING', f"No se encontró una sesión activa para el usuario {user_id}", 'telegram_bot')
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=messages.get("error_session_inactive","⚠️ No se encontró una sesión activa para cerrar. Si es un error, intenta autenticándote nuevamente.")
            )
    except Exception as e:
        await sync_to_async(log_event)('ERROR', f"Error terminando la sesión para el usuario {update.effective_user.id}: {str(e)}", 'telegram_bot')
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=messages.get("error_session_contact","⚠️ Hubo un error inesperado al terminar tu sesión. Por favor, contacta al administrador.")
        )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if update.effective_user.id != contact.user_id:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=messages.get("user_contact_invalid","⚠️ El contacto compartido no corresponde a tu usuario de Telegram. Inténtalo de nuevo.")
        )
        return

    raw_phone = contact.phone_number.lstrip('+')
    user_id = contact.user_id

    try:
        usuario = await get_user_by_phone(raw_phone)
        if not usuario:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=messages.get("user_not_found","❌ No se encontró el usuario en el sistema.")
            )
            return

        is_active = await sync_to_async(is_user_active)(usuario['mail'])
        if not is_active:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=messages.get("user_disabled","❌ Tu cuenta está deshabilitada en Active Directory. Contacta al administrador.")
            )
            return

        is_member = await sync_to_async(check_group_membership)(usuario['mail'])

        await sync_to_async(Session.objects.update_or_create)(
            session_id=str(user_id),
            defaults={
                'email': usuario['mail'],
                'session_data': usuario['name'],
                'created_at': timezone.now(),
                'last_updated': timezone.now() + timedelta(minutes=SESSION_DURATION)
            }
        )

        keyboard = [
            [InlineKeyboardButton("🔐 Verificar vigencia", callback_data="check_expiry"),
             InlineKeyboardButton("🔄 Cambiar contraseña 🔑", callback_data="change_password")]
        ]
        if is_member:
            keyboard += [
                [InlineKeyboardButton("🔐 Verificar a usuario 👤", callback_data="check_user_expiry"),
                 InlineKeyboardButton("🔄 Cambiar a usuario 🔑👤", callback_data="change_user_password")]
            ]
        keyboard.append([InlineKeyboardButton("❌ Terminar bot 🤖", callback_data="terminar_bot")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = messages.get("start_success","👤 : {name}\n📧 : {email}\n\n✅ Autenticación exitosa.")
        message_text = message_text.format(name=usuario['name'], email=usuario['mail'])    
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            reply_markup=reply_markup
        )

    except Exception as e:
        await sync_to_async(log_event)('ERROR', f"Error autenticando al usuario {user_id}: {str(e)}", 'telegram_bot')
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=messages.get("start_error","⚠️ Hubo un error durante la autenticación. Inténtalo de nuevo más tarde.")
        )

# --------------------- Flujo para cambiar la propia contraseña ---------------------
async def start_change_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_session(update, context):
        return ConversationHandler.END
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=messages.get("change_password_reuqest","🙏 Por favor, introduce tu nueva contraseña:")
    )
    return GET_NEW_PASSWORD

async def process_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_password = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        context.user_data['new_password'] = new_password
        await context.bot.send_message(chat_id=chat_id, text=messages.get("password_confirmation_request","🙏 Por favor, confirma tu nueva contraseña:"))
        return GET_PASSWORD_CONFIRMATION
    except Exception as e:
        await sync_to_async(log_event)('EXCEPTION', f"Error en process_new_password: {str(e)}", 'telegram_bot')
        await context.bot.send_message(chat_id=chat_id, text=messages.get("error_processing","⚠️ Ocurrió un error. Inténtalo nuevamente."))
        return ConversationHandler.END

async def process_password_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        confirmation = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        new_password = context.user_data.get('new_password')
        if not new_password:
            await context.bot.send_message(
                chat_id=chat_id,
                text=messages.get("initial_password_error", "⚠️ No se recibió la contraseña inicial. Inténtalo de nuevo.")
            )
            return ConversationHandler.END
        if new_password != confirmation:
            await context.bot.send_message(
                chat_id=chat_id,
                text=messages.get("passwords_not_match", "⚠️ Las contraseñas no coinciden. Inténtalo de nuevo.")
            )
            context.user_data.pop('new_password', None)
            await context.bot.send_message(
                chat_id=chat_id,
                text=messages.get("change_password_request", "🙏 Por favor, introduce tu nueva contraseña:")
            )
            return GET_NEW_PASSWORD
        session = await sync_to_async(Session.objects.get)(session_id=str(chat_id))
        email = session.email
        if not email:
            await context.bot.send_message(
                chat_id=chat_id,
                text=messages.get("user_email_invalid", "❌ No tienes un email asociado. Inicia sesión nuevamente.")
            )
            return ConversationHandler.END
        result = await sync_to_async(cambiar_password_usuario)(email, new_password)
        if result["success"]:
            await context.bot.send_message(
                chat_id=chat_id,
                text=messages.get("password_changed_success", "✅ La contraseña fue cambiada exitosamente.")
            )
            notificar_cambio_contrasena_usuario(email, new_password)
            admin_emails_str = config('ADMIN_EMAILS', default='')
            admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]
            if admin_emails:
                notificar_cambio_contrasena_admin(admin_emails, email)
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Error al cambiar contraseña: {result['message']}"
            )
            return ConversationHandler.END
    except Exception as e:
        await sync_to_async(log_event)('ERROR', f"Error en process_password_confirmation: {str(e)}", 'telegram_bot')
        await context.bot.send_message(
            chat_id=chat_id,
            text=messages.get("error_processing", "⚠️ Ocurrió un error. Inténtalo nuevamente.")
        )
        context.user_data.clear()
        return ConversationHandler.END
    
# ----------------- Flujo para cambiar la contraseña de otro usuario (administrador) -----------------
async def start_change_user_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_session(update, context):
        return ConversationHandler.END
    try:
        user = update.effective_user
        session = await sync_to_async(Session.objects.get)(session_id=str(user.id))
        if not await sync_to_async(check_group_membership)(session.email):
            await context.bot.send_message(chat_id=update.effective_chat.id, text=messages.get("invalid_access", "❌ Acceso restringido: Solo para administradores."))
            return ConversationHandler.END
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=messages.get("internal_error","❌ Error interno. Contacte al administrador."))
        return ConversationHandler.END
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=messages.get("admin_password_email_request","🙏 Por favor, introduce el email del usuario al que deseas cambiar la contraseña:")
    )
    return GET_USER_EMAIL

async def process_user_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_email = update.message.text.strip().lower()
        chat_id = update.message.chat_id
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", target_email):
            await context.bot.send_message(chat_id=chat_id, text=messages.get("user_email_invalid","❌ El formato del email no es válido. Inténtalo de nuevo:"))
            return GET_USER_EMAIL
        context.user_data['target_email'] = target_email
        await context.bot.send_message(
            chat_id=chat_id,
            text=messages.get(
                "change_password_request",
                f"🔍 Se procederá a cambiar la contraseña para {target_email}. 🙏 Por favor, introduce la nueva contraseña:"
            )
        )
        return GET_USER_NEW_PASSWORD
    except Exception as e:
        await sync_to_async(log_event)('EXCEPTION', f"Error en process_user_email: {str(e)}", 'telegram_bot')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=messages.get("error_processing","⚠️ Ocurrió un error. Inténtalo nuevamente."))
        return ConversationHandler.END

async def process_user_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_password = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        context.user_data['target_new_password'] = new_password
        await context.bot.send_message(chat_id=chat_id, text=messages.get("change_password_reuqest","🙏 Por favor, confirma la nueva contraseña:"))
        return GET_USER_PASSWORD_CONFIRMATION
    except Exception as e:
        await sync_to_async(log_event)('EXCEPTION', f"Error en process_user_new_password: {str(e)}", 'telegram_bot')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=messages.get("error_processing","⚠️ Ocurrió un error. Inténtalo nuevamente."))
        return ConversationHandler.END

async def process_user_password_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        confirmation = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        new_password = context.user_data.get('target_new_password')
        target_email = context.user_data.get('target_email')
        if not new_password or not target_email:
            await context.bot.send_message(chat_id=chat_id, text=messages.get("data_error","⚠️ Datos insuficientes. Inténtalo de nuevo."))
            return ConversationHandler.END
        if new_password != confirmation:
            await context.bot.send_message(chat_id=chat_id, text=messages.get("password_not_match","⚠️ Las contraseñas no coinciden. Inténtalo de nuevo."))
            return ConversationHandler.END
        result = await sync_to_async(cambiar_password_usuario)(target_email, new_password)
        if result["success"]:
            await context.bot.send_message(chat_id=chat_id,
                                           text=messages.get("admin_password_changed","✅ La contraseña fue cambiada exitosamente para el usuario."))
            notificar_cambio_contrasena_usuario(target_email, new_password)
            admin_emails_str = config('ADMIN_EMAILS', default='')
            admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]
            await sync_to_async(log_event)('INFO', f"Emails de administradores leídos: {admin_emails}", 'telegram_bot')
            if admin_emails:
                notificar_cambio_contrasena_admin(admin_emails, target_email)
        else:
            await context.bot.send_message(chat_id=chat_id, text=messages.get(f"general_error",f"⚠️ Error: {result['message']}"))
    except Exception as e:
        await sync_to_async(log_event)('EXCEPTION', f"Error en process_user_password_confirmation: {str(e)}", 'telegram_bot')
        await context.bot.send_message(chat_id=chat_id, text=messages.get("password_confirmation_error","⚠️ Ocurrió un error al procesar la confirmación."))
    finally:
        context.user_data.clear()
        return ConversationHandler.END

# ----------------- Otros flujos -----------------
async def check_user_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_session(update, context):
        return
    try:
        query = update.callback_query
        await query.answer()
        await sync_to_async(log_event)('INFO', "Inicio de check_user_expiry", 'telegram_bot')
        session = await sync_to_async(Session.objects.get)(session_id=str(query.from_user.id))
        await sync_to_async(log_event)('DEBUG', f"Sesión obtenida: {session.session_id}", 'telegram_bot')
        if not await sync_to_async(check_group_membership)(session.email):
            await sync_to_async(log_event)('WARNING', "Intento de acceso no autorizado", 'telegram_bot')
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=messages.get("error_access","❌ Acceso restringido: Solo para administradores")
            )
            return ConversationHandler.END
        await sync_to_async(log_event)('INFO', "Solicitando email completo para verificación de vigencia de otro usuario", 'telegram_bot')
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=messages.get("admin_password_fullemail_request","🙏 Por favor, introduce el email completo del usuario:"),
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_EMAIL
    except Exception as e:
        await sync_to_async(log_event)('EXCEPTION', f"Error en check_user_expiry: {str(e)}", 'telegram_bot')
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=messages.get("internal_error","⚠️ Error interno. Contacte al administrador.")
        )
        return ConversationHandler.END

async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_session(update, context):
        return ConversationHandler.END
    try:
        if not update.message or not update.message.text:
            await sync_to_async(log_event)('DEBUG', "No se recibió mensaje de texto en process_email", 'telegram_bot')
            await update.message.reply_text("🙏 Por favor, introduce un email válido.")
            return GET_EMAIL
        email = update.message.text.strip().lower()
        await sync_to_async(log_event)('DEBUG', f"Email recibido: {email}", 'telegram_bot')
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            await update.message.reply_text("❌ El formato del email no es válido. Inténtalo de nuevo:")
            return GET_EMAIL
        await update.message.reply_text(f"🔍 Procesando vigencia de la contraseña para el email: {email}")
        try:
            expiry_info = await sync_to_async(get_password_expiry, thread_sensitive=True)(email)
            await sync_to_async(log_event)('DEBUG', f"Resultado obtenido de get_password_expiry: {expiry_info}", 'telegram_bot')
        except Exception as e_inner:
            await sync_to_async(log_event)('ERROR', f"Error en consulta a AD: {str(e_inner)}", 'telegram_bot')
            await update.message.reply_text("⚠️ Error al verificar la vigencia del email. Intenta nuevamente más tarde.")
            return ConversationHandler.END
        if expiry_info['is_expired']:
            response = (f"🔴 CONTRASEÑA EXPIRADA\n" f"📧 Email: {email}\n" f"🗓️ Expiró hace {-expiry_info['days_remaining']} días")
        else:
            response = (f"🟢 CONTRASEÑA VIGENTE\n" f"📧 Email: {email}\n" f"🗓️ Expira: {expiry_info.get('expiry_date', 'N/A')}\n" f"⌛ Días restantes: {expiry_info.get('days_remaining', 'N/A')}")
        await sync_to_async(log_event)('INFO', f"Enviando respuesta al usuario: {response}", 'telegram_bot')
        response_escaped = escape_markdown_v2(response)
        await update.message.reply_text(response_escaped, parse_mode="MarkdownV2")
    except Exception as e:
        await sync_to_async(log_event)('EXCEPTION', f"Error crítico en process_email: {str(e)}", 'telegram_bot')
        await update.message.reply_text("⚠️ Error procesando solicitud.")
    finally:
        context.user_data.clear()
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Operación cancelada", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def check_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_session(update, context):
        return
    try:
        query = update.callback_query
        await query.answer()
        user = update.effective_user
        session = await sync_to_async(Session.objects.get)(session_id=str(user.id))
        email = session.email
        if not email:
            raise ValueError("📧 Email no registrado en sesión")
        expiry_info = await sync_to_async(get_password_expiry)(email)
        if expiry_info['error']:
            raise Exception(expiry_info['error'])
        if expiry_info['is_expired']:
            message = (f"🔴 CONTRASEÑA EXPIRADA\n" f"📧 Email: {email}\n" f"🗓️ Expiró hace {-expiry_info['days_remaining']} días")
        else:
            message = (f"🟢 CONTRASEÑA VIGENTE\n" f"📧 Email: {email}\n" f"🗓️ Expira: {expiry_info['expiry_date']}\n" f"⌛ Días restantes: {expiry_info['days_remaining']}")
        await context.bot.send_message(chat_id=query.message.chat_id, text=escape_markdown_v2(message), parse_mode='MarkdownV2')
    except Exception as e:
        await sync_to_async(log_event)('ERROR', f"Error en check_expiry: {str(e)}", 'telegram_bot')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=messages.get(f"error_verifiying2", f"⚠️ Error al verificar: {str(e)}"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session_exists = await sync_to_async(Session.objects.filter(session_id=str(user.id)).exists)()
    if session_exists:
        await sync_to_async(Session.objects.filter(session_id=str(user.id)).delete)()
        await sync_to_async(log_event)('INFO', f"Sesión previa eliminada para el usuario {user.id}", 'telegram_bot')
    greeting = get_greeting()
    contexts = {
        'g_greeting': greeting,
        'user_first_name': user.first_name
    }
    message_template = messages.get("start_session", "{g_greeting} {user_first_name}! 👋\n\nPara continuar, 🙏 comparte tu número de contacto:")
    message_text = message_template.format_map(contexts)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message_text,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Compartir contacto 📱", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    if action == "check_expiry":
        await check_expiry(update, context)
    elif action == "check_user_expiry":
        await check_user_expiry(update, context)
    elif action == "change_password":
        return
    elif action == "exit_bot":
        await terminate_bot(update, context)

async def run_bot(token: str, stop_event: threading.Event = None):
    """Inicia la aplicación del bot de Telegram."""
    application = None

    try:
        # ← Crear la aplicación
        application = ApplicationBuilder().token(token).build()

        # ← Añadir handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
        application.add_handler(CommandHandler('terminar_bot', terminate_bot))

        conv_handler_change = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_change_password, pattern='^change_password$')],
            states={
                GET_NEW_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_password)],
                GET_PASSWORD_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_password_confirmation)]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(conv_handler_change)

        conv_handler_change_user = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_change_user_password, pattern='^change_user_password$')],
            states={
                GET_USER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_email)],
                GET_USER_NEW_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_new_password)],
                GET_USER_PASSWORD_CONFIRMATION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_password_confirmation)]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(conv_handler_change_user)

        conv_handler_verify = ConversationHandler(
            entry_points=[CallbackQueryHandler(check_user_expiry, pattern='^check_user_expiry$')],
            states={GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)]},
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(conv_handler_verify)

        application.add_handler(CallbackQueryHandler(check_expiry, pattern='^check_expiry$'))
        application.add_handler(CallbackQueryHandler(terminate_bot, pattern='^terminar_bot$'))

        # ← Función asíncrona que ejecuta el bot
        async def run():
            # ← Inicializar y empezar el bot
            await application.initialize()
            await application.start()

            # ← Iniciar el polling
            await application.updater.start_polling()

            # ← Esperar a que se detenga
            if stop_event:
                while not stop_event.is_set():
                    await asyncio.sleep(1)
                await sync_to_async(log_event)('INFO', 'Señal de detención recibida. Deteniendo el bot...', 'telegram_bot')

            # ← Detener el updater (esto detendrá run_polling)
            await application.updater.stop()

            # ← Detener la aplicación
            await application.stop()

            await sync_to_async(log_event)('INFO', 'Bot de Telegram detenido correctamente.', 'telegram_bot')

        # ← Ejecutar el bot
        await run()

    except Exception as e:
        await sync_to_async(log_event)('CRITICAL', f'Error al iniciar run_polling: {str(e)}', 'telegram_bot')
        raise
    finally:
        # ← Actualizar estado
        try:
            from web_interface.views import update_status
            update_status(telegram_running=False, telegram_start_time=None)
        except Exception as e:
            await sync_to_async(log_event)('ERROR', f'Error al actualizar estado: {str(e)}', 'telegram_bot')

# ← Función síncrona para iniciar el bot en un hilo
def run_bot_sync(token: str, stop_event: threading.Event = None):
    """Función síncrona que ejecuta run_bot en un loop asyncio."""
    # ← Crear un nuevo event loop para este hilo
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot(token, stop_event))
    finally:
        loop.close()
        
def run_bot_sync(token: str, stop_event: threading.Event = None):
    """Función síncrona que ejecuta run_bot en un loop asyncio."""
    # ← Crear un nuevo event loop para este hilo
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot(token, stop_event))
    finally:
        loop.close()