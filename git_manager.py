# -*- coding: utf-8 -*-
"""
Git Portable Manager (v1.6)
Author: Oleksii Rovnianskyi / Autonomous Capsule

CHANGELOG:
    v1.6 — Підготовка до публікації на GitHub (портативність):
           CAPSULE_ROOT auto-detect від SCRIPT_DIR (замінено хардкод USER_ROOT)
           __version__ = "1.6" + get_manager_hash() — SHA256 self-check цілісності
           _rotate_log_if_needed() — якщо активний лог > 50 MB → part-файл (_part2, _part3...)
           cleanup_old_logs() — захист поточного дня (today_str перевірка перед видаленням)
           git_launcher.bat — GitHub-ready лаунчер поруч з менеджером (auto-detect від %~dp0)
           .gitignore — мінімальний стандарт капсули
    v1.5 — Резервне копіювання apps/git/ → backups/git/ (AES-256, 7-Zip):
           manage_backups(): архівує весь apps/git/ включно з .ssh/ (SSH ключі шифруються!)
           _rotate_backups(): 7 щоденних + 4 тижневих (понеділки) — стандарт капсули
           load_backup_password(): Vaultwarden (CAPSULE_GIT_BACKUP_PASSWORD) або прямий GIT_BACKUP_PASSWORD
           Повний Vaultwarden-стек: _parse_env_file, _read_clipboard, _getpass_win,
           _bw_clear_data, _bw_get_status, _bw_do_unlock, _bw_do_login,
           _get_password_from_vaultwarden, _bw_logout (порт з vscode_manager.py)
           Виклик у main() як крок 2 (після ensure_gh_installed, перед verify_ssh_keys)
    v1.4 — get_installed_version(): замінено жадібний regex на два послідовних патерни:
           1. r"\\d+\\.\\d+\\.\\d+\\.windows\\.\\d+" (повний, пріоритет)
           2. r"\\d+\\.\\d+\\.\\d+" (fallback)
           Причина: r"[\\d\\.]+" жадібно захоплював "2.53.0." -> r"\\.windows\\." не матчився
           -> версія завжди парсилась як "2.53.0" < "2.53.0.1" -> хибне оновлення
    v1.3 — Фікси:
           1. SSH: додано -F ssh_config → alias "github-security" резолвиться коректно
           2. normalize_version(): strip trailing dot → "2.53.0." → "2.53.0"
           3. Auto-download gh.exe якщо відсутній (GitHub CLI releases API)
           4. Автозакриття: 5 сек → 30 сек
    v1.2 — check_github_access(): переведено на GitHub CLI (gh repo list).
           gh.exe береться з apps/bin/ (керується bin_manager.py).
           Авторизація: GH_TOKEN у .env (змінна середовища для gh).
           Fallback: SSH-only якщо gh відсутній або GH_TOKEN не задано.
    v1.1 — check_github_access(): SSH перевірка обох акаунтів + список репозиторіїв
           через GitHub REST API (PAT з .env). Fallback: SSH-only без PAT.
    v1.0 — Початкова версія. GitHub API (git-for-windows/git),
           PortableGit-{ver}-64-bit.7z.exe, збереження .ssh/ та etc/gitconfig.
"""
import os, sys, subprocess, time, datetime, logging, glob, shutil, re, json, hashlib
import msvcrt
import ctypes

# ===========================================================================
# VERSION
# ===========================================================================
__version__ = "1.6"

def get_manager_hash() -> str:
    """Return first 12 chars of SHA256 of this script (self-integrity check).
    UA: Перші 12 символів SHA256 власного файлу (self-check цілісності)."""
    try:
        with open(os.path.abspath(__file__), 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    except Exception:
        return "????????????"

# ===========================================================================
# AUTO-DETECT CAPSULE ROOT — НЕ хардкодити шляхи!
# UA: SCRIPT_DIR → два рівні вгору → корінь капсули
# Структура: CAPSULE_ROOT/devops/gitupdate/git_manager.py
# ===========================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CAPSULE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
# UA: USER_ROOT збережено як str(CAPSULE_ROOT) для зворотної сумісності з Vaultwarden-стеком
USER_ROOT    = str(CAPSULE_ROOT)

# --- КОНФІГУРАЦІЯ ---
GIT_DIR      = os.path.join(CAPSULE_ROOT, "apps", "git")
GIT_EXE      = os.path.join(GIT_DIR, "bin", "git.exe")
GIT_BASH_EXE = os.path.join(GIT_DIR, "git-bash.exe")
LOG_DIR      = os.path.join(CAPSULE_ROOT, "logs", "gitlog")
DOWNLOADS_DIR= os.path.join(CAPSULE_ROOT, "downloads")
ZIP_EXE      = os.path.join(CAPSULE_ROOT, "apps", "7zip", "7za.exe")
PWSH_EXE     = os.path.join(CAPSULE_ROOT, "apps", "pwsh", "pwsh.exe")
GITHUB_REPO  = "git-for-windows/git"
ENV_FILE     = os.path.join(SCRIPT_DIR, ".env")
GH_EXE       = os.path.join(CAPSULE_ROOT, "apps", "bin", "gh.exe")
BACKUP_ROOT  = os.path.join(CAPSULE_ROOT, "backups", "git")
# Файли/папки, які треба зберегти при оновленні (дані користувача)
PRESERVE_PATHS = [
    ".ssh",          # SSH ключі та config для двох GitHub акаунтів
    r"etc\gitconfig",# Портативний gitconfig
]
# Конфігурація двох GitHub акаунтів
GITHUB_ACCOUNTS: list[dict] = [
    {
        "label":    "main (oleksii-rovnianskyi)",
        "username": "oleksii-rovnianskyi",
        "ssh_host": "github.com",
        "ssh_key":  os.path.join(GIT_DIR, r".ssh\id_ed25519_main"),
        "env_key":  "GH_TOKEN_MAIN",      # GH_TOKEN для gh CLI
    },
    {
        "label":    "security (0scorp919)",
        "username": "0scorp919",
        "ssh_host": "github-security",
        "ssh_key":  os.path.join(GIT_DIR, r".ssh\id_ed25519_security"),
        "env_key":  "GH_TOKEN_SECURITY",  # GH_TOKEN для gh CLI
    },
]
START_TIME   = time.time()

os.system('')
class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
    GREEN  = '\033[92m'; YELLOW= '\033[93m'; RED  = '\033[91m'
    RESET  = '\033[0m';  BOLD  = '\033[1m'

def cprint(msg: str, color: str = Colors.RESET, end: str = "\n") -> None:
    sys.stdout.write(color + msg + Colors.RESET + end)
    sys.stdout.flush()

def ensure_dependencies() -> None:
    """Self-healing: auto-install missing pip packages. UA: Авто-встановлення залежностей."""
    required = {"requests": "requests", "packaging": "packaging"}
    missing = []
    for imp, pkg in required.items():
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    if missing:
        cprint(f"[SETUP] Встановлення залежностей: {', '.join(missing)}...", Colors.YELLOW)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + missing,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

ensure_dependencies()

from packaging import version  # type: ignore
import requests                # type: ignore

def _rotate_log_if_needed() -> str:
    """If today's log > 50 MB → rename to _part2, _part3... Return active log path.
    UA: Якщо поточний лог > 50 МБ → перейменувати з суфіксом _part2, _part3...
        Повертає шлях до активного лог-файлу. Поточний день ніколи не видаляється."""
    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    base = os.path.join(LOG_DIR, f"git_log_{today}.log")
    if not os.path.exists(base):
        return base
    size_mb = os.path.getsize(base) / (1024 * 1024)
    if size_mb <= 50:
        return base
    part = 2
    while os.path.exists(os.path.join(LOG_DIR, f"git_log_{today}_part{part}.log")):
        part += 1
    new_path = os.path.join(LOG_DIR, f"git_log_{today}_part{part}.log")
    os.rename(base, new_path)
    return base


_log_path = _rotate_log_if_needed()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(_log_path, encoding='utf-8')]
)

