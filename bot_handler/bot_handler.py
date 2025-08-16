from datetime import datetime, timedelta
from decouple import config
import re
import logging
import os
import asyncio
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

def handle_password_change(user_id, username):
    try:
        # ... lógica de cambio de contraseña
        log_event(
            level='INFO',
            message=f"Usuario {user_id} solicitó cambio de contraseña para {username}",
            source='bot_handler'
        )
        return True
    except Exception as e:
        log_event(
            level='ERROR',
            message=f"Error al cambiar contraseña para {username}: {str(e)}",
            source='bot_handler'
        )
        return False

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados para los ConversationHandlers
# Flujo para cambiar la propia contraseña
GET_NEW_PASSWORD = 2
GET_PASSWORD_CONFIRMATION = 3
# Flujo para cambiar la contraseña de otro usuario (administrador)
GET_USER_EMAIL = 10
GET_USER_NEW_PASSWORD = 11
GET_USER_PASSWORD_CONFIRMATION = 12
# Flujo para verificar vigencia de otro usuario
GET_EMAIL = 1

# Duración de la sesión en minutos (definida en .env, por defecto 30)
SESSION_DURATION = int(os.getenv("SESSION_DURATION"))

def get_greeting():
    """Devuelve el saludo según la hora actual."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "¡Buenos días! 🌅"
    elif 12 <= hour < 19:
        return "¡Buenas tardes! ☀️"
    else:
        return "¡Buenas noches! 🌙"

# -------------------- Función: escape_markdown_v2 ----------------------- #
def escape_markdown_v2(text: str) -> str:
    """Escapa caracteres según la especificación de Markdown V2 para Telegram."""
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
                text="Tu sesión ha expirado. 🙏 Por favor, autentícate nuevamente aquí: [Autenticar](https://t.me/<TU_NOMBRE_DE_USUARIO_DEL_BOT>?start=start)",
                parse_mode="Markdown"
            )
            return False
        else:
            # Actualizar el campo `last_updated` si la sesión sigue activa
            session.last_updated = timezone.now() + timedelta(minutes=SESSION_DURATION)
            await sync_to_async(session.save)()
            return True
    except Session.DoesNotExist:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ No tienes una sesión activa.\n"
                 " Por favor, inicia sesión \n"
                 "[/start - 🚀 Iniciar Bot]",
            parse_mode="Markdown"
        )
        return False
    except Exception as e:
        logger.error("Error verificando la sesión: %s", e)
        return False

async def terminate_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cierra la sesión del usuario y elimina el registro."""
    try:
        user_id = str(update.effective_user.id)

        # Llamar directamente a la función asíncrona delete_session
        deleted_count = await delete_session(user_id)

        if deleted_count > 0:
            logger.info(f"Sesión eliminada para el usuario {user_id}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🤖 Bot cerrado. ¡Hasta luego!"
            )
        else:
            logger.warning(f"No se encontró una sesión activa para el usuario {user_id}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ No se encontró una sesión activa para cerrar. Si es un error, intenta autenticándote nuevamente."
            )

    except Exception as e:
        logger.error(f"Error terminando la sesión para el usuario {update.effective_user.id}: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Hubo un error inesperado al terminar tu sesión. Por favor, contacta al administrador."
        )

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Valida el contacto del usuario, verifica AD y crea la sesión."""
    contact = update.message.contact

    # Validar que el contacto corresponde al usuario
    if update.effective_user.id != contact.user_id:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ El contacto compartido no corresponde a tu usuario de Telegram. Inténtalo de nuevo."
        )
        return

    raw_phone = contact.phone_number.lstrip('+')
    user_id = contact.user_id

    try:
        # Buscar usuario por teléfono en la base de datos
        usuario = await get_user_by_phone(raw_phone)
        if not usuario:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ No se encontró el usuario en el sistema."
            )
            return

        # Verificar si el usuario está activo en AD
        is_active = await sync_to_async(is_user_active)(usuario['mail'])
        if not is_active:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Tu cuenta está deshabilitada en Active Directory. Contacta al administrador."
            )
            return

        # Verificar si el usuario pertenece al grupo permitido
        is_member = await sync_to_async(check_group_membership)(usuario['mail'])

        # Crear la sesión después de todas las verificaciones exitosas
        await sync_to_async(Session.objects.update_or_create)(
            session_id=str(user_id),
            defaults={
                'email': usuario['mail'],
                'session_data': usuario['name'],
                'created_at': timezone.now(),
                'last_updated': timezone.now() + timedelta(minutes=SESSION_DURATION)
            }
        )

        # Construir las botoneras y enviarlas al usuario
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

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"👤 : {usuario['name']}\n📧 : {usuario['mail']}\n\n✅ Autenticación exitosa.",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error autenticando al usuario {user_id}: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Hubo un error durante la autenticación. Inténtalo de nuevo más tarde."
        )

# --------------------- Flujo para cambiar la propia contraseña ---------------------
async def start_change_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_session(update, context):
        return ConversationHandler.END
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🙏 Por favor, introduce tu nueva contraseña:"
    )
    return GET_NEW_PASSWORD

async def process_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_password = update.message.text.strip()
        chat_id = update.message.chat_id
        # Borrar el mensaje con la nueva contraseña del usuario (para no dejar datos sensibles)
        await update.message.delete()
        context.user_data['new_password'] = new_password
        await context.bot.send_message(chat_id=chat_id, text="🙏 Por favor, confirma tu nueva contraseña:")
        return GET_PASSWORD_CONFIRMATION
    except Exception as e:
        logger.exception("Error en process_new_password: %s", e)
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Ocurrió un error. Inténtalo nuevamente.")
        return ConversationHandler.END

async def process_password_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        confirmation = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        new_password = context.user_data.get('new_password')
        if not new_password:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ No se recibió la contraseña inicial. Inténtalo de nuevo.")
            return ConversationHandler.END
        if new_password != confirmation:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Las contraseñas no coinciden. Inténtalo de nuevo.")
            return ConversationHandler.END

        user = update.effective_user
        session = await sync_to_async(Session.objects.get)(session_id=str(user.id))
        email = session.email
        if not email:
            await context.bot.send_message(chat_id=chat_id, text="❌ No se encontró email asociado a tu sesión.")
            return ConversationHandler.END

        result = await sync_to_async(cambiar_password_usuario)(email, new_password)
        if result["success"]:
            await context.bot.send_message(chat_id=chat_id, text="✅ La contraseña fue cambiada exitosamente.")
            # Notificar vía email al usuario.
            notificar_cambio_contrasena_usuario(email, new_password)

            # Notificar a los administradores sin incluir la contraseña.
            admin_emails_str = config('ADMIN_EMAILS', default='')
            admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]
            logger.info(f"Emails de administradores leídos: {admin_emails}")
            if admin_emails:
                notificar_cambio_contrasena_admin(admin_emails, email)
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {result['message']}")
    except Exception as e:
        logger.exception("Error en process_password_confirmation: %s", e)
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Ocurrió un error al procesar la confirmación.")
    finally:
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
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Acceso restringido: Solo para administradores.")
            return ConversationHandler.END
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Error interno. Contacte al administrador.")
        return ConversationHandler.END
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🙏 Por favor, introduce el email del usuario al que deseas cambiar la contraseña:"
    )
    return GET_USER_EMAIL

async def process_user_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_email = update.message.text.strip().lower()
        chat_id = update.message.chat_id
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", target_email):
            await context.bot.send_message(chat_id=chat_id, text="❌ El formato del email no es válido. Inténtalo de nuevo:")
            return GET_USER_EMAIL
        context.user_data['target_email'] = target_email
        await context.bot.send_message(chat_id=chat_id, text=f"🔍 Se procederá a cambiar la contraseña para {target_email}.🙏 Por favor, introduce la nueva contraseña:")
        return GET_USER_NEW_PASSWORD
    except Exception as e:
        logger.exception("Error en process_user_email: %s", e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ Ocurrió un error. Inténtalo nuevamente.")
        return ConversationHandler.END

async def process_user_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_password = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        context.user_data['target_new_password'] = new_password
        await context.bot.send_message(chat_id=chat_id, text="🙏 Por favor, confirma la nueva contraseña:")
        return GET_USER_PASSWORD_CONFIRMATION
    except Exception as e:
        logger.exception("Error en process_user_new_password: %s", e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ Ocurrió un error. Inténtalo nuevamente.")
        return ConversationHandler.END

async def process_user_password_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        confirmation = update.message.text.strip()
        chat_id = update.message.chat_id
        await update.message.delete()
        new_password = context.user_data.get('target_new_password')
        target_email = context.user_data.get('target_email')
        if not new_password or not target_email:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Datos insuficientes. Inténtalo de nuevo.")
            return ConversationHandler.END
        if new_password != confirmation:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Las contraseñas no coinciden. Inténtalo de nuevo.")
            return ConversationHandler.END
        result = await sync_to_async(cambiar_password_usuario)(target_email, new_password)
        if result["success"]:
            await context.bot.send_message(chat_id=chat_id,
                                           text="✅ La contraseña fue cambiada exitosamente para el usuario.")
            # Notificar al usuario afectado.
            notificar_cambio_contrasena_usuario(target_email, new_password)
            # Notificar a los administradores.
            admin_emails_str = config('ADMIN_EMAILS', default='')
            admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]
            logger.info(f"Emails de administradores leídos: {admin_emails}")
            if admin_emails:
                notificar_cambio_contrasena_admin(admin_emails, target_email)
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {result['message']}")
    except Exception as e:
        logger.exception("Error en process_user_password_confirmation: %s", e)
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Ocurrió un error al procesar la confirmación.")
    finally:
        context.user_data.clear()
        return ConversationHandler.END


# ----------------- Otros flujos (handle_contact, check_expiry, check_user_expiry, process_email) -----------------
async def check_user_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Inicia el flujo para verificar la vigencia de otro usuario.
    Se solicita el email completo y se procesa con la misma estructura que para el propio usuario.
    """
    if not await verify_session(update, context):
        return

    try:
        query = update.callback_query
        await query.answer()
        logger.info("Inicio de check_user_expiry")

        session = await sync_to_async(Session.objects.get)(session_id=str(query.from_user.id))
        logger.debug(f"Sesión obtenida: {session.session_id}")
        if not await sync_to_async(check_group_membership)(session.email):
            logger.warning("Intento de acceso no autorizado")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Acceso restringido: Solo para administradores"
            )
            return ConversationHandler.END

        logger.info("Solicitando email completo para verificación de vigencia de otro usuario")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🙏 Por favor, introduce el email completo del usuario:",
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_EMAIL

    except Exception as e:
        logger.exception("Error en check_user_expiry:")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚠️ Error interno. Contacte al administrador."
        )
        return ConversationHandler.END

