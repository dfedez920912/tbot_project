# TBot Project 🤖

<div align="center">

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Active Directory](https://img.shields.io/badge/Active_Directory-0078D4?style=for-the-badge&logo=microsoft&logoColor=white)](https://microsoft.com)

*An Advanced Telegram Bot System for University Password Management*

*Sistema Avanzado de Bot de Telegram para Gestión de Contraseñas Universitarias*

</div>

## 📋 Overview | Descripción General

### 🇬🇧 English
A comprehensive system that integrates Telegram bot functionality with Active Directory services for managing university passwords. Built with Django and featuring email services, database management, and secure logging capabilities.

### 🇪🇸 Español
Un sistema integral que integra funcionalidad de bot de Telegram con servicios de Active Directory para la gestión de contraseñas universitarias. Construido con Django e incluye servicios de correo electrónico, gestión de base de datos y capacidades seguras de registro.

## 🏗️ Project Structure | Estructura del Proyecto

```
tbot_project/
├── ad_connector/        # Active Directory integration
├── bot_handler/         # Telegram bot core functionality
├── db_handler/         # Database management
├── email_service/      # Email notification system
├── logs/              # System logging
├── telegram_bot/      # Telegram interface
├── tbot_project/      # Django project core
└── manage.py          # Django management script
```

## 🔑 Key Components | Componentes Principales

- **Active Directory Connector**: Manages authentication and user directory services
- **Bot Handler**: Core bot logic and command processing
- **Database Handler**: Data persistence and management
- **Email Service**: User notifications and alerts
- **Telegram Interface**: User interaction and command handling

## ✨ Features | Características

- 🔐 Active Directory Integration
- 📨 Email Notifications
- 🗄️ Secure Database Management
- 📝 Comprehensive Logging
- 🤖 Interactive Telegram Commands
- 👥 User Management
- 🔄 Password Synchronization
- 📊 Activity Monitoring

## 🚀 Getting Started | Comenzar

### Prerequisites | Prerrequisitos

- Python 3.x
- Django
- Telegram Bot API Token
- Active Directory Access
- Email Server Configuration

### Installation | Instalación

```bash
# Clone the repository
git clone https://github.com/dfedez920912/tbot_project.git

# Navigate to project directory
cd tbot_project

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your configurations

# Run migrations
python manage.py migrate

# Start the bot
python manage.py runbot
```

## 🛠️ Configuration | Configuración

1. Set up environment variables in `.env`:
   - Telegram Bot Token
   - Active Directory credentials
   - Database settings
   - Email configuration

2. Configure Active Directory connection in `ad_connector/settings.py`

3. Set up email service in `email_service/config.py`

## 📚 Documentation | Documentación

Detailed documentation is available in the following formats:
- 📖 User Manual (`Manual de Usuario.docx`)
- 🔧 Technical Documentation (in project directories)
- 💡 Code Comments and Docstrings

## 🔒 Security | Seguridad

This project implements comprehensive security measures:

- 🔐 Active Directory authentication
- 📝 Detailed activity logging
- 🔒 Encrypted password storage
- 📨 Secure email communications
- 🛡️ Role-based access control

## 🤝 Contributing | Contribuir

Please read our [Contributing Guidelines](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) before submitting pull requests.

## 📄 License | Licencia

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

## 🆘 Support | Soporte

For support:
1. Check the User Manual (`Manual de Usuario.docx`)
2. Open an [issue](https://github.com/dfedez920912/tbot_project/issues)
3. Contact system administrators

---

<div align="center">
Made with ❤️ by @dfedez920912

[Report Bug](https://github.com/dfedez920912/tbot_project/issues) · [Request Feature](https://github.com/dfedez920912/tbot_project/issues)
</div>