def log(msg: str, color: str = Colors.RESET, console: bool = True) -> None:
    logging.info(msg)
    if console:
        cprint(msg, color)

def draw_progress(label: str, percent: int, width: int = 20) -> None:
    """Draw ASCII progress bar. UA: Малює прогрес-бар."""
    bars = int(percent / (100 / width))
    bar = '=' * bars + '.' * (width - bars)
    sys.stdout.write(f"\r{Colors.YELLOW}{label}: [{bar}] {percent}%{Colors.RESET}")
    sys.stdout.flush()

# --- УТИЛІТИ ---

def cleanup_old_logs(days: int = 7) -> None:
    """Delete log files older than N days. NEVER delete current day files.
    UA: Видаляє лог-файли старші за N днів. Поточний день НЕ видаляється."""
    log("🧹 Перевірка старих логів...", Colors.CYAN)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    deleted = 0
    for f in glob.glob(os.path.join(LOG_DIR, "git_log_*.log")):
        fname = os.path.basename(f)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        if not m:
            continue
        file_date = m.group(1)
        if file_date == today_str:
            continue  # UA: поточний день — ніколи не видаляємо
        try:
            file_dt = datetime.datetime.strptime(file_date, "%Y-%m-%d").date()
            cutoff = datetime.date.today() - datetime.timedelta(days=days)
            if file_dt < cutoff:
                os.remove(f)
                deleted += 1
        except Exception:
            pass
    if deleted:
        log(f"✅ Очищено старих логів: {deleted}", Colors.GREEN)
    else:
        log("✨ Старих логів немає.", Colors.GREEN)


