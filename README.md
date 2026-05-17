# MCP DROSPR Server

MCP-сервер для анализа Perl кода с помощью Perl::Critic.

> Проект следует [AI Engineering Standard (AES) v1.2](https://github.com/LENA-EE/AI-Engineering-Standard-AES), уровень **AES-L2**. См. [`PROJECT_CONSTITUTION.md`](PROJECT_CONSTITUTION.md) и [`CLAUDE.md`](CLAUDE.md).

## Инструменты

### `perlcritic_analyze`
Анализирует Perl код и возвращает структурированный отчёт.

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `code` | string | **ОБЯЗАТЕЛЬНО** - Perl код для анализа |
| `filename` | string | Имя файла (для отчёта) |
| `severity` | int | Уровень строгости 1-5 (по умолчанию 1) |

**Пример использования:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "perlcritic_analyze",
    "arguments": {
      "code": "use strict;\nopen FILE, 'test.txt';",
      "severity": 1
    }
  }
}
```

### `lookup_symbol`
Найти где определена функция или метод в Perl-проекте.
```json
{"method": "tools/call", "params": {"name": "lookup_symbol", "arguments": {"name": "process_billing"}}}
```
Доступен только если загружен PPI-индекс (`POST /index/upload`).

### `get_file_structure`
Карта файла: все функции с номерами строк, импорты, глобальные переменные.
```json
{"method": "tools/call", "params": {"name": "get_file_structure", "arguments": {"filepath": "Finance/Billing.pm"}}}
```

### `get_callers`
Найти все места где реально вызывается функция (только фактические вызовы, не комментарии).
```json
{"method": "tools/call", "params": {"name": "get_callers", "arguments": {"name": "process_billing"}}}
```

### `index_status`
Информация об индексе: дата обновления, количество файлов.
```json
{"method": "tools/call", "params": {"name": "index_status", "arguments": {}}}
```

### `check_before_push`
Проверяет список Perl-файлов перед `git push`. Severity 4-5 блокирует пуш, severity 3 — предупреждение, 1-2 — игнорируется.
```json
{
  "method": "tools/call",
  "params": {
    "name": "check_before_push",
    "arguments": {
      "files": [{"filename": "Billing.pm", "code": "open(FILE, $path);"}],
      "block_severity": 4
    }
  }
}
```
Используется pre-push git хуком. Возвращает `allow_push: true/false`.

---

## Pre-push git хук — "Husky для Perl"

Автоматически проверяет Perl-файлы перед отправкой в Bitbucket.

### Подключение (одна команда)
```bash
./setup.sh
```

### Что происходит при `git push`
```
git push
  → .githooks/pre-push срабатывает локально
  → читает изменённые .pl/.pm файлы
  → отправляет на MCP-сервер
  → severity 4-5 → ❌ пуш заблокирован
  → severity 3   → ⚠ предупреждение, пуш идёт
  → чисто        → ✅ пуш проходит молча
```

### Настройка адреса сервера
Поменяй `MCP_URL` в `.githooks/pre-push`:
```bash
MCP_URL="http://192.168.1.106:8000"  # адрес виртуалки банка
```

### Требования на машине разработчика
- `bash`, `curl`, `python3` — стандарт, ничего дополнительно ставить не нужно
- Perl::Critic **не нужен** — работает в Docker на сервере

---

## PPI-индекс — загрузка

Индекс собирается через TeamCity и загружается на сервер:
```bash
# На TeamCity-агенте (или вручную для теста):
perl tools/build_index.pl /path/to/perl/project | gzip > index.json.gz

curl -X POST http://<host>:8000/index/upload \
     -H "Authorization: Bearer $MCP_INDEX_TOKEN" \
     -H "Content-Encoding: gzip" \
     --data-binary @index.json.gz
