# -*- coding: utf-8 -*-
"""
Git Portable Manager (v1.8)
Author: Oleksii Rovnianskyi / Autonomous Capsule

UA: Менеджер Git — оновлення, бекап та АВТО-СИНХРОНІЗАЦІЯ репозиторіїв.
    Об'єднано функціонал gitupdate та gitsyncupdate.

CHANGELOG:
    v1.8 (2026-02-27) — Інтеграція gitsyncupdate та оптимізація:
           Додано функції sync_repo() та sync_repos() для авто-push.
           Впроваджено url.insteadOf для примусового SSH (фікс помилки /dev/tty).
           Додано CLI аргумент --sync для швидкої синхронізації.
           Уніфіковано REPOS конфігурацію, об'єднано лаунчери (launcher.bat v2.0).
    v1.7 (2026-02-27) — Стандартизація до manager_standard v3.2:
           Впроваджено AutoCloseTimer (30 сек бездіяльності), оновлено logging.
           Впроваджено health_check(), error_reporting(), network_request_with_retry().
           show_path_info() інтегровано в ensure_in_system_path().
    v1.6 — Підготовка до публікації на GitHub (портативність).
    v1.5 — Резервне копіювання apps/git/ → backups/git/ (AES-256).
"""
import os, sys, subprocess, time, datetime, logging, glob, shutil, re, json, hashlib, threading
import msvcrt
import ctypes
from typing import Optional

# ===========================================================================
# VERSION
# ===========================================================================
__version__ = "1.9"