def get_installed_version() -> str:
    """Read installed Git version. UA: Зчитує встановлену версію Git."""
    if not os.path.exists(GIT_EXE):
        return "0.0.0"
    try:
        result = subprocess.run(
            [GIT_EXE, "--version"],
            capture_output=True, text=True, timeout=10
        )
        # "git version 2.53.0.windows.1" → "2.53.0.windows.1"
        # UA: ФІКС — спочатку шукаємо повний патерн з windows, потім fallback на цифри
        # Жадібний [\d\.]+ захоплює "2.53.0." і \.windows\. вже не матчиться
        m = re.search(r"git version (\d+\.\d+\.\d+\.windows\.\d+)", result.stdout)
        if not m:
            m = re.search(r"git version (\d+\.\d+\.\d+)", result.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def normalize_version(ver: str) -> str:
    """Normalize git version for comparison: '2.53.0.windows.1' → '2.53.0.1'.
    UA: Нормалізує версію git для порівняння.
    ФІКС v1.3: strip trailing dot → '2.53.0.' → '2.53.0'"""
    ver = ver.lstrip("v")
    ver = re.sub(r"\.windows\.", ".", ver)
    ver = ver.rstrip(".")  # UA: ФІКС — прибираємо trailing dot
    return ver


def get_latest_version_github() -> tuple[str, str]:
    """Fetch latest Git for Windows release. Returns (tag, download_url).
    UA: Отримує останній реліз Git for Windows. Повертає (тег, url_завантаження)."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Git-Manager/1.0"}
    resp = requests.get(api_url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    tag = data.get("tag_name", "v0.0.0")  # e.g. "v2.53.0.windows.1"

    # Шукаємо PortableGit-{ver}-64-bit.7z.exe
    for asset in data.get("assets", []):
        name = asset["name"]
        if re.match(r"PortableGit-[\d\.]+-64-bit\.7z\.exe", name):
            return tag, asset["browser_download_url"]

    raise RuntimeError(f"Не знайдено PortableGit-*-64-bit.7z.exe у релізі {tag}")


def _preserve_user_data(tmp_dir: str) -> dict[str, str]:
    """Save user data (SSH keys, gitconfig) to temp before update.
    UA: Зберігає дані користувача (.ssh, gitconfig) у temp перед оновленням.
    Returns dict: {relative_path: temp_backup_path}"""
    saved: dict[str, str] = {}
    for rel in PRESERVE_PATHS:
        src = os.path.join(GIT_DIR, rel)
        if not os.path.exists(src):
            continue
        dst = os.path.join(tmp_dir, "_preserve", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        saved[rel] = dst
        log(f"   💾 Збережено: {rel}", Colors.CYAN)
    return saved


def _restore_user_data(saved: dict[str, str]) -> None:
    """Restore user data after update. UA: Відновлює дані користувача після оновлення."""
    for rel, src in saved.items():
        dst = os.path.join(GIT_DIR, rel)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        log(f"   ✅ Відновлено: {rel}", Colors.GREEN)


def update_git(download_url: str, tag: str) -> bool:
    """Download PortableGit self-extracting 7z, extract, preserve user data.
    UA: Завантажує PortableGit self-extracting 7z, розпаковує, зберігає дані користувача."""
    # Витягуємо версію з тегу: v2.53.0.windows.1 → 2.53.0
    ver_match = re.search(r"v([\d\.]+)\.windows", tag)
    ver_short = ver_match.group(1) if ver_match else tag.lstrip("v")

    asset_name = f"PortableGit-{ver_short}-64-bit.7z.exe"
    zip_path = os.path.join(DOWNLOADS_DIR, asset_name)
    tmp_dir = os.path.join(DOWNLOADS_DIR, f"git_tmp_{ver_short}")

    # 1. Завантаження
    log(f"⬇️  Завантаження {asset_name}...", Colors.BLUE)
    headers = {"User-Agent": "Git-Manager/1.0"}
    try:
        with requests.get(download_url, stream=True, headers=headers, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded * 100 / total)
                        draw_progress("Завантаження", pct)
        print()
    except Exception as e:
        log(f"   ❌ Помилка завантаження: {e}", Colors.RED)
        return False

    # 2. Збереження даних користувача
    log("💾 Збереження даних користувача (.ssh, gitconfig)...", Colors.CYAN)
    os.makedirs(tmp_dir, exist_ok=True)
    saved = _preserve_user_data(tmp_dir)

    # 3. Розпакування через 7za.exe
    # PortableGit-*.7z.exe — це self-extracting 7z, розпаковується через: 7za x <file> -o<dir>
    log("📦 Розпакування Git Portable...", Colors.CYAN)
    extract_dir = os.path.join(tmp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    if not os.path.exists(ZIP_EXE):
        log(f"   ❌ 7za.exe не знайдено: {ZIP_EXE}", Colors.RED)
        return False

    result = subprocess.run(
        [ZIP_EXE, "x", zip_path, f"-o{extract_dir}", "-y"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"   ❌ Помилка розпакування:\n{result.stderr}", Colors.RED)
        return False

    # 4. Копіювання файлів у apps/git/ (крім збережених шляхів)
    log("🔄 Копіювання файлів у apps/git/...", Colors.CYAN)
    preserve_set = {p.split("\\")[0].lower() for p in PRESERVE_PATHS}  # top-level dirs to skip

    try:
        for item in os.listdir(extract_dir):
            if item.lower() in preserve_set:
                continue  # Пропускаємо — відновимо з backup
            src = os.path.join(extract_dir, item)
            dst = os.path.join(GIT_DIR, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    except Exception as e:
        log(f"   ❌ Помилка копіювання: {e}", Colors.RED)
        return False

    # 5. Відновлення даних користувача
    log("🔑 Відновлення .ssh/ та gitconfig...", Colors.CYAN)
    _restore_user_data(saved)

    log(f"✅ Git оновлено до {tag}!", Colors.GREEN)

    # 6. Cleanup
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        os.remove(zip_path)
    except Exception:
        pass

    return True


# ---------------------------------------------------------------------------
# УТИЛІТИ — ПАРОЛЬ (Vaultwarden-стек, порт з vscode_manager.py)
# ---------------------------------------------------------------------------

def _parse_env_file() -> dict[str, str]:
    """Parse .env file into key→value dict. UA: Парсить .env у словник."""
    result: dict[str, str] = {}
    if not os.path.exists(ENV_FILE):
        return result
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip().strip('"').strip("'")
    except Exception:
        pass
    return result


def _read_clipboard() -> str:
    """Read clipboard via PowerShell (UAC-safe, bypasses UIPI). Win32 fallback.
    UA: Читає буфер обміну через PowerShell (обходить UIPI в UAC-контексті)."""
    try:
        pwsh = PWSH_EXE if os.path.exists(PWSH_EXE) else "powershell"
        ps_result = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard"],
            capture_output=True, timeout=5
        )
        if ps_result.returncode == 0 and ps_result.stdout:
            text = ps_result.stdout.decode("utf-8", errors="replace").rstrip("\r\n")
            if text:
                return text
    except Exception:
        pass
    try:
        if ctypes.windll.user32.OpenClipboard(0):
            try:
                h = ctypes.windll.user32.GetClipboardData(13)
                if h:
                    ptr = ctypes.windll.kernel32.GlobalLock(h)
                    if ptr:
                        try:
                            size = ctypes.windll.kernel32.GlobalSize(h)
                            if size and size >= 2:
                                raw = ctypes.string_at(ptr, size)
                                text = raw.decode("utf-16-le", errors="ignore").rstrip("\x00\r\n")
                                if text:
                                    return text
                        finally:
                            ctypes.windll.kernel32.GlobalUnlock(h)
            finally:
                ctypes.windll.user32.CloseClipboard()
    except Exception:
        pass
    return ""


def _getpass_win(prompt: str = "Password: ") -> str:
    """Secure password input with Ctrl+V support. UA: Захищений ввід пароля з Ctrl+V."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars: list[str] = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\n"); sys.stdout.flush(); break
        if ch == "\x08":
            if chars:
                chars.pop(); sys.stdout.write("\b \b"); sys.stdout.flush()
            continue
        if ch == "\x16":
            pasted = _read_clipboard()
            for pc in pasted:
                if pc.isprintable():
                    chars.append(pc); sys.stdout.write("*")
            sys.stdout.flush(); continue
        if ch == "\x03":
            sys.stdout.write("\n"); sys.stdout.flush(); return ""
        if ch.isprintable():
            chars.append(ch); sys.stdout.write("*"); sys.stdout.flush()
    return "".join(chars)


def _bw_clear_data(env: dict, bw_exe: str, bw_host: str) -> None:
    """Delete .bw_data/data.json to reset corrupted bw state, re-configure server.
    UA: Видаляє data.json для скидання пошкодженого стану bw."""
    bw_data_dir = env.get("BITWARDENCLI_APPDATA_DIR", "")
    if bw_data_dir:
        data_json = os.path.join(bw_data_dir, "data.json")
        if os.path.exists(data_json):
            try:
                os.remove(data_json)
                log("   🗑️ .bw_data/data.json видалено (скидання стану)", Colors.YELLOW)
            except Exception as e:
                log(f"   ⚠️ Не вдалося видалити data.json: {e}", Colors.YELLOW)
    subprocess.run([bw_exe, "config", "server", bw_host],
                   capture_output=True, env=env, timeout=15)


def _bw_get_status(bw_exe: str, env: dict) -> str:
    """Return bw vault status. UA: Повертає статус сховища (unauthenticated/locked/unlocked)."""
    try:
        result = subprocess.run([bw_exe, "status"],
                                capture_output=True, text=True, env=env, timeout=10)
        data = json.loads(result.stdout.strip())
        return data.get("status", "unauthenticated")
    except Exception:
        return "unauthenticated"


_BW_CRYPTO_ERROR_KEYWORDS = ("key is not", "expected type", "decrypt", "mac failed", "invalid key")


def _is_crypto_error(err_text: str) -> bool:
    low = err_text.lower()
    return any(kw in low for kw in _BW_CRYPTO_ERROR_KEYWORDS)


