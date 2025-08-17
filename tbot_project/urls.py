from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static  # 👈 Importar

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('web_interface.urls')),
]

# Sirve archivos estáticos en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Asegúrate de que STATIC_ROOT no interfiera
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'web_interface' / 'static')