from django.urls import path
from . import views

urlpatterns = [
    path("api/status", views.status, name="api_status"),
    path("api/file", views.file, name="api_file"),
    path("api/client-log", views.device_log, name="device_log"),
]