# gitupdate — Git Portable Manager

Менеджер автоматичного оновлення, резервного копіювання, автентифікації та **АВТО-СИНХРОНІЗАЦІЇ** Git for Windows Portable у Autonomous Capsule.

**Поточна версія:** `git_manager.py` v1.8

## Запуск

### 🔵 Бойовий ярлик (системний, для обслуговування)

```
Win+R → git
```

- Виконує оновлення Git, бекап та перевірку доступу.
- Вказує на `devops\gitupdate\git_launcher.bat`.

### 🔄 Швидка синхронізація (Sync All Repos)

```
Win+R → gitsync
```

- Виконує автоматичний `git push` для всіх репозиторіїв капсули.
- Вказує на `devops\gitupdate\sync_launcher.bat` (викликає `git_manager.py --sync`).

## Портативність

`git_manager.py` використовує `CAPSULE_ROOT` auto-detect:
Хардкодовані абсолютні шляхи відсутні — проект працює з будь-якого розташування.

## Алгоритм роботи

1. **Перевірка системного PATH** — `apps/git/bin` та `apps/git/cmd` у HKLM PATH.
2. **Очищення логів** — видалення файлів старших за 7 днів; якщо активний лог > 50 MB → ротація.
3. **Health Checks** — перевірка наявності 7-Zip, Git директорії та SSH.
4. **Крок синхронізації (`--sync`)** — автоматичний `git push` для REPOS (тільки якщо запущено з прапором або в повному циклі).
5. **Резервне копіювання** — AES-256 шифрований архів `apps/git/`.
6. **Автентифікація GitHub** — перевірка SSH з'єднання та отримання списку репозиторіїв.
7. **Перевірка оновлення** — запит останнього релізу через GitHub API.

## Структура файлів

```
devops/gitupdate/
  git_manager.py      ✅ — головний менеджер (v1.8)
  git_launcher.bat    ✅ — лаунчер (обслуговування)
  sync_launcher.bat   ✅ — лаунчер (швидка синхронізація)
  .env.example        ✅ — шаблон конфігурації
  README.md           ✅ — ця документація

apps/git/             ✅ — Git for Windows Portable
  .ssh/               ✅ — SSH ключі та config (Routing)
  etc/gitconfig       ✅ — портативний gitconfig
```

## Конфігурація (.env)

Скрипт підтримує `.env` файл для Vaultwarden та GitHub CLI:

```bash
# Vaultwarden для пароля бекапу
BW_HOST=https://your-vaultwarden-host.example.com
BW_EMAIL=your-email@example.com
BW_ITEM_NAME=CAPSULE_GIT_BACKUP_PASSWORD

# GitHub CLI токени (для gh repo list)
GH_TOKEN_MAIN=github_pat_placeholder_main
GH_TOKEN_SECURITY=github_pat_placeholder_security
```

## SSH Routing (Два акаунти)

Менеджер підтримує ізоляцію двох GitHub акаунтів через SSH config:

- **Акаунт 1:** `Host1` → `Key1`
- **Акаунт 2:** `Host2` → `Key2`

Маршрутизація налаштовується локально у `.env` та SSH config.

## Резервні копії

- **Що архівується:** `apps/git/` (бінарники + критичні дані)
- **Шифрування:** AES-256 (Vaultwarden)
- **Ротація:** 7 щоденних + 4 тижневих.

## Авто-синхронізація (Git Sync)

Менеджер автоматично обходить список `REPOS` (корінь капсули, second-brain, devops/*) і виконує:
`git status` → `git add .` → `git commit` → `git push`.
Використовується портативний SSH з відповідним ключем для кожного акаунту.

## Залежності

- `requests`, `packaging` (self-healing pip install)
- `apps/bin/gh.exe` — GitHub CLI
- `apps/bin/bw.exe` — Bitwarden CLI
- `apps/7zip/7za.exe` — архівація

## Troubleshooting

**Синхронізація не вдалася:**
Перевір підключення до мережі та наявність `GH_TOKEN` або SSH ключів. У разі конфліктів Git (merge conflicts) — вирішуй їх вручну через Git Bash.

## CHANGELOG

- **v1.8** — Інтеграція `gitsyncupdate`. Додано швидку синхронізацію репозиторіїв та аргумент `--sync`.
- **v1.7** — Стандартизація до `manager_standard v3.2`: `AutoCloseTimer`, оновлене логування, health checks.
- **v1.0-1.6** — Базовий розвиток: оновлення, бекап, Vaultwarden, портативність.