def get_manager_hash() -> str:
    """Return first 12 chars of SHA256 of this script (self-integrity check)."""
    try:
        with open(os.path.abspath(__file__), 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    except Exception:
        return "????????????"

# ===========================================================================
# AUTO-DETECT CAPSULE ROOT
# ===========================================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CAPSULE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
USER_ROOT    = str(CAPSULE_ROOT)

# --- КОНФІГУРАЦІЯ ---
APP_NAME     = "git"
GIT_DIR      = os.path.join(CAPSULE_ROOT, "apps", "git")
GIT_EXE      = os.path.join(GIT_DIR, "bin", "git.exe")
GIT_BIN      = os.path.join(GIT_DIR, "cmd", "git.exe")
LOG_DIR      = os.path.join(CAPSULE_ROOT, "logs", "gitlog")
DOWNLOADS_DIR= os.path.join(CAPSULE_ROOT, "downloads")
ZIP_EXE      = os.path.join(CAPSULE_ROOT, "apps", "7zip", "7za.exe")
PWSH_EXE     = os.path.join(CAPSULE_ROOT, "apps", "pwsh", "pwsh.exe")
GITHUB_REPO  = "git-for-windows/git"
ENV_FILE     = os.path.join(SCRIPT_DIR, ".env")
GH_EXE       = os.path.join(CAPSULE_ROOT, "apps", "bin", "gh.exe")
BW_EXE       = os.path.join(CAPSULE_ROOT, "apps", "bin", "bw.exe")
BACKUP_ROOT  = os.path.join(CAPSULE_ROOT, "backups", "git")
SSH_BIN      = os.path.join(GIT_DIR, "usr", "bin", "ssh.exe")
SSH_CONFIG   = os.path.join(GIT_DIR, ".ssh", "config")
SSH_KEY_MAIN = os.path.join(GIT_DIR, ".ssh", "id_ed25519_main")
SSH_KEY_SECURITY = os.path.join(GIT_DIR, ".ssh", "id_ed25519_security")

def load_sync_repos() -> list[dict]:
    """Parse SYNC_REPO_XX entries from .env.
    UA: Парсить записи SYNC_REPO_XX з .env для динамічного списку синхронізації."""
    repos = []
    env_vars = _parse_env_file()
    keys = sorted([k for k in env_vars.keys() if k.startswith("SYNC_REPO_")])
    for k in keys:
        val = env_vars[k]
        try:
            parts = val.split(":")
            if len(parts) >= 3:
                repos.append({
                    "name":    parts[0].strip(),
                    "local":   parts[1].strip(),
                    "account": parts[2].strip()
                })
        except Exception: continue
    return repos

REPOS = []
PRESERVE_PATHS = [".ssh", r"etc\gitconfig"]

GITHUB_ACCOUNTS: list[dict] = [
    {"label": "main (oleksii-rovnianskyi)", "username": "oleksii-rovnianskyi", "ssh_host": "github.com", "ssh_key": SSH_KEY_MAIN, "env_key": "GH_TOKEN_MAIN"},
    {"label": "security (0scorp919)", "username": "0scorp919", "ssh_host": "github-security", "ssh_key": SSH_KEY_SECURITY, "env_key": "GH_TOKEN_SECURITY"},
]

START_TIME = time.time()
os.system('')

class AutoCloseTimer:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout; self.last_activity = time.time(); self.running = False; self._thread: Optional[threading.Thread] = None
    def reset(self) -> None: self.last_activity = time.time()
    def start(self) -> None: self.running = True; self._thread = threading.Thread(target=self._run, daemon=True); self._thread.start()
    def stop(self) -> None: self.running = False
    def _run(self) -> None:
        while self.running:
            if time.time() - self.last_activity > self.timeout:
                cprint(f"\n[{Colors.YELLOW}TIMEOUT{Colors.RESET}] Автозакриття через {self.timeout} сек.", Colors.YELLOW); os._exit(0)
            time.sleep(1)

_auto_close = AutoCloseTimer(30)

def network_request_with_retry(url: str, method: str = "GET", headers: dict = None, max_retries: int = 3, initial_delay: float = 1.0) -> 'requests.Response':
    import requests
    delay = initial_delay; last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.request(method, url, headers=headers, timeout=30)
            resp.raise_for_status(); return resp
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                log(f"   Retry {attempt + 1}/{max_retries}: {e}", Colors.YELLOW); time.sleep(delay); delay *= 2
    raise ConnectionError(f"Failed after {max_retries} attempts: {last_error}")

class Colors:
    HEADER = '\033[95m'; BLUE = '\033[94m'; CYAN = '\033[96m'
    GREEN  = '\033[92m'; YELLOW= '\033[93m'; RED  = '\033[91m'
    RESET  = '\033[0m';  BOLD  = '\033[1m'

def cprint(msg: str, color: str = Colors.RESET, end: str = "\n") -> None:
    _auto_close.reset(); sys.stdout.write(color + msg + Colors.RESET + end); sys.stdout.flush()

def ensure_dependencies() -> None:
    required = {"requests": "requests", "packaging": "packaging"}
    missing = [pkg for imp, pkg in required.items() if _not_imported(imp)]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing, stdout=subprocess.DEVNULL)

def _not_imported(m):
    try: __import__(m); return False
    except ImportError: return True

ensure_dependencies()
from packaging import version
import requests

def _rotate_log_if_needed() -> str:
    os.makedirs(LOG_DIR, exist_ok=True); today = datetime.date.today().strftime("%Y-%m-%d"); base = os.path.join(LOG_DIR, f"{APP_NAME}_log_{today}.log")
    if os.path.exists(base) and os.path.getsize(base) > 50*1024*1024:
        p = 2
        while os.path.exists(os.path.join(LOG_DIR, f"{APP_NAME}_log_{today}_part{p}.log")): p += 1
        os.rename(base, os.path.join(LOG_DIR, f"{APP_NAME}_log_{today}_part{p}.log"))
    return base

_log_path = _rotate_log_if_needed()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.FileHandler(_log_path, encoding='utf-8')])

def log(msg: str, color: str = Colors.RESET, console: bool = True) -> None:
    logging.info(msg);
    if console: cprint(msg, color)

def draw_progress(label: str, percent: int, width: int = 20) -> None:
    _auto_close.reset(); bars = int(percent / (100 / width)); bar = '=' * bars + '.' * (width - bars)
    sys.stdout.write(f"\r{Colors.YELLOW}{label}: [{bar}] {percent}%{Colors.RESET}"); sys.stdout.flush()

