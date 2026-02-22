# gitupdate — Git Portable Manager

**Версія:** 1.6
**Менеджер:** `devops/gitupdate/git_manager.py`
**Лаунчер (системний):** `tags/git.bat` (Win+R → `git`)
**Лаунчер (GitHub-ready):** `devops/gitupdate/git_launcher.bat`

---

## Призначення

Автоматизований менеджер Git for Windows Portable:

- Резервне копіювання `apps/git/` (включно з `.ssh/`) — AES-256 через Vaultwarden
- Перевірка SSH ключів обох GitHub акаунтів (відбитки)
- Перевірка SSH з'єднання з GitHub (`ssh -T`)
- Список репозиторіїв через GitHub CLI (`gh repo list --json`)
- Перевірка та оновлення Git for Windows Portable
- Збереження `.ssh/` та `etc/gitconfig` при оновленні
- Реєстрація в системному PATH
- Ротація логів (7 днів + 50 MB)
- Запуск Git Bash як detached process

---

## Портативність

`CAPSULE_ROOT` визначається автоматично від `SCRIPT_DIR` — хардкодовані шляхи відсутні:

```
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CAPSULE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
```

Структура шляхів:
```
CAPSULE_ROOT/
  devops/
    gitupdate/          ← SCRIPT_DIR
      git_manager.py
  apps/git/             ← GIT_DIR (auto-detect)
  logs/gitlog/          ← LOG_DIR (auto-detect)
  backups/git/          ← BACKUP_ROOT (auto-detect)
```

Проект працює з будь-якого розташування без змін коду.

---

## Портативний лаунчер (GitHub-ready)

`git_launcher.bat` — лаунчер для публікації проекту на GitHub:

- Auto-detect `CAPSULE_ROOT` від `%~dp0` (два рівні вгору: `gitupdate\` → `devops\` → `CAPSULE_ROOT\`)
- Без хардкодованих шляхів — працює з будь-якого розташування capsule
- UAC elevation, перевірки безпеки (Python + скрипт), передача `%*` аргументів
- Виводить `Capsule: %CAPSULE_ROOT%` для підтвердження auto-detect

Відмінність від `tags/git.bat`:
- `tags/git.bat` — системний лаунчер, містить хардкод шляху до capsule, не публікується
- `git_launcher.bat` — GitHub-ready, лежить поруч з менеджером, публікується разом з проектом

---

## Структура файлів

```
devops/gitupdate/
├── git_manager.py      — головний менеджер (v1.6)
├── git_launcher.bat    — GitHub-ready лаунчер (auto-detect CAPSULE_ROOT)
├── .env                — конфігурація (НЕ в git, у .gitignore)
├── .env.example        — шаблон конфігурації (тільки placeholder-значення)
├── .gitignore          — виключення: .env, __pycache__/, *.log, *.7z, *.bak
└── README.md           — цей файл

apps/git/               — Git for Windows Portable
├── .ssh/               — SSH ключі та config (зберігаються при оновленні + шифруються в бекапі)
│   ├── id_ed25519_main      — ключ основного акаунту
│   ├── id_ed25519_security  — ключ security акаунту
│   └── config               — SSH routing (github.com / github-security)
├── etc/gitconfig       — портативний gitconfig (зберігається при оновленні)
├── bin/git.exe         — git CLI
├── git-bash.exe        — Git Bash
└── usr/bin/ssh.exe     — SSH клієнт

apps/bin/
├── gh.exe              — GitHub CLI (керується bin_manager.py)
└── bw.exe              — Bitwarden CLI (керується bin_manager.py)

backups/git/            — резервні копії (AES-256)
└── Git_Backup_YYYY-MM-DD_HH-MM-SS.7z

logs/gitlog/            — логи (ротація 7 днів + 50 MB)
└── git_log_YYYY-MM-DD.log
```

---

## Алгоритм роботи

```
tags/git.bat (UAC)
  └── git_manager.py
        ├── 1. cleanup_old_logs(7)           — видалення логів > 7 днів (поточний день захищений)
        │       └── _rotate_log_if_needed()  — якщо лог > 50 MB → part-файл (_part2, _part3...)
        ├── 2. ensure_gh_installed()          — авто-завантаження gh.exe якщо відсутній
        ├── 3. load_backup_password()         — отримання пароля (Vaultwarden або .env)
        │       ├── Режим 2: bw status → unlock/login → bw get item → пароль
        │       └── Режим 1: GIT_BACKUP_PASSWORD з .env (fallback)
        ├── 4. manage_backups(password)       — AES-256 архів apps/git/ + .ssh/
        │       └── _rotate_backups()         — 7 щоденних + 4 тижневих (понеділки)
        ├── 5. verify_ssh_keys()              — перевірка ключів + відбитки
        ├── 6. check_github_access()          — для кожного акаунту:
        │       ├── _check_ssh_connection()   — ssh -T git@<host>
        │       └── _fetch_repos_via_gh()     — gh repo list --json
        │               └── _print_repos_gh() — форматований вивід
        ├── 7. get_latest_version_github()    — GitHub API releases/latest
        │       └── (якщо є оновлення)
        │             ├── _preserve_user_data()  — backup .ssh/ + gitconfig
        │             ├── download PortableGit-*-64-bit.7z.exe
        │             ├── 7za x → extract_dir
        │             ├── copy → apps/git/
        │             └── _restore_user_data()   — відновлення .ssh/ + gitconfig
        ├── 8. ensure_in_system_path()        — PATH реєстрація (UAC → fix_path.ps1 -AutoClose)
        └── 9. launch_git_bash()              — DETACHED_PROCESS
```

---

## Налаштування пароля резервної копії

Два режими — пріоритет: Режим 2 → Режим 1 → WARNING (без шифрування).

**Режим 2 — Vaultwarden (рекомендовано):**

```
devops/gitupdate/.env:
  BW_HOST=https://your-vaultwarden-instance.example.com
  BW_EMAIL=your-email@example.com
  BW_METHOD=0
  BW_ITEM_NAME=CAPSULE_GIT_BACKUP_PASSWORD
```

Процес автентифікації:

- `bw status` → `unauthenticated` → `bw login` (email + пароль + TOTP, до 3 спроб)
- `bw status` → `locked` → `bw unlock` (тільки майстер-пароль, до 3 спроб)
- `bw status` → `unlocked` → `bw unlock --raw` (свіжий session token)
- `bw sync --session` → синхронізація локального кешу
- `bw get item CAPSULE_GIT_BACKUP_PASSWORD --session` → пароль
- `bw lock` → блокування після використання

⚠️ **ВСТАВКА ПАРОЛЯ: тільки Ctrl+V!** Права кнопка миші обрізає пароль.

**Режим 1 — прямий пароль (fallback):**

```
devops/gitupdate/.env:
  GIT_BACKUP_PASSWORD=your_strong_password_here
```

---

## Резервні копії

- **Що архівується:** `apps/git/` — повністю, включно з `.ssh/` (SSH ключі)
- **Формат:** `Git_Backup_YYYY-MM-DD_HH-MM-SS.7z`
- **Шифрування:** AES-256 + `-mhe=on` (шифрування імен файлів — SSH ключі не видно без пароля)
- **Ротація:** 7 щоденних + 4 тижневих (понеділки)
- **Шлях:** `backups/git/`

Чому `.ssh/` включено в резервну копію:

- `.ssh/` містить приватні ключі обох GitHub акаунтів + SSH routing config
- Втрата ключів = втрата доступу до репозиторіїв (потрібно генерувати нові + реєструвати на GitHub)
- AES-256 + `-mhe=on` — ключі захищені навіть якщо архів витік
- При оновленні Git — `.ssh/` зберігається окремо (`_preserve_user_data`) і відновлюється після

---

## Логи

- **Шлях:** `logs/gitlog/git_log_YYYY-MM-DD.log`
- **Ротація за датою:** 7 днів (поточний день ніколи не видаляється)
- **Ротація за розміром:** якщо активний лог > 50 MB → перейменування у `_part2`, `_part3`...
- **Формат:** `YYYY-MM-DD HH:MM:SS [INFO] повідомлення`

---

## SSH Routing (два акаунти)

```
apps/git/.ssh/config:

Host github.com          → id_ed25519_main     (oleksii-rovnianskyi)
Host github-security     → id_ed25519_security (0scorp919)
```

Використання у репозиторіях:

```bash
# Основний акаунт
git remote set-url origin git@github.com:oleksii-rovnianskyi/repo.git

# Security акаунт
git remote set-url origin git@github-security:0scorp919/repo.git
```

---

## GitHub CLI (gh repo list)

`gh.exe` береться з `apps/bin/` (встановлюється через `Win+R → bin`).

Авторизація без `gh auth login` — через змінну середовища `GH_TOKEN`:

```
devops/gitupdate/.env:
  GH_TOKEN_MAIN=github_pat_your_main_token_here
  GH_TOKEN_SECURITY=github_pat_your_secondary_token_here
```

`git_manager.py` передає відповідний токен як `GH_TOKEN` у середовище `gh` процесу.

---

## Як створити GH_TOKEN

```
GitHub → Settings → Developer settings
  → Personal access tokens → Fine-grained tokens → Generate new token

Необхідні права (Repository permissions):
  - Contents: Read-only
  - Metadata: Read-only (обов'язково)

Для приватних репозиторіїв: "All repositories"
```

---

## Оновлення Git

- Джерело: GitHub `git-for-windows/git` Releases API
- Asset: `PortableGit-{ver}-64-bit.7z.exe` (self-extracting 7z)
- Розпакування: `apps/7zip/7za.exe x`
- Збереження при оновленні: `.ssh/` + `etc/gitconfig`

---

## Залежності

Self-healing pip install при першому запуску:

- `requests` — GitHub API для перевірки оновлень
- `packaging` — порівняння версій

Зовнішні бінарники (керуються `bin_manager.py`):

- `apps/bin/gh.exe` — GitHub CLI
- `apps/bin/bw.exe` — Bitwarden CLI (для Vaultwarden-режиму)
- `apps/7zip/7za.exe` — архівування резервних копій

---

## Troubleshooting

**SSH: Permission denied:**

```bash
# Перевір що публічний ключ додано на GitHub
# Settings → SSH and GPG keys → New SSH key
cat apps/git/.ssh/id_ed25519_main.pub
```

**gh: помилка автентифікації:**

```
Перевір GH_TOKEN_MAIN у devops/gitupdate/.env
Токен має scope: repo + metadata (read)
```

**gh.exe не знайдено:**

```
Win+R → bin   (bin_manager.py завантажить gh.exe)
```

**bw.exe не знайдено:**

```
Win+R → bin   (bin_manager.py завантажить bw.exe)
```

**Vaultwarden: помилка автентифікації:**

```
Перевір BW_HOST, BW_EMAIL у .env
⚠️ Вставляй пароль тільки через Ctrl+V (не права кнопка миші!)
При crypto-помилці — менеджер автоматично робить logout → login
```

**Vaultwarden: запис не знайдено:**

```
Перевір BW_ITEM_NAME=CAPSULE_GIT_BACKUP_PASSWORD у .env
Переконайся що запис існує у Vaultwarden
```

**CAPSULE_ROOT визначається неправильно:**

```
Перевір структуру: git_manager.py має бути у CAPSULE_ROOT/devops/gitupdate/
Поточна структура: SCRIPT_DIR/../.. = CAPSULE_ROOT
```

**Git Bash не запускається:**

```
Перевір: apps/git/git-bash.exe
Запусти вручну: Win+R → git
```

---

## CHANGELOG

- **v1.6** — підготовка до публікації на GitHub (портативність):
  `CAPSULE_ROOT` auto-detect від `SCRIPT_DIR` (замінено хардкод `USER_ROOT`);
  `__version__ = "1.6"` + `get_manager_hash()` — SHA256 self-check цілісності;
  `_rotate_log_if_needed()` — якщо активний лог > 50 MB → part-файл (`_part2`, `_part3`...);
  `cleanup_old_logs()` — захист поточного дня (`today_str` перевірка перед видаленням);
  `git_launcher.bat` — GitHub-ready лаунчер (auto-detect від `%~dp0`);
  `.gitignore` — мінімальний стандарт капсули
- **v1.5** — резервне копіювання `apps/git/` + `.ssh/` (AES-256, Vaultwarden), `_rotate_backups()` (7+4), `load_backup_password()`, повний Vaultwarden-стек; фікс прогрес-бару архівування: `stderr=subprocess.STDOUT` + `readline()` (патерн chrome_manager) — 7-Zip `-bsp1` виводить прогрес у stdout через `\r`, не stderr
- **v1.4** — фікс regex для версії git-for-windows (`2.53.0.windows.1` → `2.53.0.1`)
- **v1.3** — `ensure_gh_installed()` (авто-завантаження gh.exe), фікс SSH `-F config`, таймер 30 с
- **v1.2** — GitHub CLI (`gh repo list --json`), `GH_TOKEN_*` замість `GITHUB_PAT_*`
- **v1.1** — `check_github_access()`, SSH перевірка, GitHub REST API
- **v1.0** — базовий менеджер: версія, оновлення, SSH ключі, Git Bash
