from django.urls import path
from . import views

app_name = 'web_interface'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('logs/', views.logs_view, name='logs'),
    path('users/', views.users_view, name='users'),
]