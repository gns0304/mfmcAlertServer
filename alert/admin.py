from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.html import format_html, format_html_join
from .models import BroadcastLog, Command, Device, DeviceLog, WavFile

admin.site.site_header = "통합주차관제센터 방송 시스템"
admin.site.site_title = "통합주차관제센터 방송 시스템"
admin.site.index_title = "방송 음원 및 기기 관리"

class SuperuserOnlyAdminMixin:
    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)


User = get_user_model()


@admin.register(WavFile)
class WavFileAdmin(admin.ModelAdmin):
    list_display = (
        "title_link",
        "file_name",
    )
    list_display_links = ("title_link",)
    fields = ("title", "description", "file")
    change_form_template = "admin/alert/wavfile/change_form.html"

    def title_link(self, obj):
        url = reverse("admin:alert_wavfile_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.title)

    title_link.short_description = "방송명"

    def file_name(self, obj):
        return obj.file.name.rsplit("/", 1)[-1]

    file_name.short_description = "파일명"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<int:wav_id>/all_play/", self.admin_site.admin_view(self.all_play), name="wav-all-play"),
            path("all_stop/", self.admin_site.admin_view(self.all_stop), name="wav-all-stop"),
            path("<int:wav_id>/target_play/", self.admin_site.admin_view(self.target_play), name="wav-target-play"),
            path("<int:wav_id>/target_stop/", self.admin_site.admin_view(self.target_stop), name="wav-target-stop"),
        ]
        return custom + urls

    def all_play_button(self, obj):
        return format_html('<a class="button" href="{}">{}</a>', f"{obj.id}/all_play/", "전체 방송")

    all_play_button.short_description = "전체 방송"

    def all_stop_button(self, obj):
        return format_html('<a class="button" href="{}">{}</a>', "all_stop/", "전체 정지")

    all_stop_button.short_description = "전체 정지"

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["devices"] = Device.objects.filter(is_active=True).select_related("user").order_by("id")
        return super().render_change_form(request, context, add, change, form_url, obj)

    def all_play(self, request, wav_id):
        wav = get_object_or_404(WavFile, pk=wav_id)
        Command.objects.create(action=Command.Action.PLAY, wav=wav, all_devices=True)
        BroadcastLog.objects.create(action="PLAY", wav=wav, executed_by=request.user, all_devices=True)
        self.message_user(request, "[전체] 방송 실행 기록 생성", level=messages.SUCCESS)
        return redirect("admin:alert_wavfile_changelist")

    def all_stop(self, request):
        Command.objects.create(action=Command.Action.STOP, all_devices=True)
        BroadcastLog.objects.create(action="STOP", executed_by=request.user, all_devices=True)
        self.message_user(request, "[전체] 정지 실행 기록 생성", level=messages.SUCCESS)
        return redirect("admin:alert_wavfile_changelist")

    def target_play(self, request, wav_id):
        wav = get_object_or_404(WavFile, pk=wav_id)
        ids = request.POST.getlist("device_ids")
        devices = Device.objects.filter(id__in=ids, is_active=True)

        cmd = Command.objects.create(action=Command.Action.PLAY, wav=wav, all_devices=False)
        cmd.targets.set(devices)

        log = BroadcastLog.objects.create(action="PLAY", wav=wav, executed_by=request.user, all_devices=False)
        log.targets.set(devices)

        self.message_user(request, f"[선택] 방송 기록 생성 (장비 {devices.count()}대)", level=messages.SUCCESS)
        return redirect("admin:alert_wavfile_change", object_id=wav_id)

    def target_stop(self, request, wav_id):
        ids = request.POST.getlist("device_ids")
        devices = Device.objects.filter(id__in=ids, is_active=True)

        cmd = Command.objects.create(action=Command.Action.STOP, all_devices=False)
        cmd.targets.set(devices)

        log = BroadcastLog.objects.create(action="STOP", executed_by=request.user, all_devices=False)
        log.targets.set(devices)

        self.message_user(request, f"[선택] 정지 기록 생성 (장비 {devices.count()}대)", level=messages.SUCCESS)
        return redirect("admin:alert_wavfile_change", object_id=wav_id)


@admin.register(Command)
class CommandAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "action", "wav", "all_devices", "created_at")
    filter_horizontal = ("targets",)
    list_filter = ("action", "all_devices")


