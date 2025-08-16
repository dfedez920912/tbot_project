# email_service/email_sender.py

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from decouple import config
import logging
from web_interface.utils import log_event


def send_password_reset_email(email: str, token: str):
    try:
        # ... lógica de envío de correo
        log_event(
            level='INFO',
            message=f"Correo de restablecimiento enviado a {email}",
            source='email_service'
        )
    except Exception as e:
        log_event(
            level='ERROR',
            message=f"Fallo al enviar correo a {email}: {str(e)}",
            source='email_service'
        )


logger = logging.getLogger(__name__)

def enviar_correo(destinatarios, asunto, cuerpo_html):
    try:
        # Configuración del servidor SMTP
        smtp_host = config('EMAIL_HOST')
        smtp_port = config('EMAIL_PORT', cast=int)
        smtp_user = config('EMAIL_HOST_USER')
        smtp_pass = config('EMAIL_HOST_PASSWORD')
        email_sender = config('EMAIL_SENDER')

        # Crear el mensaje
        msg = MIMEMultipart()
        msg['From'] = email_sender
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = asunto

        # Cuerpo del mensaje
        msg.attach(MIMEText(cuerpo_html, 'html'))

        # Enviar el correo
        with smtplib.SMTP(host=smtp_host, port=smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_sender, destinatarios, msg.as_string())

        logger.info(f"Correo enviado a: {', '.join(destinatarios)}")
    except Exception as e:
        logger.error(f"Error al enviar el correo: {e}")

def notificar_cambio_contrasena_usuario(destinatario, nueva_contrasena):
    asunto = 'Notificación de cambio de contraseña'
    cuerpo_html = f"""
    <html>
    <body>
        <h2>Notificación de cambio de contraseña</h2>
        <p>Hola,</p>
        <p>Se ha cambiado la contraseña de tu cuenta mediante el <a href="https://t.me/INCA_PASS_BOT">Bot de Telegram</a>.</p>
        <p><strong>Nueva contraseña:</strong> {nueva_contrasena}</p>
        <p>Si no ha realizando usted este cambio, por favor contacta a Administracion de redes INCA inmediatamente (Yuniel, Daniel o Idariel).</p>
        <p>Saludos,<br>Departamento de Informática y comunicaciones</p>
    </body>
    </html>
    """
    enviar_correo([destinatario], asunto, cuerpo_html)

def notificar_cambio_contrasena_admin(admin_emails, usuario_email):
    """
    Envía una notificación a los administradores indicando que el usuario con correo usuario_email
    ha cambiado su contraseña; NO se incluye la contraseña.
    """
    asunto = 'Notificación de cambio de contraseña'
    cuerpo_html = f"""
    <html>
    <body>
        <h2>Notificación de cambio de contraseña</h2>
        <p>Hola,</p>
        <p>El usuario con correo <strong>{usuario_email}</strong> ha cambiado su contraseña utilizando el bot de Telegram.</p>
        <p>Saludos,<br>Equipo de Soporte</p>
    </body>
    </html>
    """
    enviar_correo(admin_emails, asunto, cuerpo_html)