```

Требует переменную окружения `MCP_INDEX_TOKEN` на сервере (см. раздел Запуск).

---

## ⚠️ Важно: Почему только `code` параметр

**MCP всегда работает удалённо!** Сервер запущен в Docker на другом компьютере.

```
┌─────────────────┐         ┌─────────────────┐
│   Компьютер      │         │   MCP Сервер    │
│   разработчика  │   HTTP   │   (Docker)      │
│                 │  ──────> │                 │
│   Файл:         │          │   Нет доступа   │
│   C:\project\    │          │   к файловой    │
│   script.pl     │          │   системе!      │
└─────────────────┘          └─────────────────┘
```

**Проблема:**
- LLM получает путь `C:\project\script.pl`
- LLM "эмулирует" чтение файла
- Запускает MCP с `target: "C:\project\script.pl"`
- **MCP не видит этот файл!** Он на другом компьютере.

**Решение:**
LLM должен:
1. Прочитать файл **реально**
2. Отправить содержимое через параметр `code`

**Правильный флоу для LLM:**
```
Пользователь: "Проверь C:\project\script.pl"
     ↓
LLM: Читаю файл C:\project\script.pl...
     ↓
LLM: Отправляю в MCP:
     {
       "code": "use strict;\nuse warnings;\n...",
       "filename": "script.pl"
     }
```

### Настройка LLM (Kiloterm/Cline)

Добавь в system prompt:
```
ПРОВЕРКА PERL КОДА:
1. Всегда читай файл ПОЛНОСТЬЮ перед анализом
2. Используй ТОЛЬКО параметр 'code' для perlcritic_analyze
3. НИКОГДА не используй параметр 'target' - он не работает для удалённого MCP
```

## Запуск

### Docker (рекомендуется)
```bash
docker pull lenchik8/simple_mcp:latest

docker run -d --name mcp-drospr \
  -p 8000:8000 \
  -e MCP_INDEX_TOKEN=your_secret_token \
  -v mcp_data:/app/data \
  lenchik8/simple_mcp:latest
```

`-v mcp_data:/app/data` — сохраняет `index.db` между перезапусками контейнера.

### Локальная сборка
```bash
docker build -t mcp-drospr .
docker run -p 8000:8000 -e MCP_INDEX_TOKEN=your_secret_token mcp-drospr
```

### Из исходников
```bash
pip install -e .
python server.py
```

## Переменные окружения

| Переменная | Обязательна | Описание |
|------------|-------------|----------|
| `MCP_INDEX_TOKEN` | Для `/index/upload` | Bearer-токен для загрузки PPI-индекса |

## Структура проекта

```
mcp-drospr/
├── server.py                  # FastAPI, SSE, JSON-RPC, роутинг тулов
├── tools/
│   ├── perlcritic.py          # Perl::Critic анализ
│   ├── index_store.py         # SQLite хранилище PPI-индекса
│   └── build_index.pl         # Perl-скрипт сборки индекса (запускается на TeamCity)
├── data/
│   └── index.db               # SQLite индекс (создаётся после первой загрузки)
├── docs/
│   └── teamcity_setup.md      # Инструкция для TeamCity-администратора
├── Dockerfile
└── pyproject.toml
```

## Подключение к MCP клиенту

```json
{
  "mcpServers": {
    "DROSPR_JARVIS": {
      "url": "http://<IP>:8000",
      "transport": "sse"
    }
  }
}
```

## Docker Hub

https://hub.docker.com/r/lenchik8/simple_mcp

## GitHub

https://github.com/LENA-EE/simple_mcp

---

## Примеры промптов для анализа Perl кода

### Простой анализ файла
```
Проверь этот Perl файл на ошибки:
/path/to/script.pl
```

### Анализ с мягким уровнем (только критичные ошибки)
```
Проверь код, но покажи только серьёзные проблемы (severity 4-5)
```

### Анализ кода (отправка кода напрямую)
```
Проверь этот Perl код:
use strict;
...
```

### Анализ проекта
```
Проанализируй каждый .pl файл в папке /src/
```

### Ограничения удалённого MCP
- Анализ директорий возможен только если они доступны внутри контейнера
- Для полного аудита проекта - отправляй код файлов по одному