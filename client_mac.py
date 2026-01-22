import os
import time
import tempfile
import traceback
import subprocess
from pathlib import Path
from typing import Optional

import requests


SERVER = os.getenv("MFMC_SERVER", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.getenv("MFMC_USERNAME", "device01")
PASSWORD = os.getenv("MFMC_PASSWORD", "pass1234")

POLL_INTERVAL = float(os.getenv("MFMC_POLL_INTERVAL", "3.0"))
REQUEST_TIMEOUT = float(os.getenv("MFMC_REQUEST_TIMEOUT", "5.0"))
DOWNLOAD_TIMEOUT = float(os.getenv("MFMC_DOWNLOAD_TIMEOUT", "60.0"))

HEARTBEAT_INTERVAL_SEC = int(os.getenv("MFMC_HEARTBEAT_INTERVAL_SEC", "60"))

STATE_DIR = Path(os.getenv("MFMC_STATE_DIR", tempfile.gettempdir()))
LAST_ID_FILE = STATE_DIR / "mfmc_last_command_id.txt"
WAV_FILE_PATH = STATE_DIR / "mfmc_received.wav"

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = BASE_DIR / "log"
SERVER_LOG_MIN_LEVEL = os.getenv("MFMC_SERVER_LOG_MIN_LEVEL", "INFO").upper()


_LEVEL_RANK = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _level_ok(level: str, min_level: str) -> bool:
    return _LEVEL_RANK.get(level, 20) >= _LEVEL_RANK.get(min_level, 20)


def current_log_path() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fname = time.strftime("client_%Y-%m-%d.log")
    return LOG_DIR / fname


def log(msg: str, level: str = "INFO") -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}".replace("\n", "\\n").replace("\r", "\\r")

    try:
        print(line, flush=True)
    except Exception:
        pass

    try:
        with open(current_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    if _level_ok(level, SERVER_LOG_MIN_LEVEL):
        try:
            requests.post(
                f"{SERVER}/api/client-log",
                data={"level": level, "message": msg},
                auth=(USERNAME, PASSWORD),
                timeout=3,
            )
        except Exception:
            pass


def log_exception(prefix: str, exc: Exception) -> None:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log(f"{prefix} exc={repr(exc)}", level="ERROR")
    log(f"{prefix} tb={tb}", level="ERROR")


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


_audio_proc: Optional[subprocess.Popen] = None


def stop_audio() -> None:
    global _audio_proc
    try:
        if _audio_proc and _audio_proc.poll() is None:
            _audio_proc.terminate()
            try:
                _audio_proc.wait(timeout=2)
            except Exception:
                _audio_proc.kill()
        _audio_proc = None
    except Exception as e:
        log_exception("[AUDIO][STOP]", e)


def play_wav(path: Path) -> None:
    global _audio_proc
    stop_audio()
    try:
        _audio_proc = subprocess.Popen(
            ["afplay", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        log("[AUDIO][PLAY] afplay not found on this system", level="ERROR")
    except Exception as e:
        log_exception("[AUDIO][PLAY]", e)


def fetch_status(auth: tuple[str, str], last_id: Optional[int]) -> dict:
    params = {"last_id": str(last_id)} if last_id is not None else None
    url = f"{SERVER}/api/status"
    r = requests.get(url, params=params, auth=auth, timeout=REQUEST_TIMEOUT)

    ct = (r.headers.get("Content-Type") or "").lower()
    if "application/json" not in ct:
        body = (r.text or "")[:400]
        log(f"[STATUS][NON_JSON] http={r.status_code} ct={ct} body={body}", level="ERROR")
        raise RuntimeError("Non-JSON response from /api/status")

    r.raise_for_status()
    return r.json()


def download_wav(auth: tuple[str, str], command_id: int) -> bytes:
    url = f"{SERVER}/api/file"
    r = requests.get(url, params={"command_id": str(command_id)}, auth=auth, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    return r.content


def _env_line() -> str:
    parts = [
        "CLIENT_START",
        f"os=macOS",
        f"server={SERVER}",
        f"user={USERNAME}",
        f"poll={POLL_INTERVAL}s",
        f"timeout={REQUEST_TIMEOUT}s",
        f"dl_timeout={DOWNLOAD_TIMEOUT}s",
        f"state_dir={STATE_DIR}",
        f"log_dir={LOG_DIR}",
        f"server_log_min={SERVER_LOG_MIN_LEVEL}",
        f"heartbeat={HEARTBEAT_INTERVAL_SEC}s",
    ]
    return " | ".join(parts)


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    auth = (USERNAME, PASSWORD)
    last_id = load_last_id()
    last_heartbeat_at = 0.0

    log(_env_line(), level="INFO")
    if last_id is not None:
        log(f"STATE_LOADED | last_command_id={last_id}", level="INFO")

    while True:
        try:
            data = fetch_status(auth, last_id)

            if not data.get("has_command"):
                now = time.time()
                if now - last_heartbeat_at >= HEARTBEAT_INTERVAL_SEC:
                    log("HEARTBEAT | has_command=False", level="INFO")
                    last_heartbeat_at = now
                time.sleep(POLL_INTERVAL)
                continue

            cmd_id = int(data["command_id"])
            action = data.get("action")

            if last_id is not None and cmd_id <= last_id:
                time.sleep(POLL_INTERVAL)
                continue

            if action == "STOP":
                log(f"CMD | action=STOP | command_id={cmd_id}", level="INFO")
                stop_audio()
                last_id = cmd_id
                save_last_id(last_id)

            elif action == "PLAY":
                filename = data.get("filename", "(unknown)")
                log(f"CMD | action=PLAY | command_id={cmd_id} | file={filename}", level="INFO")

                wav_bytes = download_wav(auth, cmd_id)
                WAV_FILE_PATH.write_bytes(wav_bytes)
                log(f"FILE_SAVED | path={WAV_FILE_PATH} | bytes={len(wav_bytes)}", level="INFO")

                play_wav(WAV_FILE_PATH)

                last_id = cmd_id
                save_last_id(last_id)

            else:
                log(f"CMD | action=UNKNOWN | command_id={cmd_id} | action={action}", level="WARNING")
                last_id = cmd_id
                save_last_id(last_id)

        except requests.exceptions.HTTPError as e:
            log_exception("HTTP_ERROR", e)
        except requests.exceptions.RequestException as e:
            log_exception("NETWORK_ERROR", e)
        except Exception as e:
            log_exception("UNEXPECTED", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()