def _bw_do_unlock(bw_exe: str, env: dict, master_password: str,
                  max_attempts: int = 3) -> tuple[str | None, bool]:
    """Unlock vault with master password. Returns (token|None, needs_relogin).
    UA: Розблоковує vault майстер-паролем. До max_attempts спроб."""
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            cprint(f"   ⚠️ Невірний пароль. Спроба {attempt}/{max_attempts}:", Colors.YELLOW)
            cprint("   ⚠️  ВСТАВКА: тільки Ctrl+V ! Права кнопка миші обрізає пароль.", Colors.YELLOW)
            master_password = _getpass_win("   Майстер-пароль Vaultwarden (Ctrl+V): ")
            if not master_password:
                return None, False
        unlock_env = env.copy()
        unlock_env["BW_MASTER_PASS"] = master_password
        res = subprocess.run([bw_exe, "unlock", "--passwordenv", "BW_MASTER_PASS", "--raw"],
                             capture_output=True, text=True, env=unlock_env, timeout=15)
        if res.returncode == 0:
            token = res.stdout.strip()
            if token:
                log("   ✅ Vault розблоковано", Colors.GREEN)
                return token, False
        err = (res.stderr.strip() or res.stdout.strip())
        if _is_crypto_error(err):
            log(f"   ⚠️ Crypto-помилка unlock: {err}", Colors.YELLOW)
            return None, True
        log(f"   ❌ Помилка unlock (спроба {attempt}): {err}", Colors.RED)
    log(f"❌ Vaultwarden: вичерпано {max_attempts} спроби unlock.", Colors.RED)
    return None, False


def _bw_do_login(bw_exe: str, env: dict, bw_email: str, master_password: str,
                 bw_method: str, max_attempts: int = 3) -> str | None:
    """Full login with email + password + 2FA. UA: Повний логін з 2FA."""
    method_name = "Authenticator App (TOTP)" if bw_method == "0" else "Email"
    cprint(f"   🔑 Автентифікація (2FA: {method_name})...", Colors.CYAN)
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            cprint(f"   ⚠️ Невірний пароль або TOTP. Спроба {attempt}/{max_attempts}:", Colors.YELLOW)
        if not master_password or attempt > 1:
            cprint("   ⚠️  ВСТАВКА: тільки Ctrl+V ! Права кнопка миші обрізає пароль.", Colors.YELLOW)
            master_password = _getpass_win("   Майстер-пароль Vaultwarden (Ctrl+V): ")
            if not master_password:
                return None
        login_env = env.copy()
        login_env["BW_MASTER_PASS"] = master_password
        if bw_method == "1":
            cprint("   📧 Надсилання 2FA коду на email...", Colors.CYAN)
            subprocess.run([bw_exe, "login", bw_email, "--passwordenv", "BW_MASTER_PASS",
                            "--method", "1", "--code", "000000", "--raw"],
                           capture_output=True, text=True, env=login_env, timeout=15)
            sys.stdout.write("   2FA код з email: "); sys.stdout.flush()
            totp_code = input().strip()
        else:
            sys.stdout.write("   TOTP код (Authenticator App): "); sys.stdout.flush()
            totp_code = input().strip()
        if not totp_code:
            return None
        res = subprocess.run([bw_exe, "login", bw_email, "--passwordenv", "BW_MASTER_PASS",
                              "--method", bw_method, "--code", totp_code, "--raw"],
                             capture_output=True, text=True, env=login_env, timeout=30)
        if res.returncode == 0:
            token = res.stdout.strip()
            if token:
                log("   ✅ Успішний вхід", Colors.GREEN)
                return token
        err = (res.stderr.strip() or res.stdout.strip())
        log(f"   ❌ Помилка login (спроба {attempt}): {err}", Colors.RED)
    log(f"❌ Vaultwarden: вичерпано {max_attempts} спроби login.", Colors.RED)
    return None


def _bw_logout(bw_exe: str, env: dict) -> None:
    """Lock vault after use. UA: Блокує сховище після використання."""
    try:
        subprocess.run([bw_exe, "lock"], capture_output=True, env=env, timeout=10)
    except Exception:
        pass


def _get_password_from_vaultwarden(bw_host: str, bw_email: str,
                                    bw_method: str, item_name: str) -> str | None:
    """Fetch backup password from Vaultwarden via bw.exe.
    UA: Отримує пароль резервної копії з Vaultwarden через bw.exe.
    Flow: bw status → unauthenticated→login / locked→unlock / unlocked→token."""
    bw_exe = os.path.join(USER_ROOT, r"apps\bin\bw.exe")
    if not os.path.exists(bw_exe):
        log(f"❌ bw.exe не знайдено: {bw_exe}", Colors.RED)
        log("   Запусти Win+R → bin для встановлення Bitwarden CLI.", Colors.YELLOW)
        return None
    try:
        env = os.environ.copy()
        env["BITWARDENCLI_APPDATA_DIR"] = os.path.join(USER_ROOT, r"apps\bin\.bw_data")
        log(f"🔧 Налаштування Vaultwarden: {bw_host}", Colors.CYAN)
        subprocess.run([bw_exe, "config", "server", bw_host],
                       capture_output=True, env=env, timeout=15)
        vault_status = _bw_get_status(bw_exe, env)
        log(f"   ℹ️  Статус vault: {vault_status}", Colors.CYAN)
        session_token: str | None = None

        if vault_status == "unlocked":
            res = subprocess.run([bw_exe, "unlock", "--raw"],
                                 capture_output=True, text=True, env=env, timeout=15)
            if res.returncode == 0:
                session_token = res.stdout.strip() or None
            if not session_token:
                cprint(f"   Email: {bw_email}", Colors.CYAN)
                cprint("   ⚠️  ВСТАВКА: тільки Ctrl+V ! Права кнопка миші обрізає пароль.", Colors.YELLOW)
                mp = _getpass_win("   Майстер-пароль Vaultwarden (Ctrl+V): ")
                if mp:
                    session_token, needs_relogin = _bw_do_unlock(bw_exe, env, mp)
                    if needs_relogin:
                        subprocess.run([bw_exe, "logout"], capture_output=True, env=env, timeout=10)
                        _bw_clear_data(env, bw_exe, bw_host)
                        session_token = _bw_do_login(bw_exe, env, bw_email, mp, bw_method)

        elif vault_status == "locked":
            cprint(f"   Email: {bw_email}", Colors.CYAN)
            cprint("   ⚠️  ВСТАВКА: тільки Ctrl+V ! Права кнопка миші обрізає пароль.", Colors.YELLOW)
            mp = _getpass_win("   Майстер-пароль Vaultwarden (Ctrl+V): ")
            if not mp:
                return None
            session_token, needs_relogin = _bw_do_unlock(bw_exe, env, mp)
            if needs_relogin:
                subprocess.run([bw_exe, "logout"], capture_output=True, env=env, timeout=10)
                _bw_clear_data(env, bw_exe, bw_host)
                session_token = _bw_do_login(bw_exe, env, bw_email, "", bw_method)

        else:  # unauthenticated
            subprocess.run([bw_exe, "logout"], capture_output=True, env=env, timeout=10)
            _bw_clear_data(env, bw_exe, bw_host)
            cprint(f"   Email: {bw_email}", Colors.CYAN)
            cprint("   ⚠️  ВСТАВКА: тільки Ctrl+V ! Права кнопка миші обрізає пароль.", Colors.YELLOW)
            mp = _getpass_win("   Майстер-пароль Vaultwarden (Ctrl+V): ")
            if not mp:
                return None
            session_token = _bw_do_login(bw_exe, env, bw_email, mp, bw_method)

        if not session_token:
            log("❌ Vaultwarden: не отримано session token.", Colors.RED)
            return None

        cprint("   🔄 Синхронізація сховища (bw sync)...", Colors.CYAN)
        sync_res = subprocess.run([bw_exe, "sync", "--session", session_token],
                                  capture_output=True, text=True, env=env, timeout=30)
        if sync_res.returncode != 0:
            log(f"   ⚠️ bw sync: {sync_res.stderr.strip()}", Colors.YELLOW)
        else:
            log("   ✅ Синхронізацію завершено", Colors.GREEN)

        cprint(f"   🔍 Пошук запису: {item_name}", Colors.CYAN)
        get_res = subprocess.run([bw_exe, "get", "item", item_name, "--session", session_token],
                                 capture_output=True, text=True, env=env, timeout=15)
        if get_res.returncode != 0:
            log(f"❌ Vaultwarden: запис '{item_name}' не знайдено.", Colors.RED)
            _bw_logout(bw_exe, env)
            return None

        item_data = json.loads(get_res.stdout)
        backup_password: str | None = item_data.get("login", {}).get("password")
        if not backup_password:
            log(f"❌ Vaultwarden: поле 'password' порожнє у записі '{item_name}'.", Colors.RED)
            _bw_logout(bw_exe, env)
            return None

        log(f"✅ Пароль отримано з Vaultwarden (запис: {item_name})", Colors.GREEN)
        _bw_logout(bw_exe, env)
        return backup_password

    except subprocess.TimeoutExpired:
        log("❌ Vaultwarden: timeout. Перевір доступність сервера.", Colors.RED)
        return None
    except json.JSONDecodeError as e:
        log(f"❌ Vaultwarden: помилка парсингу відповіді: {e}", Colors.RED)
        return None
    except Exception as e:
        log(f"❌ Vaultwarden: непередбачена помилка: {e}", Colors.RED)
        return None