def health_check() -> dict:
    free_space_gb = 0.0
    try:
        total, used, free = shutil.disk_usage(CAPSULE_ROOT)
        free_space_gb = free / (1024**3)
    except Exception:
        pass

    checks = {"7zip": os.path.exists(ZIP_EXE), "git": os.path.exists(GIT_BIN), "log_dir": os.path.exists(LOG_DIR), "capsule_root": os.path.exists(CAPSULE_ROOT), "disk_space": free_space_gb >= 5.0}
    if not checks["7zip"]: log("⚠️ 7-Zip не знайдено!", Colors.YELLOW)
    if not checks["disk_space"]: log(f"❌ Критично мало місця на диску! Вільно: {free_space_gb:.1f} GB (мінімум 5.0 GB)", Colors.RED)
    return checks

def error_reporting(error: Exception, context: str = "") -> None:
    log(f"❌ ПОМИЛКА [{context}]: {error}", Colors.RED); logging.error(f"{context}: {error}", exc_info=True)

# ===========================================================================
# GIT SYNC LOGIC
# ===========================================================================
def sync_repo(repo: dict, max_retries: int = 3) -> bool:
    name = repo["name"]; account = repo["account"]; local_path = os.path.join(CAPSULE_ROOT, repo["local"])
    if not os.path.exists(local_path):
        log(f"   ❌ Репозиторій '{name}' не існує: {local_path}", Colors.RED); return False

    ssh_key = SSH_KEY_MAIN if account == "main" else SSH_KEY_SECURITY
    ssh_host = "github.com" if account == "main" else "github-security"
    ssh_cmd = f'"{SSH_BIN}" -i "{ssh_key}" -F "{SSH_CONFIG}" -o StrictHostKeyChecking=no -o BatchMode=yes'
    env = {**os.environ, "GIT_SSH_COMMAND": ssh_cmd}

    # UA: Вимикаємо credential helper та примушуємо SSH, щоб уникнути GUI вікон
    # UA: Вимикаємо credential helper та примушуємо SSH, щоб уникнути GUI вікон
    # Додатково встановлюємо url.ssh://git@github.com/.insteadOf для примусового SSH
    base_cmd = [
        GIT_BIN,
        "-c", "credential.helper=",
        "-c", f"core.sshCommand={ssh_cmd}",
        "-c", f"url.git@{ssh_host}:.insteadOf=https://github.com/",
        "-c", f"url.git@{ssh_host}:.insteadOf=git@github.com:"
    ]

    log(f"   🔄 Синхронізація '{name}' ({account})...", Colors.CYAN)
    orig_dir = os.getcwd()
    try:
        os.chdir(local_path)
        status = subprocess.run(base_cmd + ["status", "--porcelain"], capture_output=True, text=True, timeout=30).stdout.strip()
        if not status: log(f"   ✅ '{name}' — немає змін", Colors.GREEN); return True

        subprocess.run(base_cmd + ["add", "."], capture_output=True)
        msg = f"Auto-sync {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(base_cmd + ["commit", "-m", msg], capture_output=True)

        for attempt in range(max_retries):
            push = subprocess.run(base_cmd + ["push"], capture_output=True, text=True, env=env, timeout=120)
            if push.returncode == 0: log(f"   ✅ '{name}' — push успішний", Colors.GREEN); return True
            log(f"   ⚠️ Push спроба {attempt+1}/{max_retries}: {push.stderr.strip()}", Colors.YELLOW)
            time.sleep(2 ** attempt)
        return False
    except Exception as e:
        log(f"   ❌ '{name}' помилка: {e}", Colors.RED); return False
    finally: os.chdir(orig_dir)

