from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

def validate_wav_file(f):
    name = (f.name or "").lower()
    if not name.endswith(".wav"):
        raise ValidationError("WAV(.wav) 파일만 업로드 가능합니다.")

    pos = f.file.tell()
    try:
        f.file.seek(0)
        header = f.file.read(12)
    finally:
        f.file.seek(pos)

    if len(header) < 12 or header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise ValidationError("유효한 WAV 파일이 아닙니다(RIFF/WAVE 헤더 없음).")


class Device(models.Model):
    """
    장비 = 로그인 계정(User) 1개와 1:1 매핑
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="device")
    name = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name or self.user.username

    class Meta:
        verbose_name = "방송 장비"
        verbose_name_plural = "방송 장비"

    def clean(self):
        if self.user and (self.user.is_staff or self.user.is_superuser):
            raise ValidationError("스태프/슈퍼유저 계정은 장비로 지정할 수 없습니다.")


class WavFile(models.Model):
    title = models.CharField("방송명", max_length=200)
    description = models.TextField("상세 설명", blank=True)

    file = models.FileField(upload_to="audios/", validators=[validate_wav_file])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "방송 음원"
        verbose_name_plural = "방송 음원"


class Command(models.Model):
    class Action(models.TextChoices):
        PLAY = "PLAY", "PLAY"
        STOP = "STOP", "STOP"
        PING = "PING", "PING"

    action = models.CharField(max_length=10, choices=Action.choices)
    wav = models.ForeignKey(WavFile, null=True, blank=True, on_delete=models.SET_NULL)

    # 전체 명령인지 / 지정 명령인지
    all_devices = models.BooleanField(default=False)
    targets = models.ManyToManyField(Device, blank=True, related_name="commands")

    # 클라이언트가 last_id로 비교할 값(명령 단위)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.action} all={self.all_devices} wav={self.wav}"

    class Meta:
        verbose_name = "방송 명령"
        verbose_name_plural = "방송 명령"



class BroadcastLog(models.Model):
    """
    방송 실행 기록 (어드민에서 버튼을 눌렀을 때 생성)
    """
    action = models.CharField(max_length=10)  # PLAY / STOP
    wav = models.ForeignKey(
        WavFile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="broadcast_logs",
    )

    # 누가 실행했는지 (어드민 사용자)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="broadcast_logs",
    )

    # 대상 장비
    all_devices = models.BooleanField(default=False)
    targets = models.ManyToManyField(Device, blank=True, related_name="broadcast_logs")

    executed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.executed_at} {self.action} {self.wav}"

    class Meta:
        verbose_name = "방송 로그"
        verbose_name_plural = "방송 로그"

class DeviceLog(models.Model):
    device = models.ForeignKey(
        "Device", on_delete=models.CASCADE, related_name="logs"
    )
    level = models.CharField(max_length=20, default="INFO")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device} {self.level} {self.created_at}"

    class Meta:
        verbose_name = "장비 로그"
        verbose_name_plural = "장비 로그"