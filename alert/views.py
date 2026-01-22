from django.http import JsonResponse, FileResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET
from django.utils import timezone
from .models import Device, DeviceLog

from .models import Command
from .auth import basic_auth_device


@require_GET
@basic_auth_device
def status(request):
    device = request.device
    last_id = request.GET.get("last_id")

    # last_seen 업데이트
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])

    qs = Command.objects.order_by("-id")

    # 장비 대상 필터: 전체거나, targets에 포함된 명령
    qs = qs.filter(all_devices=True) | qs.filter(targets=device)
    qs = qs.order_by("-id")

    if last_id:
        # last_id는 숫자(pk) 기준으로 다루는게 가장 단순
        try:
            last_id_int = int(last_id)
            qs = qs.filter(id__gt=last_id_int)
        except ValueError:
            pass

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
        cmd = Command.objects.select_related("wav").get(id=int(command_id))
    except Exception:
        return JsonResponse({"error": "not found"}, status=404)

    # 본인 대상인지 체크(보안)
    device = request.device
    is_target = cmd.all_devices or cmd.targets.filter(id=device.id).exists()
    if not is_target:
        return JsonResponse({"error": "forbidden"}, status=403)

    if cmd.action != Command.Action.PLAY or not cmd.wav:
        return JsonResponse({"error": "not a play command"}, status=400)

    f = cmd.wav.file
    return FileResponse(f.open("rb"), as_attachment=True, filename=str(cmd.wav))

# alert/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required


@csrf_exempt
@login_required
def device_log(request):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)

    device = Device.objects.filter(user=request.user).first()
    if not device:
        return JsonResponse({"ok": False, "error": "device not found"}, status=403)

    data = request.POST
    DeviceLog.objects.create(
        device=device,
        level=data.get("level", "INFO"),
        message=data.get("message", ""),
    )
    return JsonResponse({"ok": True})