def sync_repos() -> None:
    global REPOS
    REPOS = load_sync_repos()
    if not REPOS: log("   ⚠️ Список репозиторіїв порожній.", Colors.YELLOW); return
    cprint("-" * 50, Colors.BLUE); log("🔄 ГІТ СИНХРОНІЗАЦІЯ КАПСУЛИ", Colors.HEADER)
    success_count = sum(1 for repo in REPOS if sync_repo(repo))
    log(f"   ✅ Синхронізація завершена: {success_count}/{len(REPOS)}", Colors.GREEN if success_count == len(REPOS) else Colors.YELLOW)

# ===========================================================================
# GIT UPDATE UTILS
# ===========================================================================
def cleanup_old_logs(days: int = 7) -> None:
    log("🧹 Очищення старих логів...", Colors.CYAN); today_str = datetime.date.today().strftime("%Y-%m-%d"); deleted = 0
    for f in glob.glob(os.path.join(LOG_DIR, f"{APP_NAME}_log_*.log")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
        if m and m.group(1) != today_str and (datetime.date.today() - datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()).days > days:
            os.remove(f); deleted += 1
    log(f"✅ Видалено логів: {deleted}", Colors.GREEN)

def get_installed_version() -> str:
    if not os.path.exists(GIT_EXE): return "0.0.0"
    try:
        res = subprocess.run([GIT_EXE, "--version"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"git version (\d+\.\d+\.\d+\.windows\.\d+)", res) or re.search(r"git version (\d+\.\d+\.\d+)", res)
        return m.group(1) if m else "0.0.0"
    except: return "0.0.0"

def normalize_version(ver: str) -> str: return re.sub(r"\.windows\.", ".", ver.lstrip("v")).rstrip(".")

def get_latest_version_github() -> tuple[str, str]:
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    data = network_request_with_retry(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Git-Manager/1.0"}).json()
    tag = data.get("tag_name", "v0.0.0")
    for asset in data.get("assets", []):
        if re.match(r"PortableGit-[\d\.]+-64-bit\.7z\.exe", asset["name"]): return tag, asset["browser_download_url"]
    raise RuntimeError("No asset found")

def _preserve_user_data(tmp_dir: str) -> dict:
    saved = {}
    for rel in PRESERVE_PATHS:
        src = os.path.join(GIT_DIR, rel)
        if not os.path.exists(src): continue
        dst = os.path.join(tmp_dir, "_preserve", rel); os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src): shutil.copytree(src, dst)
        else: shutil.copy2(src, dst)
        saved[rel] = dst; log(f"   💾 Збережено: {rel}", Colors.CYAN)
    return saved

def _restore_user_data(saved: dict) -> None:
    for rel, src in saved.items():
        dst = os.path.join(GIT_DIR, rel)
        if os.path.isdir(src):
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else: os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)
        log(f"   ✅ Відновлено: {rel}", Colors.GREEN)

def update_git(download_url: str, tag: str) -> bool:
    ver_match = re.search(r"v([\d\.]+)\.windows", tag); ver_short = ver_match.group(1) if ver_match else tag.lstrip("v")
    zip_path = os.path.join(DOWNLOADS_DIR, f"PortableGit-{ver_short}-64-bit.7z.exe"); tmp_dir = os.path.join(DOWNLOADS_DIR, f"git_tmp_{ver_short}")
    log(f"⬇️  Завантаження {tag}...", Colors.BLUE)
    try:
        with requests.get(download_url, stream=True, timeout=120) as r:
            r.raise_for_status(); total = int(r.headers.get("content-length", 0)); downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk); downloaded += len(chunk)
                    if total: draw_progress("Завантаження", int(downloaded * 100 / total))
        print()
    except Exception as e: log(f"   ❌ Помилка завантаження: {e}", Colors.RED); return False
    log("💾 Збереження даних...", Colors.CYAN); os.makedirs(tmp_dir, exist_ok=True); saved = _preserve_user_data(tmp_dir)
    log("📦 Розпакування...", Colors.CYAN); ext_dir = os.path.join(tmp_dir, "extracted"); os.makedirs(ext_dir, exist_ok=True)
    subprocess.run([ZIP_EXE, "x", zip_path, f"-o{ext_dir}", "-y"], capture_output=True)
    log("🔄 Копіювання...", Colors.CYAN); ps = {p.split("\\")[0].lower() for p in PRESERVE_PATHS}
    for item in os.listdir(ext_dir):
        if item.lower() in ps: continue
        src = os.path.join(ext_dir, item); dst = os.path.join(GIT_DIR, item)
        if os.path.isdir(src):
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else: shutil.copy2(src, dst)
    log("🔑 Відновлення...", Colors.CYAN); _restore_user_data(saved); log(f"✅ Git оновлено!", Colors.GREEN); shutil.rmtree(tmp_dir, ignore_errors=True); os.remove(zip_path); return True