def load_backup_password() -> str | None:
    """Load backup password from .env (direct or Vaultwarden).
    UA: Завантажує пароль резервної копії з .env.
    Режим 1: GIT_BACKUP_PASSWORD → прямий пароль.
    Режим 2: BW_HOST + BW_EMAIL + BW_ITEM_NAME → Vaultwarden (CAPSULE_GIT_BACKUP_PASSWORD)."""
    env_vars = _parse_env_file()

    direct = env_vars.get("GIT_BACKUP_PASSWORD", "").strip()
    if direct:
        log("🔑 Режим пароля: прямий (.env → GIT_BACKUP_PASSWORD)", Colors.CYAN)
        return direct

    bw_host   = env_vars.get("BW_HOST", "").strip()
    bw_email  = env_vars.get("BW_EMAIL", "").strip()
    bw_method = env_vars.get("BW_METHOD", "0").strip()
    bw_item   = env_vars.get("BW_ITEM_NAME", "").strip()

    if bw_host and bw_email and bw_item:
        log("🔑 Режим пароля: Vaultwarden (bw.exe, інтерактивний вхід)", Colors.CYAN)
        return _get_password_from_vaultwarden(bw_host, bw_email, bw_method, bw_item)

    log("⚠️ .env: пароль не налаштовано. Резервна копія БЕЗ шифрування!", Colors.RED)
    log("   Додай GIT_BACKUP_PASSWORD або BW_HOST+BW_EMAIL+BW_METHOD+BW_ITEM_NAME у .env", Colors.YELLOW)
    return None


# ---------------------------------------------------------------------------
# РЕЗЕРВНЕ КОПІЮВАННЯ
# ---------------------------------------------------------------------------

def _rotate_backups() -> None:
    """Rotate: today=all, 6 prev days=last per day, 4 Mondays=weekly, rest=delete.
    UA: Ротація: сьогодні — всі, 6 днів — по одному, 4 понеділки — тижневі."""
    log("🧹 Ротація резервних копій...", Colors.CYAN)
    files = sorted(glob.glob(os.path.join(BACKUP_ROOT, "Git_Backup_*.7z")))
    if not files:
        return
    today = datetime.date.today()
    keep: set[str] = set()
    # Сьогодні — всі
    for f in files:
        if os.path.basename(f).startswith(f"Git_Backup_{today.strftime('%Y-%m-%d')}"):
            keep.add(f)
    # 6 попередніх днів — по одному (найновіший)
    for delta in range(1, 7):
        day_str = (today - datetime.timedelta(days=delta)).strftime("%Y-%m-%d")
        day_files = [f for f in files if os.path.basename(f).startswith(f"Git_Backup_{day_str}")]
        if day_files:
            keep.add(day_files[-1])
    # 4 тижневих (понеділки)
    mondays = 0
    for delta in range(7, 365):
        day = today - datetime.timedelta(days=delta)
        if day.weekday() == 0 and mondays < 4:
            day_str = day.strftime("%Y-%m-%d")
            day_files = [f for f in files if os.path.basename(f).startswith(f"Git_Backup_{day_str}")]
            if day_files:
                keep.add(day_files[-1]); mondays += 1
    deleted = 0
    for f in files:
        if f not in keep:
            try:
                os.remove(f); deleted += 1
            except Exception:
                pass
    if deleted:
        log(f"   🗑️ Видалено застарілих резервних копій: {deleted}", Colors.YELLOW)
    else:
        log("   ✨ Зайвих резервних копій немає.", Colors.GREEN)


