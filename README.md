# MCP DROSPR Server

MCP-сервер для анализа Perl кода с помощью Perl::Critic.

## Инструменты

### `drospr`
Тестовый инструмент - возвращает приветственное сообщение.

```json
{"method": "tools/call", "params": {"name": "drospr", "arguments": {}}}
```
Результат: `"Привет от MCP ДРОСПР! :)"`

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
# Скачать образ
docker pull lenchik8/simple_mcp:latest

# Запустить
docker run -d --name mcp-drospr -p 8000:8000 lenchik8/simple_mcp:latest
```

### Локальная сборка
```bash
docker build -t mcp-drospr .
docker run -p 8000:8000 mcp-drospr
```

### Из исходников
```bash
pip install -e .
python server.py
```

## Структура проекта

```
mcp_drospr/
├── server.py          # FastAPI сервер
├── tools/
│   └── perlcritic.py  # Модуль анализа Perl::Critic
├── Dockerfile         # Docker образ
├── pyproject.toml     # Python зависимости
└── docs/             # Документация
```

## Подключение к MCP клиенту

```json
{
  "mcpServers": {
    "drospr": {
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