# ===========================================================================
# VAULTWARDEN LOGIC
# ===========================================================================
def _parse_env_file() -> dict:
    res = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1); res[k.strip()] = v.strip().strip("'\"")
    return res

def _read_clipboard() -> str:
    try:
        pwsh = PWSH_EXE if os.path.exists(PWSH_EXE) else "powershell"
        return subprocess.run([pwsh, "-NoProfile", "-Command", "Get-Clipboard"], capture_output=True, text=True).stdout.strip()
    except: return ""

def _getpass_win(prompt: str = "🔑 Пароль: ") -> str:
    sys.stdout.write(prompt); sys.stdout.flush(); chars = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"): sys.stdout.write("\n"); break
        if ch == "\x08":
            if chars: chars.pop(); sys.stdout.write("\b \b"); sys.stdout.flush()
        elif ch == "\x16":
            p = _read_clipboard()
            for pc in p:
                if pc.isprintable(): chars.append(pc); sys.stdout.write("*")
            sys.stdout.flush()
        elif ch.isprintable(): chars.append(ch); sys.stdout.write("*"); sys.stdout.flush()
    return "".join(chars)

def _bw_get_status(env: dict) -> str:
    try:
        res = subprocess.run([BW_EXE, "status"], capture_output=True, text=True, env=env, timeout=10)
        return json.loads(res.stdout).get("status", "unauthenticated")
    except: return "unauthenticated"

def get_vaultwarden_token() -> tuple[Optional[str], dict]:
    ev = _parse_env_file()
    if not os.path.exists(BW_EXE): return None, {}
    env = os.environ.copy(); env["BITWARDENCLI_APPDATA_DIR"] = os.path.join(os.path.dirname(BW_EXE), ".bw_data")
    if ev.get("BW_HOST"): subprocess.run([BW_EXE, "config", "server", ev["BW_HOST"]], capture_output=True, env=env)
    status = _bw_get_status(env); token = None
    if status == "unlocked":
        res = subprocess.run([BW_EXE, "unlock", "--raw"], capture_output=True, text=True, env=env)
        if res.returncode == 0: token = res.stdout.strip()
    if not token:
        log(f"   ℹ️  Vaultwarden ({ev.get('BW_EMAIL', 'Vault')}) заблоковано.", Colors.CYAN)
        _auto_close.stop()
        mp = _getpass_win("   🔑 Майстер-пароль Vaultwarden (тільки Ctrl+V): ")
        _auto_close.reset()
        _auto_close.start()
        if not mp:
            log("   ⚠️ Майстер-пароль не введено. Пропускаємо Vaultwarden.", Colors.YELLOW)
            return None, env
        env["BW_PASSWORD"] = mp
        res = subprocess.run([BW_EXE, "unlock", "--passwordenv", "BW_PASSWORD", "--raw"], capture_output=True, text=True, env=env)
        if res.returncode == 0: token = res.stdout.strip()
    if token:
        subprocess.run([BW_EXE, "sync", "--session", token], capture_output=True, env=env)
    return token, env

def get_password_from_vaultwarden(token: str, env: dict) -> Optional[str]:
    ev = _parse_env_file()
    if ev.get("GIT_BACKUP_PASSWORD"): return ev["GIT_BACKUP_PASSWORD"]
    if not token or not ev.get("BW_ITEM_NAME"): return None
    get_res = subprocess.run([BW_EXE, "get", "item", ev["BW_ITEM_NAME"], "--session", token], capture_output=True, text=True, env=env)
    if get_res.returncode == 0:
        return json.loads(get_res.stdout).get("login", {}).get("password")
    return None

