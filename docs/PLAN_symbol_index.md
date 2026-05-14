# План реализации: Symbol Index

## Проблема

MCP-сервер работает удалённо в Docker. Доступа к файловой системе разработчика нет.
Агент может анализировать только один файл за раз — передаёт код строкой.
Для больших Perl-проектов (500+ файлов) агент работает вслепую: не знает структуру,
галлюцинирует зависимости, не может ответить "где используется функция X".

## Решение

Разбить на два шага:

1. **Клиент (локально)** — скрипт обходит весь Perl-проект, строит JSON-индекс, заливает на MCP
2. **Сервер (MCP)** — хранит индекс, отвечает на запросы агента без LLM

---

## Что даёт индекс

| Вопрос агента | Сейчас | После |
|---|---|---|
| "где функция validate_amount?" | не знает | lookup в JSON → файл + строка, 0 токенов |
| "что вызывает calculate_fee?" | галлюцинирует | call_graph.json → точный ответ |
| "какие зависимости у billing.pl?" | нужно читать файл | symbol_index.json → мгновенно |
| "объясни модуль" | читает 1847 строк | читает только нужную функцию (80 строк) |

---

## Структура индекса

```json
{
  "meta": {
    "project": "my_perl_project",
    "indexed_at": "2026-05-02T10:00:00",
    "total_files": 47,
    "total_functions": 312
  },
  "symbols": {
    "validate_amount": {
      "file": "ProcessPayment.pl",
      "line": 45,
      "type": "sub",
      "calls": ["check_limit", "log_error"],
      "called_by": ["process_payment", "refund"],
      "uses_globals": ["$MAX_AMOUNT", "%CONFIG"]
    },
    "calculate_fee": {
      "file": "billing.pl",
      "line": 112,
      "type": "sub",
      "calls": ["get_rate", "apply_discount"],
      "called_by": ["invoice_generate"],
      "uses_globals": []
    }
  },
  "files": {
    "ProcessPayment.pl": {
      "package": "ProcessPayment",
      "dependencies": ["use POSIX", "use BankUtils", "require config.pl"],
      "total_lines": 847,
      "functions": ["validate_amount", "process_payment", "refund"]
    }
  }
}
```

---

## Новые файлы

```
mcp_drospr/
├── tools/
│   ├── perlcritic.py          ← уже есть
│   └── symbol_index.py        ← НОВЫЙ: тулы для работы с индексом
├── scripts/
│   └── build_index.py         ← НОВЫЙ: клиентский скрипт, запускается локально
├── server.py                  ← добавить 2 новых тула + хранилище индекса
```

---

## Шаг 1 — `scripts/build_index.py` (клиент, Python + PPI через subprocess)

Скрипт запускается разработчиком локально:
```bash
python scripts/build_index.py --path ./my_perl_project --server http://mcp-server:8000
```

**Что делает:**
1. Обходит все `.pl` и `.pm` файлы в указанной директории
2. Для каждого файла запускает Perl-скрипт через subprocess: `perl parse_perl.pl <file>`
3. Собирает результаты в единый `symbol_index.json`
4. POST на `http://mcp-server:8000/index/upload`

**Зависимости:**
- Python стандартная библиотека (subprocess, pathlib, json, argparse)
- Perl + PPI должны быть установлены локально (или в Docker на клиенте)
- Никаких новых Python-пакетов

**Perl-скрипт парсера** (`parse_perl.pl`, живёт внутри Docker-образа и локально):
```perl
use strict;
use warnings;
use PPI;
use JSON;

my $file = $ARGV[0];
my $doc  = PPI::Document->new($file) or die "Cannot parse $file";

my (@functions, @deps, %globals);

# Функции
for my $sub (@{ $doc->find('PPI::Statement::Sub') || [] }) {
    push @functions, { name => $sub->name, line => $sub->line_number };
}

# Зависимости
for my $inc (@{ $doc->find('PPI::Statement::Include') || [] }) {
    push @deps, $inc->module if $inc->module;
}

print encode_json({ functions => \@functions, dependencies => \@deps });
```

---

## Шаг 2 — `tools/symbol_index.py` (серверный модуль)

Два тула:

**`upload_index`** — принимает JSON-индекс, сохраняет в памяти сервера:
```python
def upload_index(index_json: str) -> dict:
    # валидирует структуру
    # сохраняет в INDEX_STORE (dict в памяти)
    # возвращает {"status": "ok", "files": 47, "symbols": 312}
```

**`lookup_symbol`** — ищет по индексу:
```python
def lookup_symbol(name: str) -> dict:
    # точный поиск по имени функции
    # возвращает: файл, строку, вызовы, кто вызывает
    # 0 запросов к LLM
```

---

## Шаг 3 — Регистрация в `server.py`

Добавить в `tools/list`:
```json
{
  "name": "upload_index",
  "description": "Загружает JSON-индекс Perl-проекта. Запускается один раз после build_index.py."
},
{
  "name": "lookup_symbol",
  "description": "Ищет функцию/переменную в индексе проекта. Возвращает файл, строку, зависимости. 0 токенов LLM."
}
```

Добавить хранилище индекса на уровне модуля:
```python
INDEX_STORE: dict = {}  # обновляется через upload_index
```

---

## Шаг 4 — Эндпоинт загрузки

Добавить в `server.py` отдельный REST-эндпоинт (не через MCP):
```python
@app.post("/index/upload")
async def upload_index_endpoint(request: Request):
    # принимает multipart или JSON
    # сохраняет в INDEX_STORE
    # возвращает статус
```

Это нужно для скрипта `build_index.py` — он не использует MCP-протокол, просто делает POST.

---

## Порядок реализации

| # | Что | Файл | Сложность |
|---|-----|------|-----------|
| 1 | Perl-парсер через PPI | `parse_perl.pl` | низкая |
| 2 | Клиентский скрипт | `scripts/build_index.py` | низкая |
| 3 | Серверный модуль тулов | `tools/symbol_index.py` | низкая |
| 4 | Эндпоинт загрузки + хранилище | `server.py` | низкая |
| 5 | Регистрация тулов в tools/list | `server.py` | низкая |
| 6 | Тест | `test_symbol_index.py` | низкая |

Всё реализуется без новых зависимостей в Python. Единственное новое требование — PPI должен быть установлен (уже есть в планах Docker-образа).

---

## Ограничения MVP

- Индекс хранится **в памяти** — при перезапуске Docker-контейнера теряется.
  Решение потом: сохранять на диск (`/data/index.json`) или Redis.
- `called_by` (кто вызывает функцию) — сложнее строить, можно добавить во второй итерации.
- PPI не всегда правильно парсит динамический Perl (`eval`, `AUTOLOAD`) — это ожидаемо для MVP.

---

## Как это выглядит в использовании

```
Разработчик один раз:
  python scripts/build_index.py --path /projects/billing --server http://10.0.0.5:8000
  → "Indexed 47 files, 312 symbols. Uploaded to MCP."

Агент в IDE:
  "где используется функция validate_amount?"
  → lookup_symbol("validate_amount")
  → {"file": "ProcessPayment.pl", "line": 45, "called_by": ["process_payment", "refund"]}
  → ответ без LLM, мгновенно
```
