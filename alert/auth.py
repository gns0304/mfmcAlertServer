from functools import wraps
from django.http import JsonResponse
from django.contrib.auth import authenticate
from .models import Device

def basic_auth_device(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Basic "):
            return JsonResponse({"error": "unauthorized"}, status=401)

        import base64
        try:
            raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
            username, password = raw.split(":", 1)
        except Exception:
            return JsonResponse({"error": "unauthorized"}, status=401)

        user = authenticate(username=username, password=password)
        if not user:
            return JsonResponse({"error": "unauthorized"}, status=401)

        device = Device.objects.filter(user=user, is_active=True).first()
        if not device:
            return JsonResponse({"error": "device_not_found_or_inactive"}, status=403)

        request.device = device
        return view(request, *args, **kwargs)
    return wrapper