@admin.register(BroadcastLog)
class BroadcastLogAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("executed_at", "action", "wav", "executed_by", "device_summary")
    list_filter = ("action", "all_devices", "executed_at")
    search_fields = ("wav__file", "executed_by__username")

    def device_summary(self, obj):
        if obj.all_devices:
            return "전체 장비"
        return f"{obj.targets.count()}대"

    device_summary.short_description = "대상 장비"


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name_link", "user", "is_active", "last_seen_at")
    list_display_links = ("name_link",)
    search_fields = ("name", "user__username")
    list_filter = ("is_active",)
    list_select_related = ("user",)

    def get_fieldsets(self, request, obj=None):
        base = ((None, {"fields": ("name", "user", "is_active")}),)
        if obj:
            return base + (("최근 클라이언트 로그 (최신 25개)", {"fields": ("recent_device_logs",)}),)
        return base

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj:
            ro.append("recent_device_logs")
        return ro

    def recent_device_logs(self, obj):
        if not obj:
            return format_html('<span style="color:#888;">-</span>')

        logs = DeviceLog.objects.filter(device=obj).order_by("-created_at")[:25]

        if not logs:
            return format_html('<span style="color:#888;">로그 없음</span>')

        rows = format_html_join(
            "",
            "<tr>"
            "<td style='white-space:nowrap;padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "<td style='white-space:nowrap;padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;word-break:break-word;'>{}</td>"
            "</tr>",
            (
                (
                    timezone.localtime(l.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                    l.level,
                    l.message,
                )
                for l in logs
            ),
        )

        return format_html(
            "<div style='max-width:100%;overflow:auto;'>"
            "<table style='border-collapse:collapse;width:100%;'>"
            "<thead>"
            "<tr>"
            "<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ddd;'>시간</th>"
            "<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ddd;'>레벨</th>"
            "<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ddd;'>메시지</th>"
            "</tr>"
            "</thead>"
            "<tbody>{}</tbody>"
            "</table>"
            "</div>",
            rows,
        )

    recent_device_logs.short_description = "최근 로그"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(is_staff=False, is_superuser=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def name_link(self, obj):
        url = reverse("admin:alert_device_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.name or obj.user.username)

    name_link.short_description = "디바이스"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:device_id>/generate_app_password/",
                self.admin_site.admin_view(self.generate_app_password_view),
                name="device-generate-app-password",
            ),
            path(
                "<int:device_id>/connection_check/",
                self.admin_site.admin_view(self.connection_check_view),
                name="device-connection-check",
            ),
        ]
        return custom + urls

    def gen_password_button(self, obj):
        url = reverse("admin:device-generate-app-password", args=[obj.pk])
        return format_html('<a class="button" href="{}">{}</a>', url, "기기 비밀번호 생성")

    gen_password_button.short_description = "기기 비밀번호"

    def generate_app_password_view(self, request, device_id: int):
        device = get_object_or_404(Device, pk=device_id)
        user = device.user

        raw = get_random_string(24)
        user.set_password(raw)
        user.save(update_fields=["password"])

        context = dict(
            self.admin_site.each_context(request),
            title="기기 비밀번호 생성 완료",
            device=device,
            username=user.username,
            app_password=raw,
        )
        return TemplateResponse(request, "admin/alert/device/app_password_created.html", context)

    def connection_check_view(self, request, device_id: int):
        device = get_object_or_404(Device, pk=device_id)
        
        # Create a PING command for the device
        command = Command.objects.create(action=Command.Action.PING, all_devices=False)
        command.targets.set([device])
        
        self.message_user(
            request, 
            f"장비 '{device.name or device.user.username}'에 연결 확인 명령을 보냈습니다. 클라이언트 응답을 기다립니다.", 
            level=messages.INFO
        )
        
        return redirect("admin:alert_device_change", object_id=device_id)



@admin.register(DeviceLog)
class DeviceLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "device", "level", "short_message")
    list_filter = ("device", "level", ("created_at", DateFieldListFilter))
    search_fields = ("message", "device__name", "device__user__username")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("device",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs

        # 사용자가 'view' 권한을 가진 Device 목록을 가져옴
        allowed_device_ids = [
            d.pk
            for d in Device.objects.all()
            if request.user.has_perm("alert.view_device", d)
        ]
        return qs.filter(device_id__in=allowed_device_ids)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        if obj:  # 특정 DeviceLog 객체에 대한 권한 확인
            return request.user.has_perm("alert.view_device", obj.device)

        # 메뉴 노출 여부 결정: 사용자가 볼 수 있는 Device가 하나라도 있는지 확인
        return any(
            request.user.has_perm("alert.view_device", d)
            for d in Device.objects.all()
        )

    def has_add_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)


    def short_message(self, obj):
        return obj.message[:120]

    short_message.short_description = "메시지"


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(SuperuserOnlyAdminMixin, DjangoUserAdmin):
    pass


@admin.register(Group)
class GroupAdmin(SuperuserOnlyAdminMixin, DjangoGroupAdmin):
    pass