def extract_ssh_keys_from_vaultwarden(token: str, env: dict) -> bool:
    ev = _parse_env_file()
    if not token: return False
    main_name = ev.get("BW_SSH_KEY_MAIN_ITEM", "Github Oleksii Rovnianskyi (oleksii-rovnianskyi)")
    sec_name = ev.get("BW_SSH_KEY_SECURITY_ITEM", "Github Oleksii Rovnianskyi 0scorp919")
    success = True
    os.makedirs(os.path.dirname(SSH_KEY_MAIN), exist_ok=True)

    for name, path in [(main_name, SSH_KEY_MAIN), (sec_name, SSH_KEY_SECURITY)]:
        res = subprocess.run([BW_EXE, "get", "item", name, "--session", token], capture_output=True, text=True, env=env)
        if res.returncode == 0:
            item = json.loads(res.stdout)
            key_val = None
            for f in item.get("fields", []):
                if f.get("name") == "SSH": key_val = f.get("value")
            if key_val:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    content = key_val.replace("\\n", "\n") if "\\n" in key_val else key_val
                    content = content.replace("\r\n", "\n").replace("\r", "\n")
                    if not content.endswith("\n"): content += "\n"
                    f.write(content)
                log(f"   🔑 SSH ключ {name} завантажено.", Colors.GREEN)
            else:
                log(f"   ⚠️ Не знайдено поле 'SSH' у записі {name}.", Colors.YELLOW); success = False
        else:
            log(f"   ❌ Запис {name} не знайдено у Vaultwarden.", Colors.RED); success = False
    return success

def remove_ssh_keys() -> None:
    for path in [SSH_KEY_MAIN, SSH_KEY_SECURITY]:
        if os.path.exists(path):
            try: os.remove(path); log(f"   🗑️  Видалено ключ: {os.path.basename(path)}", Colors.CYAN)
            except: pass

# ===========================================================================
# BACKUP & PATH
# ===========================================================================
def _rotate_backups() -> None:
    files = sorted(glob.glob(os.path.join(BACKUP_ROOT, "Git_Backup_*.7z")))
    if len(files) > 7:
        for f in files[:-7]: os.remove(f)

def manage_backups(password: str | None) -> None:
    cprint("-" * 50, Colors.BLUE); log("💾 РЕЗЕРВНА КОПІЯ GIT", Colors.HEADER)
    os.makedirs(BACKUP_ROOT, exist_ok=True); ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_name = f"Git_Backup_{ts}.7z"
    path = os.path.join(BACKUP_ROOT, archive_name)
    cmd = [ZIP_EXE, "a", path, GIT_DIR, "-mx3", "-mmt=on", "-bso0"]
    if password: cmd.extend([f"-p{password}", "-mhe=on"])
    log(f"   📦 Створення архіву: {archive_name}...", Colors.CYAN)
    subprocess.run(cmd, capture_output=True)

    try:
        with open(path, 'rb') as f: file_hash = hashlib.sha256(f.read()).hexdigest()
        with open(f"{path}.sha256", 'w', encoding='utf-8') as hf: hf.write(f"{file_hash} *{archive_name}\n")
        log(f"   ✓ Створено SHA256 хеш: {file_hash[:8]}...", Colors.GREEN)
    except Exception as e: log(f"   ⚠️ Не вдалося створити SHA256 хеш: {e}", Colors.YELLOW)

    _rotate_backups(); log("   ✅ Бекап завершено", Colors.GREEN)

