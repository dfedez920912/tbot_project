from django.core.management.base import BaseCommand
import os
import ssl
import logging
from ldap3 import Server, Connection, Tls, SUBTREE
from ldap3.core.exceptions import LDAPException, LDAPBindError
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_ad_config():
    return {
        'host': os.getenv('AD_SERVER'),
        'port': int(os.getenv('AD_PORT')),
        'use_ssl': os.getenv('AD_USE_SSL', 'false').lower() == 'true',
        'user': os.getenv('AD_USER'),
        'password': os.getenv('AD_PASSWORD'),
        'search_base': os.getenv('AD_SEARCH_BASE'),
        'tls_config': Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
    }


class Command(BaseCommand):
    help = 'Notifica a usuarios sobre la expiración de sus contraseñas'

    def send_mail(self, to, subject, message):
        msg = MIMEMultipart()
        msg['From'] = os.getenv('EMAIL_SENDER')
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'html', 'utf-8'))

        try:
            with smtplib.SMTP(os.getenv('EMAIL_HOST'), int(os.getenv('EMAIL_PORT'))) as server:
                if os.getenv('EMAIL_USE_TLS', 'False').lower() == 'true':
                    server.starttls()
                if os.getenv('EMAIL_HOST_USER') and os.getenv('EMAIL_HOST_PASSWORD'):
                    server.login(os.getenv('EMAIL_HOST_USER'), os.getenv('EMAIL_HOST_PASSWORD'))
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Error enviando email a {to}: {str(e)}")
            return False

    def handle(self, *args, **options):
        try:
            config = get_ad_config()
            days_to_notify = 30  # días antes para empezar a notificar
            policy_days = int(os.getenv('AD_PASSWORD_POLICY_DAYS', '90'))

            body_template = """
            Estimado usuario:

            El departamento de Informática y comunicaciones le informa que su cuenta expirará dentro de %s día(s).

            Ante cualquier tipo de duda durante el proceso de cambio de la contraseña o ante algún correo de dudosa procedencia, 
            comuníquese con nosotros.

            Por favor cambie su contraseña lo antes posible. Recuerde que es usted el máximo responsable de velar por 
            la disponibilidad de su cuenta.

            Puede cambiar la contraseña desde los servicios disponibles:
            1 - Sitio web: %s
            2 - Bot de telegram: %s

            Atentamente,
            Departamento de Informática y comunicaciones.
            """ % ("%s", os.getenv('PASSWORD_CHANGE_URL'), os.getenv('TELEGRAM_BOT_URL'))

            footer = """
            <br><br>
            Departamento de Informática y comunicaciones<br>
            %s<br>
            %s<br>
            Email: %s<br>
            Telf: %s
            """ % (
                os.getenv('INSTITUTION_NAME'),
                os.getenv('INSTITUTION_ADDRESS'),
                os.getenv('ADMIN_EMAILS').split(',')[0],
                os.getenv('INSTITUTION_PHONE')
            )

            # Configurar servidor LDAP
            server = Server(
                host=config['host'],
                port=config['port'],
                use_ssl=config['use_ssl'],
                tls=config['tls_config']
            )

            with Connection(
                    server,
                    user=config['user'],
                    password=config['password'],
                    auto_bind=True
            ) as conn:

                search_filter = '(&(objectClass=user)(objectCategory=person)(mail=*))'

                conn.search(
                    search_base=config['search_base'],
                    search_filter=search_filter,
                    attributes=['mail', 'pwdLastSet', 'userAccountControl']
                )

                notified_users = []
                count = 0

                for entry in conn.entries:
                    try:
                        if not entry.pwdLastSet.value or not entry.userAccountControl.value:
                            continue

                        # Ya que pwdLastSet viene como datetime, lo usamos directamente
                        last_set_date = entry.pwdLastSet.value
                        if isinstance(last_set_date, str):
                            last_set_date = datetime.fromisoformat(last_set_date.replace('Z', '+00:00'))

                        # Calcular fecha de expiración
                        expiry_date = last_set_date + timedelta(days=policy_days)
                        days_remaining = (expiry_date - datetime.now(expiry_date.tzinfo)).days

                        # Verificar cuenta activa y necesidad de notificación
                        if (int(entry.userAccountControl.value) == 512 and
                                0 < days_remaining <= days_to_notify):

                            email = str(entry.mail.value)
                            message = body_template % days_remaining + footer

                            if self.send_mail(
                                    email,
                                    "Atención Usuario: Notificación de expiración de su contraseña",
                                    message
                            ):
                                notified_users.append(f"{email} - {days_remaining} días restantes")
                                count += 1
                                logger.info(f"Notificación enviada a {email} (expira en {days_remaining} días)")

                    except Exception as e:
                        logger.error(f"Error procesando usuario: {str(e)}")
                        logger.error(f"Valores del usuario: pwdLastSet={entry.pwdLastSet.value}, "
                                     f"userAccountControl={entry.userAccountControl.value}")
                        continue

                if notified_users:
                    summary = "Listado de usuarios notificados ({}):\n\n{}".format(
                        count, '\n'.join(notified_users)
                    )
                    for admin_email in os.getenv('ADMIN_EMAILS').split(','):
                        self.send_mail(
                            admin_email.strip(),
                            f"Usuarios con contraseña próxima a expirar: {count}",
                            summary
                        )

                self.stdout.write(
                    self.style.SUCCESS(f'Notificación completada. {count} usuarios notificados.')
                )

        except (LDAPBindError, LDAPException) as e:
            logger.error(f"Error LDAP: {str(e)}")
            self.stdout.write(self.style.ERROR(f'Error en la conexión LDAP: {str(e)}'))
        except Exception as e:
            logger.error(f"Error inesperado: {str(e)}")
            self.stdout.write(self.style.ERROR(f'Error inesperado: {str(e)}'))