from django.urls import path
from . import views

urlpatterns = [
    path("status", views.status, name="api_status"),
    path("file", views.file, name="api_file"),
    path("client-log", views.device_log, name="device_log"),
]