import base64
from django.contrib.auth import authenticate
from django.http import JsonResponse


def basic_auth_device(view_func):
    def _wrapped(request, *args, **kwargs):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Basic "):
            return JsonResponse({"error": "auth required"}, status=401)

        try:
            raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
            username, password = raw.split(":", 1)
        except Exception:
            return JsonResponse({"error": "bad auth"}, status=401)

        user = authenticate(username=username, password=password)
        if not user or not hasattr(user, "device"):
            return JsonResponse({"error": "invalid device account"}, status=401)

        request.device = user.device
        return view_func(request, *args, **kwargs)

    return _wrapped