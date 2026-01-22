from django.http import JsonResponse, FileResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q

from .auth import basic_auth_device
from .models import Command, DeviceLog


@require_GET
@basic_auth_device
def status(request):
    device = request.device
    last_id = request.GET.get("last_id")

    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])

    qs = (
        Command.objects
        .filter(Q(all_devices=True) | Q(targets=device))
        .order_by("-id")
        .distinct()
    )

    if last_id:
        try:
            last_id_int = int(last_id)
            qs = qs.filter(id__gt=last_id_int)
        except ValueError:
            return JsonResponse({"error": "invalid_last_id"}, status=400)

    cmd = qs.first()
    if not cmd:
        return JsonResponse({"has_command": False})

    payload = {
        "has_command": True,
        "command_id": cmd.id,
        "action": cmd.action,
        "ts": int(cmd.created_at.timestamp()),
    }
    if cmd.action == Command.Action.PLAY and cmd.wav:
        payload["filename"] = str(cmd.wav)
    return JsonResponse(payload)


@require_GET
@basic_auth_device
def file(request):
    command_id = request.GET.get("command_id")
    if not command_id:
        return HttpResponseBadRequest("command_id is required")

    try:
        cmd_id = int(command_id)
    except ValueError:
        return JsonResponse({"error": "invalid_command_id"}, status=400)

    cmd = Command.objects.select_related("wav").filter(id=cmd_id).first()
    if not cmd:
        return JsonResponse({"error": "not_found"}, status=404)

    device = request.device
    is_target = cmd.all_devices or cmd.targets.filter(id=device.id).exists()
    if not is_target:
        return JsonResponse({"error": "forbidden"}, status=403)

    if cmd.action != Command.Action.PLAY or not cmd.wav:
        return JsonResponse({"error": "not_a_play_command"}, status=400)

    f = cmd.wav.file
    return FileResponse(
        f.open("rb"),
        as_attachment=True,
        filename=str(cmd.wav),
    )


@csrf_exempt
@require_POST
@basic_auth_device
def device_log(request):
    device = request.device
    level = (request.POST.get("level") or "INFO")[:20]
    message = (request.POST.get("message") or "")[:4000]

    DeviceLog.objects.create(
        device=device,
        level=level,
        message=message,
    )
    return JsonResponse({"ok": True})