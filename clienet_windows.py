import os
import time
import tempfile
import traceback
from pathlib import Path
from typing import Optional

import requests
import winsound


# =========================
# 설정 (환경변수 우선)
# =========================
SERVER = os.getenv("MFMC_SERVER", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.getenv("MFMC_USERNAME", "device01")
PASSWORD = os.getenv("MFMC_PASSWORD", "pass1234")

POLL_INTERVAL = float(os.getenv("MFMC_POLL_INTERVAL", "3.0"))
REQUEST_TIMEOUT = float(os.getenv("MFMC_REQUEST_TIMEOUT", "5.0"))
HEARTBEAT_INTERVAL = int(os.getenv("MFMC_HEARTBEAT_INTERVAL", "120"))

STATE_DIR = Path(os.getenv("MFMC_STATE_DIR", tempfile.gettempdir()))
LAST_ID_FILE = STATE_DIR / "mfmc_last_command_id.txt"
WAV_FILE_PATH = STATE_DIR / "mfmc_received.wav"

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_last_heartbeat_at = 0.0


def current_log_path() -> Path:
    date = time.strftime("%Y-%m-%d")
    return LOG_DIR / f"client_{date}.log"


def log(msg: str, level: str = "INFO") -> None:
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + f"[{level}] {msg}"

    try:
        with open(current_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    try:
        requests.post(
            f"{SERVER}/api/device-log",
            data={"level": level, "message": msg},
            auth=(USERNAME, PASSWORD),
            timeout=3,
        )
    except Exception:
        pass


def log_exception(prefix: str, exc: Exception) -> None:
    tb = " | ".join(
        line.strip()
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    log(f"{prefix} err={repr(exc)} tb={tb}", level="ERROR")


# =========================
# 상태 저장
# =========================
def load_last_id() -> Optional[int]:
    try:
        txt = LAST_ID_FILE.read_text(encoding="utf-8").strip()
        return int(txt) if txt else None
    except Exception:
        return None


def save_last_id(v: int) -> None:
    try:
        LAST_ID_FILE.write_text(str(v), encoding="utf-8")
    except Exception:
        pass


# =========================
# 오디오 제어
# =========================
def stop_audio() -> None:
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception as e:
        log_exception("[AUDIO_STOP]", e)


def play_wav(path: Path) -> None:
    stop_audio()
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        log_exception("[AUDIO_PLAY]", e)


# =========================
# 서버 통신
# =========================
def fetch_status(auth: tuple[str, str], last_id: Optional[int]) -> dict:
    params = {"last_id": str(last_id)} if last_id is not None else None
    r = requests.get(
        f"{SERVER}/api/status",
        params=params,
        auth=auth,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def download_wav(auth: tuple[str, str], command_id: int) -> bytes:
    r = requests.get(
        f"{SERVER}/api/file",
        params={"command_id": str(command_id)},
        auth=auth,
        timeout=60,
    )
    r.raise_for_status()
    return r.content


def write_wav_atomic(data: bytes) -> None:
    tmp = WAV_FILE_PATH.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(WAV_FILE_PATH)


# =========================
# Heartbeat
# =========================
def maybe_heartbeat(last_id: Optional[int]) -> None:
    global _last_heartbeat_at
    now = time.time()
    if now - _last_heartbeat_at >= HEARTBEAT_INTERVAL:
        _last_heartbeat_at = now
        log(f"[HEARTBEAT] alive last_id={last_id}")


# =========================
# 메인 루프
# =========================
def main() -> None:
    log(
        "[STARTUP] "
        f"server={SERVER} "
        f"user={USERNAME} "
        f"poll={POLL_INTERVAL}s "
        f"state_dir={STATE_DIR} "
        f"log_dir={LOG_DIR} "
        f"heartbeat={HEARTBEAT_INTERVAL}s"
    )

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    auth = (USERNAME, PASSWORD)
    last_id = load_last_id()
    if last_id is not None:
        log(f"[STATE] last_command_id={last_id}")

    while True:
        try:
            data = fetch_status(auth, last_id)

            if not data.get("has_command"):
                maybe_heartbeat(last_id)
                time.sleep(POLL_INTERVAL)
                continue

            cmd_id = int(data["command_id"])
            action = (data.get("action") or "").upper()

            if last_id is not None and cmd_id <= last_id:
                time.sleep(POLL_INTERVAL)
                continue

            if action == "STOP":
                log(f"[COMMAND] STOP id={cmd_id}")
                stop_audio()
                last_id = cmd_id
                save_last_id(last_id)

            elif action == "PLAY":
                filename = data.get("filename", "unknown")
                log(f"[COMMAND] PLAY id={cmd_id} file={filename}")

                wav_bytes = download_wav(auth, cmd_id)
                write_wav_atomic(wav_bytes)
                play_wav(WAV_FILE_PATH)

                last_id = cmd_id
                save_last_id(last_id)

            else:
                log(f"[COMMAND] UNKNOWN action={action} id={cmd_id}", level="WARNING")
                last_id = cmd_id
                save_last_id(last_id)

        except requests.exceptions.RequestException as e:
            log_exception("[NETWORK]", e)
        except Exception as e:
            log_exception("[UNEXPECTED]", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()