def manage_backups(password: str | None) -> None:
    """Backup apps/git/ → backups/git/ (AES-256 if password set).
    UA: Резервна копія apps/git/ (включно з .ssh/ — SSH ключі шифруються AES-256).
    Що архівується:
      - apps/git/.ssh/          — SSH ключі обох акаунтів + config (КРИТИЧНО!)
      - apps/git/etc/gitconfig  — портативний gitconfig
      - apps/git/bin/, cmd/     — git.exe та допоміжні бінарники
      - apps/git/usr/, mingw64/ — runtime бібліотеки Git
      - apps/git/git-bash.exe   — Git Bash лаунчер
    Формат: Git_Backup_YYYY-MM-DD_HH-MM-SS.7z"""
    cprint("-" * 50, Colors.BLUE)
    log("💾 РЕЗЕРВНА КОПІЯ GIT PORTABLE", Colors.HEADER)

    if not os.path.exists(ZIP_EXE):
        log(f"   ⚠️ 7za.exe не знайдено: {ZIP_EXE} — резервна копія неможлива.", Colors.RED)
        return
    if not os.path.exists(GIT_DIR):
        log(f"   ⚠️ apps/git/ не знайдено — резервна копія пропущена.", Colors.YELLOW)
        return

    os.makedirs(BACKUP_ROOT, exist_ok=True)

    # Розмір apps/git/
    total_bytes = 0
    for root, _, fnames in os.walk(GIT_DIR):
        for fname in fnames:
            try:
                total_bytes += os.path.getsize(os.path.join(root, fname))
            except Exception:
                pass
    git_mb = total_bytes / (1024 * 1024)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_name = f"Git_Backup_{timestamp}.7z"
    backup_path = os.path.join(BACKUP_ROOT, backup_name)

    log(f"   📂 Розмір apps/git/: {git_mb:.1f} MB", Colors.CYAN)
    log(f"   📦 Архів: {backup_name}", Colors.BLUE)
    log(f"   📋 Вміст: бінарники + .ssh/ (SSH ключі) + etc/gitconfig", Colors.CYAN)

    cmd = [ZIP_EXE, "a", backup_path, GIT_DIR, "-mx3", "-mmt=on", "-bsp1", "-bso0"]
    if password:
        log("   🔒 Шифрування: AES-256 (Активно) — .ssh/ захищено!", Colors.CYAN)
        cmd.extend([f"-p{password}", "-mhe=on"])
    else:
        log("   ⚠️  БЕЗ ПАРОЛЯ! .ssh/ буде у відкритому вигляді!", Colors.RED)
        log("   Додай BW_HOST+BW_EMAIL+BW_ITEM_NAME або GIT_BACKUP_PASSWORD у .env", Colors.YELLOW)

    try:
        # UA: Патерн з chrome_manager: stderr=STDOUT об'єднує потоки,
        # readline() читає по \n. -bsp1 виводить прогрес у stdout.
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="ignore",
        )
        if process.stdout is None:
            log("   ❌ Не вдалося отримати вивід 7-Zip.", Colors.RED)
            return
        last_pct = -1
        while True:
            try:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                m = re.search(r"(\d{1,3})%", line)
                if m:
                    pct = int(m.group(1))
                    if pct != last_pct:
                        draw_progress("   Архівування", pct)
                        last_pct = pct
            except Exception:
                break
        print()  # новий рядок після прогрес-бару
        if process.returncode == 0:
            comp_mb = os.path.getsize(backup_path) / (1024 * 1024)
            saved_pct = 100 - (comp_mb / git_mb * 100) if git_mb > 0 else 0
            log(f"   ✅ Резервна копія: {git_mb:.1f} MB → {comp_mb:.1f} MB (стиснення {saved_pct:.0f}%)", Colors.GREEN)
        else:
            log(f"   ❌ Помилка резервного копіювання (RC={process.returncode}).", Colors.RED)
            return
    except Exception as e:
        log(f"   ❌ Помилка: {e}", Colors.RED)
        return

    _rotate_backups()


# ---------------------------------------------------------------------------
# PAT ТОКЕНИ (для gh CLI)
# ---------------------------------------------------------------------------

def load_env_tokens() -> dict[str, str]:
    """Load PAT tokens from .env file. UA: Завантажує PAT токени з .env файлу.
    Returns dict: {env_key: token_value}"""
    tokens: dict[str, str] = {}
    if not os.path.exists(ENV_FILE):
        return tokens
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    tokens[key.strip()] = val.strip().strip('"').strip("'")
    except Exception as e:
        log(f"   ⚠️ Не вдалося прочитати .env: {e}", Colors.YELLOW)
    return tokens


