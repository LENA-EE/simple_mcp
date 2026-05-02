# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

**DROSPR JARVIS** — MCP-сервер для анализа легаси Perl-кода внутри банковского периметра.
Разработчики подключаются из IDE через SSE, отправляют Perl-код, получают структурированный отчёт от Perl::Critic.

Это один из двух сервисов:
- `mcp-perlcritic` (этот репо) — анализ кода, MCP протокол
- `pr-reviewer-bot` (отдельный репо) — Bitbucket webhook, комментарии в PR

## Команды

```bash
# Локальный запуск
pip install -e .
python server.py

# Тесты
python test_server.py

# Docker
docker build -t mcp-drospr .
docker run -p 8000:8000 mcp-drospr

# Проверить что сервер живой
curl http://localhost:8000/health

# Проверить список тулов
curl -s -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Архитектура

```
server.py                  — FastAPI, SSE transport, JSON-RPC 2.0, роутинг тулов
tools/perlcritic.py        — запуск perlcritic, парсинг TSV, analyze_perl_critic()
```

**Два эндпоинта:**
- `GET /sse` — SSE стрим, IDE держит соединение открытым
- `POST /sse` — IDE отправляет JSON-RPC запрос, получает ответ синхронно

**Поток вызова тула:**
```
IDE → POST /sse {"method":"tools/call","params":{"name":"perlcritic_analyze","arguments":{"code":"..."}}}
  → handle_mcp_request()
  → analyze_perl_critic(code=...)       # tools/perlcritic.py
      → записывает code во временный файл
      → запускает perlcritic с TSV verbose форматом
      → парсит TSV → список issues
  → get_recommendation(policy)          # server.py, рекомендации на русском
  → возвращает JSON-RPC response
```

## Критически важные детали

**Severity в Perl::Critic — обратная интуиция:**
```
severity=1 → СТРОЖАЙШИЙ (все нарушения, включая стиль)
severity=5 → только КРИТИЧЕСКИЕ
```
Это противоположно тому как обычно понимается шкала. LLM-агенты часто путают.

**Удалённый режим (всегда в проде):**
MCP-сервер работает в Docker на виртуалке банка. Доступа к файловой системе разработчика нет.
- Параметр `code` — работает всегда, передаётся строкой
- Параметр `target` (путь) — работает только если путь доступен внутри контейнера

Агент/IDE должен читать файл локально и передавать содержимое через `code`. Не передавать путь.

**TSV формат:**
`perlcritic.py` использует кастомный verbose-формат `"%f\t%p\t%m\t%l\t%c\t%s\n"`. Причина — дефолтный формат не содержит полное имя policy, `--verbose 5` ломал regex на одиночных файлах. TSV: 6 полей, предсказуемо.

**`raw_output` намеренно не передаётся LLM** — засоряет контекст. Только структурированные issues.

**`PERLCRITIC_AVAILABLE`** — флаг на уровне модуля. Если `perlcritic` не найден в PATH — тул не регистрируется в `tools/list`. Это ожидаемое поведение (например, локальная разработка без Perl).

## TODO — точки роста проекта

Решения согласованы, в порядке приоритета:

### Шаг 1 — Symbol Index (JSON через PPI)
Обойти весь Perl-проект PPI → сохранить JSON-индекс функций/переменных/зависимостей.
При запросе агента "где функция X?" — lookup в JSON, 0 токенов, 100% точно.
Новый тул: `build_symbol_index(path)` + `lookup_symbol(name)`.

### Шаг 2 — `parse_structure` тул (PPI)
Принимает код одного файла, возвращает карту:
- функции с номерами строк и списком вызовов
- зависимости (`use`, `require`)
- глобальные переменные

Нужно для function-level chunking — агент запрашивает только нужную функцию (80 строк), не весь файл (1847 строк). Экономия ~90% токенов.

### Шаг 3 — Call Graph
Предсчитать граф вызовов по всему проекту → JSON.
Тул: `get_call_graph(function_name)` → кто вызывает, кого вызывает.
Без LLM, только JSON lookup.

### Шаг 4 — RAG (ChromaDB + Ollama)
Добавлять только когда JSON-индексов не хватит для семантических вопросов ("как работает биллинг?").
Дополнительная инфраструктура (2 контейнера), поэтому — после Шагов 1-3.

### Отдельный сервис — PR Reviewer Bot
Bitbucket webhook → читает diff → вызывает `perlcritic_analyze` этого MCP → пишет комментарии в PR.
Держится отдельным репо намеренно: разные зависимости, разный жизненный цикл.
Нужно создать `API.md` в этом репо — зафиксировать публичный контракт тулов.
