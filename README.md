# MCP DROSPR Server

MCP-сервер для анализа Perl кода с помощью Perl::Critic.

## Инструменты

### `perlcritic_analyze`
Анализирует Perl код и возвращает структурированный отчёт.

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `target` | string | Путь к файлу или директории |
| `code` | string | Код для анализа (альтернатива target) |
| `severity` | int | Уровень строгости 1-5 (по умолчанию 1) |
| `recursive` | bool | Рекурсивный анализ директорий |
| `statistics` | bool | Показать статистику |
| `count_only` | bool | Только количество проблем |

**Severity levels:**
- 1 - Все проблемы (самый строгий)
- 2 - Серьёзные проблемы
- 3 - Потенциальные проблемы
- 4 - Структурные проблемы
- 5 - Критические ошибки

**Пример использования:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "perlcritic_analyze",
    "arguments": {
      "target": "/path/to/perl/file.pl",
      "severity": 1
    }
  }
}
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