async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recibe el email ingresado y lo envía a get_password_expiry.
    La respuesta se construye con la misma estructura que en la verificación del propio usuario.
    """
    if not await verify_session(update, context):
        return ConversationHandler.END

    try:
        if not update.message or not update.message.text:
            logger.debug("No se recibió mensaje de texto en process_email")
            await update.message.reply_text("🙏 Por favor, introduce un email válido.")
            return GET_EMAIL

        email = update.message.text.strip().lower()
        logger.debug("Email recibido: %s", email)

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            await update.message.reply_text("❌ El formato del email no es válido. Inténtalo de nuevo:")
            return GET_EMAIL

        await update.message.reply_text(
            f"🔍 Procesando vigencia de la contraseña para el email: {email}"
        )

        try:
            expiry_info = await sync_to_async(get_password_expiry, thread_sensitive=True)(email)
            logger.debug("Resultado obtenido de get_password_expiry: %s", expiry_info)
        except Exception as e_inner:
            logger.error("Error en consulta a AD: %s", str(e_inner))
            await update.message.reply_text(
                "⚠️ Error al verificar la vigencia del email. Intenta nuevamente más tarde."
            )
            return ConversationHandler.END

        if expiry_info['is_expired']:
            response = (
                f"🔴 CONTRASEÑA EXPIRADA\n"
                f"📧 Email: {email}\n"
                f"🗓️ Expiró hace {-expiry_info['days_remaining']} días"
            )
        else:
            response = (
                f"🟢 CONTRASEÑA VIGENTE\n"
                f"📧 Email: {email}\n"
                f"🗓️ Expira: {expiry_info.get('expiry_date', 'N/A')}\n"
                f"⌛ Días restantes: {expiry_info.get('days_remaining', 'N/A')}"
            )

        logger.info("Enviando respuesta al usuario: %s", response)
        response_escaped = escape_markdown_v2(response)
        await update.message.reply_text(response_escaped, parse_mode="MarkdownV2")

    except Exception as e:
        logger.exception("Error crítico en process_email:")
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
            message = (f"🔴 CONTRASEÑA EXPIRADA\n"
                       f"📧 Email: {email}\n"
                       f"🗓️ Expiró hace {-expiry_info['days_remaining']} días")
        else:
            message = (f"🟢 CONTRASEÑA VIGENTE\n"
                       f"📧 Email: {email}\n"
                       f"🗓️ Expira: {expiry_info['expiry_date']}\n"
                       f"⌛ Días restantes: {expiry_info['days_remaining']}")
        await context.bot.send_message(chat_id=query.message.chat_id, text=escape_markdown_v2(message), parse_mode='MarkdownV2')
    except Exception as e:
        logger.error("Error en check_expiry: %s", e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ Error al verificar: {str(e)}")



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start y autentica al usuario."""
    user = update.effective_user
    session_exists = await sync_to_async(Session.objects.filter(session_id=str(user.id)).exists)()

    # Si ya hay una sesión activa, asegúrate de eliminarla o manejarla correctamente
    if session_exists:
        await sync_to_async(Session.objects.filter(session_id=str(user.id)).delete)()
        logger.info(f"Sesión previa eliminada para el usuario {user.id}")

    # Solicitar al usuario compartir su contacto
    greeting = get_greeting()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{greeting} {user.first_name}! 👋\n\n"
             "Para continuar, 🙏 comparte tu número de contacto:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Compartir contacto 📱", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestiona las acciones de los botones inline."""
    query = update.callback_query
    await query.answer()

    action = query.data
    if action == "check_expiry":
        await check_expiry(update, context)
    elif action == "check_user_expiry":
        await check_user_expiry(update, context)
    elif action == "change_password":
        # El ConversationHandler de cambio de contraseña captará este callback.
        return
    elif action == "exit_bot":
        await terminate_bot(update, context)
    # Otros callbacks (p.ej.: "change_user_password") se podrían configurar de forma similar.


def run_bot(token: str):
    application = ApplicationBuilder().token(token).build()

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

    # Agregar un handler para check_expiry: este se activa cuando se pulsa el botón "check_expiry"
    application.add_handler(CallbackQueryHandler(check_expiry, pattern='^check_expiry$'))
    # Luego, registra el handler para "exit_bot"
    application.add_handler(CallbackQueryHandler(terminate_bot, pattern='^terminar_bot$'))
    application.run_polling()


if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_token_here")
    run_bot(TOKEN)