def show_path_info() -> None:
    cprint("-" * 50, Colors.BLUE); log("🔧 ІНФОРМАЦІЯ ПРО PATH", Colors.HEADER)
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_READ)
        cp, _ = winreg.QueryValueEx(key, "Path"); winreg.CloseKey(key); entries = {e.rstrip("\\").strip().lower() for e in cp.split(";") if e.strip()}
    except: entries = set()
    tags_in = os.path.join(CAPSULE_ROOT, "tags").lower() in entries; git_in = os.path.join(GIT_DIR, "bin").lower() in entries
    log(f"   ✅ tags/   Registered: {tags_in}", Colors.GREEN if tags_in else Colors.RED); log(f"   ✅ Git bin Registered: {git_in}", Colors.GREEN if git_in else Colors.RED)

def ensure_in_system_path() -> None:
    show_path_info()
    if not os.path.exists(os.path.join(CAPSULE_ROOT, r"devops\pathupdate\fix_path.ps1")): return
    log("   ℹ️  Перевірка системи PATH завершена.", Colors.CYAN)

def launch_git_bash() -> None:
    cprint("-" * 50, Colors.BLUE); log("🚀 Запуск Git Bash...", Colors.GREEN); gb = os.path.join(GIT_DIR, "git-bash.exe")
    if os.path.exists(gb): subprocess.Popen([gb, "--cd=" + USER_ROOT], creationflags=0x00000008 | 0x00000200, close_fds=True)

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=f"Manager for {APP_NAME}")
    parser.add_argument("-k", "--keep-open", action="store_true", help="Keep window open after completion")
    parser.add_argument("--sync", action="store_true", help="Run sync only")
    args, _ = parser.parse_known_args()

    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n")
    cprint("=" * 50, Colors.HEADER)
    cprint(f"🚀 MNT: {APP_NAME.upper()} (AUTO-PILOT v{__version__})", Colors.HEADER)
    cprint(f"   Hash: {get_manager_hash()}", Colors.BLUE)
    cprint("=" * 50 + "\n", Colors.HEADER)

    _auto_close.start()
    try:
        ensure_in_system_path()

        checks = health_check()
        if not all(checks.values()): log("⚠️ Деякі перевірки не пройдено", Colors.YELLOW)

        cleanup_old_logs(7)

        token, v_env = get_vaultwarden_token()

        if args.sync:
            try:
                if extract_ssh_keys_from_vaultwarden(token, v_env): sync_repos()
            finally: remove_ssh_keys()
        else:
            pw = get_password_from_vaultwarden(token, v_env); manage_backups(pw)

            cprint("-" * 50, Colors.BLUE); log("🌍 ПЕРЕВІРКА ОНОВЛЕННЯ", Colors.HEADER)
            iv = get_installed_version(); log(f"   Встановлена: {iv}", Colors.CYAN); lt, url = get_latest_version_github(); log(f"   Остання:     {lt}", Colors.CYAN)
            if version.parse(normalize_version(lt)) > version.parse(normalize_version(iv)): update_git(url, lt)
            else: log("   ✅ Оновлення не потрібне", Colors.GREEN)

            try:
                if extract_ssh_keys_from_vaultwarden(token, v_env): sync_repos()
            finally:
                remove_ssh_keys()

            launch_git_bash()

        log("Готово!", Colors.GREEN)

    except KeyboardInterrupt:
        log("\n⚠️ Перервано користувачем", Colors.YELLOW)
        return 1
    except Exception as e:
        error_reporting(e, "main")
        return 1
    finally:
        _auto_close.stop()
        elapsed = time.time() - START_TIME
        cprint("-" * 50, Colors.BLUE)
        cprint(f"⏱️  Час виконання: {elapsed:.1f} сек", Colors.BLUE)
        print("\n")

    if args.keep_open:
        cprint("\n[INFO] Режим --keep-open активовано. Вікно залишиться відкритим.", Colors.CYAN)
        input("Натисніть Enter для виходу...")
    else:
        for i in range(30, 0, -1):
            sys.stdout.write(f"\r{Colors.CYAN}Автозакриття через {i} с... {Colors.RESET}")
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write(f"\r{Colors.CYAN}Автозакриття через 0 с...  {Colors.RESET}   \n")
        sys.stdout.flush()

    return 0

if __name__ == "__main__":
    sys.exit(main())
