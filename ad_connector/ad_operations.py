# ad_connector/ad_operations.py
import os
import ssl
import logging
import time
from ldap3 import Server, Connection, Tls, SUBTREE, MODIFY_REPLACE
from ldap3.core.exceptions import LDAPException, LDAPBindError
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from web_interface.utils import log_event

def authenticate_user(username: str, password: str) -> bool:
    try:
        # ... autenticación contra AD
        success = True  # resultado real
        log_event(
            level='INFO' if success else 'WARNING',
            message=f"{'Éxito' if success else 'Fallo'} al autenticar a {username} en AD",
            source='ad_connector'
        )
        return success
    except Exception as e:
        log_event(
            level='ERROR',
            message=f"Error de conexión con AD para {username}: {str(e)}",
            source='ad_connector'
        )
        return False

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


def cambiar_password_usuario(email: str, new_password: str) -> dict:
    """
    Cambia la contraseña para el usuario identificado por su email.
    Se busca el DN del usuario mediante el filtro basado en el campo 'mail'.
    Si se encuentra el usuario, se intenta cambiar la contraseña (atributo 'unicodePwd')
    utilizando una conexión segura, tal como lo requiere AD.
    """
    try:
        logger.info(f"Cambiando contraseña para el usuario con email: {email}")
        config = get_ad_config()
        logger.info(f"Conectando al servidor AD en {config['host']}:{config['port']} (SSL: {config['use_ssl']})")

        # Crear el objeto Server. Si se requiere conexión segura, usar LDAPS.
        if config['use_ssl']:
            server = Server(config['host'], port=config['port'], use_ssl=True, tls=config['tls_config'])
        else:
            # Opción alternativa: usar StartTLS si no se usa SSL directamente.
            server = Server(config['host'], port=config['port'], use_ssl=False)

        conn = Connection(server,
                          user=config['user'],
                          password=config['password'],
                          auto_bind=True,
                          receive_timeout=30)

        if not conn.bound:
            logger.error(f"No se pudo conectar al AD. Razón: {conn.result}")
            return {"success": False, "message": "No se pudo conectar al Active Directory."}

        # Si no se usa SSL, podrías probar a iniciar TLS. Ejemplo:
        if not config['use_ssl']:
            if not conn.start_tls():
                logger.error("No se pudo iniciar StartTLS en la conexión.")
                return {"success": False, "message": "StartTLS falló. Conexión no segura para cambiar contraseña."}

        logger.info("Conexión con el AD establecida correctamente para cambiar contraseña.")

        # Buscar el usuario por el campo mail.
        search_filter = f"(&(objectClass=user)(mail={email}))"
        conn.search(
            search_base=config['search_base'],
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=['distinguishedName']
        )
        if not conn.entries:
            logger.error("No se encontró el usuario en AD con el email proporcionado.")
            conn.unbind()
            return {"success": False, "message": "Usuario no encontrado en Active Directory."}

        user_dn = conn.entries[0].entry_dn
        logger.info(f"DN encontrado para el usuario: {user_dn[:30]}...")

        password_value = ('"' + new_password + '"').encode('utf-16-le')
        modify_password = {'unicodePwd': [(MODIFY_REPLACE, [password_value])]}

        conn.modify(user_dn, modify_password)
        if conn.result.get('result') == 0:
            logger.info("Contraseña cambiada exitosamente en el servidor AD.")
            result = {"success": True, "message": "La contraseña fue cambiada exitosamente."}
        else:
            logger.error(f"Error al cambiar contraseña: {conn.result}")
            result = {"success": False,
                      "message": f"El cambio de contraseña falló. Razón: {conn.result.get('description', 'N/A')}, Mensaje: {conn.result.get('message', 'N/A')}"}
        conn.unbind()
        logger.info("Conexión LDAP cerrada.")
        return result

    except LDAPBindError as e:
        logger.error(f"Error al autenticar contra el LDAP: {e}")
        return {"success": False, "message": "Error al autenticar contra el AD."}
    except LDAPException as e:
        logger.error(f"Error en la operación LDAP: {e}")
        return {"success": False, "message": f"Error en la operación LDAP: {e}"}
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return {"success": False, "message": f"Error inesperado: {e}"}

def fetch_ad_users(retries=3, delay=5):
    """Obtiene usuarios de AD con reintentos y manejo de errores"""
    config = get_ad_config()

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Intento {attempt} de conexión con {config['host']}:{config['port']}")

            # Configurar servidor
            server = Server(
                host=config['host'],
                port=config['port'],
                use_ssl=config['use_ssl'],
                tls=config['tls_config'],
                connect_timeout=10
            )

            # Establecer conexión
            with Connection(
                    server,
                    user=config['user'],
                    password=config['password'],
                    auto_bind=True,
                    receive_timeout=30
            ) as conn:

                logger.debug(f"Conexión establecida: {conn.bound}")

                # Realizar búsqueda
                search_filter = '(&(objectClass=user)(objectCategory=person))'
                attributes = [
                    'sAMAccountName',
                    'displayName',
                    'mail',
                    'telephoneNumber'
                ]

                conn.search(
                    search_base=config['search_base'],
                    search_filter=search_filter,
                    attributes=attributes,
                    search_scope=SUBTREE,
                    size_limit=10000
                )

                logger.info(f"Usuarios encontrados: {len(conn.entries)}")

                # Procesar resultados
                usuarios = []
                for entry in conn.entries:
                    try:
                        usuario = {
                            'username': entry.sAMAccountName.value,
                            'name': entry.displayName.value if entry.displayName else entry.sAMAccountName.value,
                            'email': entry.mail.value if entry.mail else '',
                            'phone': entry.telephoneNumber.value if entry.telephoneNumber else ''
                        }
                        usuarios.append(usuario)
                    except AttributeError as e:
                        logger.warning(f"Error procesando entrada: {e}")
                        continue

                return usuarios

        except Exception as e:
            logger.error(f"Error en intento {attempt}: {str(e)}")
            if attempt < retries:
                logger.info(f"Reintentando en {delay} segundos...")
                time.sleep(delay)
            else:
                raise

    return []