def _check_ssh_connection(account: dict) -> bool:
    """Test SSH connection to GitHub for given account.
    UA: Перевіряє SSH з'єднання з GitHub для вказаного акаунту.
    Використовує SSH config з apps/git/.ssh/config для резолвінгу alias-хостів.
    Returns True if authenticated successfully."""
    ssh_exe = os.path.join(GIT_DIR, r"usr\bin\ssh.exe")
    if not os.path.exists(ssh_exe):
        ssh_exe = "ssh"

    ssh_key  = account["ssh_key"]
    ssh_host = account["ssh_host"]  # "github.com" або "github-security" (alias з SSH config)
    ssh_config = os.path.join(GIT_DIR, r".ssh\config")

    if not os.path.exists(ssh_key):
        log(f"      ⚠️  SSH ключ не знайдено: {ssh_key}", Colors.YELLOW)
        return False

    cmd = [
        ssh_exe, "-T",
        "-i", ssh_key,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
    ]
    # UA: Підключаємо SSH config щоб alias "github-security" резолвився в github.com
    if os.path.exists(ssh_config):
        cmd += ["-F", ssh_config]
    cmd.append(f"git@{ssh_host}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        # GitHub повертає exit code 1 навіть при успіху ("Hi username!")
        output = (result.stdout + result.stderr).strip()
        if "Hi " in output and "!" in output:
            m = re.search(r"Hi ([^!]+)!", output)
            gh_user = m.group(1).strip() if m else "?"
            log(f"      ✅ SSH OK → GitHub відповів: Hi {gh_user}!", Colors.GREEN)
            return True
        elif "Permission denied" in output:
            log(f"      ❌ SSH: Permission denied (ключ не авторизовано на GitHub)", Colors.RED)
        else:
            log(f"      ⚠️  SSH: несподівана відповідь: {output[:120]}", Colors.YELLOW)
    except subprocess.TimeoutExpired:
        log(f"      ❌ SSH: timeout (8 сек) — немає з'єднання з GitHub", Colors.RED)
    except Exception as e:
        log(f"      ❌ SSH помилка: {e}", Colors.RED)
    return False


def _fetch_repos_via_gh(account: dict, token: str) -> list[dict] | None:
    """Fetch repository list via GitHub CLI (gh repo list).
    UA: Отримує список репозиторіїв через GitHub CLI (gh repo list).
    gh.exe з apps/bin/, авторизація через GH_TOKEN у середовищі.
    Returns list of repo dicts or None on error."""
    if not os.path.exists(GH_EXE):
        log(f"      ⚠️  gh.exe не знайдено: {GH_EXE}", Colors.YELLOW)
        log(f"      ℹ️  Запусти Win+R → bin для встановлення GitHub CLI.", Colors.CYAN)
        return None

    # UA: gh repo list повертає TSV: name\tvisibility\tdescription\tupdatedAt
    # Використовуємо --json для структурованого виводу
    env = os.environ.copy()
    env["GH_TOKEN"] = token  # UA: gh читає GH_TOKEN як PAT

    try:
        result = subprocess.run(
            [GH_EXE, "repo", "list",
             "--limit", "200",
             "--json", "name,visibility,languages,updatedAt,stargazerCount,description"],
            capture_output=True, text=True, timeout=30,
            env=env,
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            if "authentication" in err.lower() or "token" in err.lower():
                log(f"      ❌ gh: помилка автентифікації — перевір GH_TOKEN у .env", Colors.RED)
            else:
                log(f"      ❌ gh: {err[:200]}", Colors.RED)
            return None

        import json
        repos = json.loads(result.stdout)
        return repos

    except subprocess.TimeoutExpired:
        log(f"      ❌ gh: timeout (30 сек)", Colors.RED)
        return None
    except Exception as e:
        log(f"      ❌ gh помилка: {e}", Colors.RED)
        return None


def _print_repos_gh(repos: list[dict]) -> None:
    """Print formatted repository list from gh JSON output.
    UA: Виводить відформатований список репозиторіїв з виводу gh."""
    if not repos:
        log("      📭 Репозиторіїв не знайдено.", Colors.YELLOW)
        return

    public  = [r for r in repos if r.get("visibility", "").lower() == "public"]
    private = [r for r in repos if r.get("visibility", "").lower() == "private"]

    log(f"      📦 Всього репозиторіїв: {len(repos)} "
        f"(🔓 публічних: {len(public)}, 🔒 приватних: {len(private)})", Colors.CYAN)

    if public:
        log("      🔓 Публічні:", Colors.GREEN)
        for r in public:
            stars   = r.get("stargazerCount", 0)
            # UA: languages — список об'єктів [{node: {name: "Python"}}]
            langs_raw = r.get("languages", {})
            if isinstance(langs_raw, list) and langs_raw:
                lang = langs_raw[0].get("node", {}).get("name", "—")
            elif isinstance(langs_raw, dict):
                lang = next(iter(langs_raw), "—")
            else:
                lang = "—"
            updated = (r.get("updatedAt") or "")[:10]
            star_str = f" ⭐{stars}" if stars else ""
            log(f"         • {r['name']:<35} [{lang:<12}] {updated}{star_str}", Colors.GREEN)

    if private:
        log("      🔒 Приватні:", Colors.YELLOW)
        for r in private:
            langs_raw = r.get("languages", {})
            if isinstance(langs_raw, list) and langs_raw:
                lang = langs_raw[0].get("node", {}).get("name", "—")
            elif isinstance(langs_raw, dict):
                lang = next(iter(langs_raw), "—")
            else:
                lang = "—"
            updated = (r.get("updatedAt") or "")[:10]
            log(f"         • {r['name']:<35} [{lang:<12}] {updated}", Colors.YELLOW)


def ensure_gh_installed() -> None:
    """Auto-download gh.exe from GitHub CLI releases if missing.
    UA: Автоматично завантажує gh.exe якщо відсутній у apps/bin/."""
    if os.path.exists(GH_EXE):
        return

    cprint("-" * 50, Colors.BLUE)
    log("📥 ВСТАНОВЛЕННЯ GITHUB CLI (gh.exe)", Colors.HEADER)
    log("   ℹ️  gh.exe відсутній — завантажую автоматично...", Colors.CYAN)

    try:
        api_url = "https://api.github.com/repos/cli/cli/releases/latest"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Git-Manager/1.0"}
        resp = requests.get(api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")

        # UA: Шукаємо gh_*_windows_amd64.zip
        asset_url = None
        asset_name = None
        for asset in data.get("assets", []):
            if re.search(r"gh_[\d\.]+_windows_amd64\.zip", asset["name"]):
                asset_url = asset["browser_download_url"]
                asset_name = asset["name"]
                break

        if not asset_url:
            log(f"   ⚠️  Не знайдено gh_*_windows_amd64.zip у релізі {tag}", Colors.YELLOW)
            return

        log(f"   ⬇️  {asset_name} ({tag})...", Colors.BLUE)
        zip_path = os.path.join(DOWNLOADS_DIR, asset_name)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)

        with requests.get(asset_url, stream=True, headers=headers, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        draw_progress("   gh.exe", int(downloaded * 100 / total))
        print()

        # UA: Розпакування bin/gh.exe з zip
        import zipfile
        bin_dir = os.path.dirname(GH_EXE)
        os.makedirs(bin_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            members = z.namelist()
            gh_member = next((m for m in members if m.endswith("bin/gh.exe")), None)
            if gh_member:
                with z.open(gh_member) as src, open(GH_EXE, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                log(f"   ✅ gh.exe встановлено → {GH_EXE}", Colors.GREEN)
            else:
                log(f"   ⚠️  bin/gh.exe не знайдено в архіві. Вміст: {members[:8]}", Colors.YELLOW)

        # UA: Cleanup
        try:
            os.remove(zip_path)
        except Exception:
            pass

    except Exception as e:
        log(f"   ❌ Не вдалося встановити gh.exe: {e}", Colors.RED)
        log(f"   ℹ️  Запусти Win+R → bin для встановлення вручну.", Colors.CYAN)


def check_github_access() -> None:
    """Check SSH access and list repositories for both GitHub accounts via gh CLI.
    UA: Перевіряє SSH доступ та виводить список репозиторіїв через GitHub CLI (gh)."""
    cprint("-" * 50, Colors.BLUE)
    log("🐙 ПЕРЕВІРКА ДОСТУПУ ДО GITHUB", Colors.HEADER)

    # UA: Перевірка наявності gh.exe
    gh_available = os.path.exists(GH_EXE)
    if not gh_available:
        log(f"   ⚠️  gh.exe не знайдено в apps/bin/", Colors.YELLOW)
        log(f"   ℹ️  Запусти Win+R → bin для встановлення GitHub CLI.", Colors.CYAN)

    tokens = load_env_tokens()
    if not tokens:
        log("   ℹ️  .env не знайдено або порожній.", Colors.YELLOW)
        log(f"   ℹ️  Створи: {ENV_FILE}", Colors.CYAN)
        log("   ℹ️  Формат: GH_TOKEN_MAIN=ghp_... та GH_TOKEN_SECURITY=ghp_...", Colors.CYAN)

    for account in GITHUB_ACCOUNTS:
        label = account["label"]
        cprint(f"\n   👤 {label}", Colors.BOLD)

        # 1. SSH перевірка
        log("      🔌 SSH з'єднання...", Colors.CYAN)
        ssh_ok = _check_ssh_connection(account)

        # 2. Список репозиторіїв через gh CLI
        token = tokens.get(account["env_key"], "")
        if token and gh_available:
            log("      📋 Отримання списку репозиторіїв (gh repo list)...", Colors.CYAN)
            repos = _fetch_repos_via_gh(account, token)
            if repos is not None:
                _print_repos_gh(repos)
        elif not token:
            log(f"      ℹ️  GH_TOKEN відсутній ({account['env_key']}) — список репо пропущено.",
                Colors.YELLOW)
        # gh_available=False вже залоговано вище

        if not ssh_ok and not token:
            log("      ⚠️  Ні SSH, ні GH_TOKEN — акаунт недоступний.", Colors.RED)


def verify_ssh_keys() -> None:
    """Verify SSH keys exist and show their fingerprints.
    UA: Перевіряє наявність SSH ключів та показує їх відбитки."""
    cprint("-" * 50, Colors.BLUE)
    log("🔑 ПЕРЕВІРКА SSH КЛЮЧІВ", Colors.HEADER)
    ssh_dir = os.path.join(GIT_DIR, ".ssh")
    ssh_exe = os.path.join(GIT_DIR, r"usr\bin\ssh-keygen.exe")

    keys = {
        "main (oleksii-rovnianskyi)": os.path.join(ssh_dir, "id_ed25519_main"),
        "security (0scorp919)":       os.path.join(ssh_dir, "id_ed25519_security"),
    }

    for label, key_path in keys.items():
        if os.path.exists(key_path):
            if os.path.exists(ssh_exe):
                try:
                    result = subprocess.run(
                        [ssh_exe, "-l", "-f", key_path],
                        capture_output=True, text=True, timeout=5
                    )
                    fingerprint = result.stdout.strip()
                    log(f"   ✅ {label}: {fingerprint}", Colors.GREEN)
                except Exception:
                    log(f"   ✅ {label}: ключ існує (відбиток недоступний)", Colors.GREEN)
            else:
                log(f"   ✅ {label}: ключ існує", Colors.GREEN)
        else:
            log(f"   ⚠️  {label}: ключ НЕ ЗНАЙДЕНО! ({key_path})", Colors.YELLOW)

    # Перевірка SSH config
    config_path = os.path.join(ssh_dir, "config")
    if os.path.exists(config_path):
        log("   ✅ SSH config: знайдено (github.com + github-security)", Colors.GREEN)
    else:
        log("   ⚠️  SSH config: НЕ ЗНАЙДЕНО!", Colors.YELLOW)


def ensure_in_system_path() -> None:
    """Check if apps/git/bin and apps/git/cmd are in system PATH.
    UA: Перевіряє наявність apps/git/bin та apps/git/cmd у системному PATH."""
    cprint("-" * 50, Colors.BLUE)
    log("🔧 ПЕРЕВІРКА СИСТЕМНОГО PATH", Colors.HEADER)
    ps_script = os.path.join(USER_ROOT, r"devops\pathupdate\fix_path.ps1")
    if not os.path.exists(ps_script):
        log("   ⚠️ fix_path.ps1 не знайдено, пропускаємо.", Colors.YELLOW)
        return
    try:
        import winreg  # type: ignore[import]
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0, winreg.KEY_READ
        )
        current_path, _ = winreg.QueryValueEx(key, "Path")
        winreg.CloseKey(key)
        entries = {e.rstrip("\\").strip().lower() for e in current_path.split(";") if e.strip()}
        git_bin = os.path.join(GIT_DIR, "bin").rstrip("\\").lower()
        git_cmd = os.path.join(GIT_DIR, "cmd").rstrip("\\").lower()
        if git_bin in entries and git_cmd in entries:
            log("   ✅ Capsule PATH вже зареєстровано.", Colors.GREEN)
            return
    except Exception:
        pass
    log("   ℹ️  apps/git/bin або apps/git/cmd відсутні у PATH. Запускаю реєстрацію (UAC)...", Colors.YELLOW)
    pwsh = PWSH_EXE if os.path.exists(PWSH_EXE) else "pwsh"
    try:
        subprocess.run(
            [pwsh, "-NoProfile", "-Command",
             f"Start-Process '{pwsh}' -Verb RunAs -Wait "
             f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{ps_script}\" -AutoClose'"],
            timeout=60
        )
        log("   ✅ PATH оновлено. Перезапусти термінал для застосування.", Colors.GREEN)
    except Exception as e:
        log(f"   ⚠️ Не вдалося оновити PATH: {e}", Colors.YELLOW)
        log(f"   ℹ️  Запусти вручну: {ps_script}", Colors.CYAN)


def launch_git_bash() -> None:
    """Launch Git Bash as detached process. UA: Запускає Git Bash як окремий процес."""
    cprint("-" * 50, Colors.BLUE)
    log("🚀 Запуск Git Bash...", Colors.GREEN)
    if not os.path.exists(GIT_BASH_EXE):
        log(f"   ❌ git-bash.exe не знайдено: {GIT_BASH_EXE}", Colors.RED)
        return
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        [GIT_BASH_EXE, "--cd=" + USER_ROOT],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True
    )


def main() -> None:
    """Main entry point. UA: Головна точка входу."""
    os.system("cls")
    print("\n")
    cprint("=" * 55, Colors.HEADER)
    cprint(f"  🐙 GIT PORTABLE MANAGER  v{__version__}", Colors.HEADER)
    cprint("  Autonomous Capsule | Oleksii Rovnianskyi", Colors.CYAN)
    cprint("=" * 55 + "\n", Colors.HEADER)

    # 1. Очищення старих логів
    cleanup_old_logs(7)

    # 2. Авто-встановлення gh.exe якщо відсутній
    ensure_gh_installed()

    # 3. Резервна копія apps/git/ (Vaultwarden → AES-256)
    backup_pass = load_backup_password()
    manage_backups(backup_pass)

    # 4. Перевірка SSH ключів
    verify_ssh_keys()

    # 5. Перевірка доступу до GitHub + список репозиторіїв
    check_github_access()

    # 6. Перевірка оновлення
    cprint("-" * 50, Colors.BLUE)
    log("🌍 ПЕРЕВІРКА ОНОВЛЕННЯ (GitHub)", Colors.HEADER)
    installed_ver = get_installed_version()
    log(f"   Встановлена версія: {installed_ver}", Colors.CYAN)
    try:
        latest_tag, download_url = get_latest_version_github()
        log(f"   Остання версія:     {latest_tag}", Colors.CYAN)

        installed_norm = normalize_version(installed_ver)
        latest_norm    = normalize_version(latest_tag)

        if version.parse(latest_norm) > version.parse(installed_norm):
            log(f"🚀 Знайдено нову версію! Оновлення {normalize_version(installed_ver)} → {latest_tag}", Colors.YELLOW)
            if update_git(download_url, latest_tag):
                log(f"✅ Git оновлено до {latest_tag}!", Colors.GREEN)
            else:
                log("⚠️ Оновлення не вдалося. Продовжуємо з поточною версією.", Colors.YELLOW)
        else:
            log("✅ Встановлена остання версія.", Colors.GREEN)
    except Exception as e:
        log(f"⚠️ Не вдалося перевірити оновлення: {e}", Colors.YELLOW)

    # 7. Перевірка системного PATH
    ensure_in_system_path()

    # 8. Запуск Git Bash
    launch_git_bash()

    elapsed = time.time() - START_TIME
    cprint(f"\n⏱️  Час виконання: {elapsed:.1f} сек", Colors.BLUE)
    print()
    for i in range(30, 0, -1):
        sys.stdout.write(f"\r{Colors.CYAN}Автозакриття через {i} с...{Colors.RESET}")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r{Colors.CYAN}Автозакриття через 0 с...  {Colors.RESET}   \n")
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