def check_group_membership(email: str) -> bool:
    """Verifica si el usuario pertenece al grupo configurado"""
    config = get_ad_config()
    group_dn = os.getenv("AD_GROUP")

    if not group_dn:
        raise ValueError("AD_GROUP no configurado en .env")

    # Asegurar que el filtro use el DN del grupo correctamente
    search_filter = (
        f"(&(objectClass=user)(mail={email})"
        f"(memberOf:1.2.840.113556.1.4.1941:={group_dn}))"
    )

    with Connection(
            Server(config['host'], port=config['port'], use_ssl=config['use_ssl']),
            user=config['user'],
            password=config['password']
    ) as conn:
        conn.search(
            search_base=config['search_base'],
            search_filter=search_filter,
            attributes=['memberOf'],
            search_scope=SUBTREE
        )
        return bool(conn.entries)

def is_user_active(email: str) -> bool:
    """
    Verifica si un usuario está activo en Active Directory.
    :param email: Correo electrónico del usuario.
    :return: True si está activo, False en caso contrario.
    """
    try:
        config = get_ad_config()
        server = Server(config['host'], port=config['port'], use_ssl=config['use_ssl'])

        with Connection(server, user=config['user'], password=config['password'], auto_bind=True) as conn:
            search_filter = f"(&(objectClass=user)(mail={email}))"
            conn.search(
                search_base=config['search_base'],
                search_filter=search_filter,
                attributes=['userAccountControl'],
                search_scope=SUBTREE
            )

            if not conn.entries:
                return False  # Usuario no encontrado

            # Verificar el atributo `userAccountControl`
            user_control = int(conn.entries[0].userAccountControl.value)
            is_active = not (user_control & 2)  # Verifica si el bit de "deshabilitado" no está activo
            return is_active
    except LDAPException as e:
        logger.error(f"Error verificando estado del usuario en AD: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado verificando estado del usuario: {str(e)}")
        return False


# ad_connector/ad_operations.py
def get_password_expiry(email: str) -> dict:
    """Calcula la expiración usando pwdLastSet y la política definida en .env"""
    logger.debug(f"Iniciando consulta para email: {email}")

    config = get_ad_config()
    result = {
        'email': email,
        'expiry_date': None,
        'days_remaining': None,
        'is_expired': True,
        'error': None
    }

    try:
        # Obtener la política desde .env
        policy_days = int(os.getenv('AD_PASSWORD_POLICY_DAYS', 180))
        logger.debug(f"Política de contraseña: {policy_days} días")

        if policy_days <= 0:
            raise ValueError("AD_PASSWORD_POLICY_DAYS debe ser mayor a 0")

        # Conexión a Active Directory
        server = Server(
            config['host'],
            port=config['port'],
            use_ssl=config['use_ssl'],
            connect_timeout=10
        )

        with Connection(
                server,
                user=config['user'],
                password=config['password'],
                auto_bind=True
        ) as conn:

            # Buscar el usuario usando el email
            conn.search(
                search_base=config['search_base'],
                search_filter=f"(&(objectClass=user)(mail={email}))",
                attributes=['pwdLastSet'],
                search_scope=SUBTREE,
                size_limit=1
            )

            if not conn.entries:
                raise ValueError(f"Usuario {email} no encontrado en AD")

            user_entry = conn.entries[0]
            pwd_last_set_value = user_entry.pwdLastSet.value
            logger.debug(f"Valor obtenido de pwdLastSet: {pwd_last_set_value}")

            # Procesar pwdLastSet: si es un datetime, usarlo directamente;
            # de lo contrario, convertirlo a entero y calcular la fecha.
            if isinstance(pwd_last_set_value, datetime):
                last_set_date = pwd_last_set_value
            else:
                # Asegurarse de convertir el valor a entero
                pwd_last_set_value = int(pwd_last_set_value)
                epoch_start = datetime(1601, 1, 1, tzinfo=timezone.utc)
                last_set_date = epoch_start + timedelta(
                    microseconds=pwd_last_set_value // 10
                )

            logger.debug(f"Último cambio de contraseña: {last_set_date.isoformat()}")

            # Calcular la fecha de expiración según la política
            expiry_date = last_set_date + timedelta(days=policy_days)
            logger.debug(f"Expiración calculada: {expiry_date.isoformat()}")

            # Determinar los días restantes y el estado de expiración
            now = datetime.now(timezone.utc)
            days_remaining = (expiry_date - now).days
            logger.debug(f"Días restantes: {days_remaining}")

            result.update({
                'expiry_date': expiry_date.strftime('%d/%m/%Y %H:%M UTC'),
                'days_remaining': days_remaining,
                'is_expired': days_remaining < 0
            })

    except Exception as e:
        logger.error(f"Error para {email}: {str(e)}", exc_info=True)
        result['error'] = str(e)

    logger.debug(f"Resultado final: {result}")
    return result


if __name__ == "__main__":
    # Para pruebas directas
    load_dotenv()
    try:
        users = fetch_ad_users()
        print(f"\nUsuarios obtenidos ({len(users)}):")
        for user in users[:5]:
            print(f" - {user['username']}: {user['name']}")
    except Exception as e:
        print(f"Error crítico: {str(e)}")