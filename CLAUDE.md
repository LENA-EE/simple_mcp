# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

**DROSPR JARVIS** — MCP-сервер для анализа легаси Perl-кода внутри банковского периметра.
Разработчики подключаются из IDE через SSE, отправляют Perl-код, получают структурированный отчёт от Perl::Critic.

Это часть трёхкомпонентной системы:

- `mcp-drospr` (этот репо) — анализ кода (perlcritic) + PPI символьный индекс
- `mcp-bitbucket` (отдельный) — git история, blame, файлы из Bitbucket
- `pr-reviewer-bot` (отдельный) — Bitbucket webhook, комментарии в PR

**Феникс (Qwen)** — локальная LLM внутри банковского периметра. Оркестрируется IDE (Kilo/opencode).
Получает только собранный контекст от MCP-серверов, никогда не получает сырые файлы целиком.

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
curl http://localhost:8000/

# Проверить список тулов
curl -s -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Архитектура системы целиком

```
IDE (Kilo / opencode)
        ↓
MCP оркестрация
  ├── mcp-drospr (этот репо)
  │     ├── perlcritic_analyze   ← качество кода
  │     ├── lookup_symbol        ← где определена функция
  │     ├── get_file_structure   ← карта файла
  │     └── get_callers          ← кто вызывает функцию
  ├── mcp-bitbucket
  │     ├── git blame            ← кто и когда менял
  │     ├── commit history       ← почему так сделано
  │     └── file content         ← прочитать конкретные строки
  └── Феникс (Qwen, локальная LLM)
        ← получает только маленький точный контекст
        ← никогда не получает файл целиком
```

**Ключевой принцип:** PPI говорит ЧТО важно в файле, Bitbucket говорит КТО и КОГДА менял,
Феникс получает только это. Токены экономятся, галлюцинаций меньше.

## Файлы этого репо

```
server.py                  — FastAPI, SSE transport, JSON-RPC 2.0, роутинг тулов
tools/perlcritic.py        — запуск perlcritic, парсинг TSV, analyze_perl_critic()
tools/index_store.py       — SQLite хранилище PPI-индекса, атомарная замена, lookup-функции
tools/build_index.pl       — Perl-скрипт сборки индекса через PPI (запускается на TeamCity)
data/index.db              — SQLite индекс (создаётся после POST /index/upload)
docs/teamcity_setup.md     — инструкция для TeamCity-администратора
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

### Шаг 1 — Symbol Index (централизованный, через TeamCity + PPI)

**Архитектура:**

```
Bitbucket push → TeamCity VCS Trigger
                      ↓
              build_index.pl (PPI)
              функции + use/require + globals + callers
                      ↓ gzip → POST /index/upload (Bearer token)
              MCP-сервер → SQLite (атомарная замена index_new.db → index.db)
                      ↓
              lookup_symbol / get_file_structure / get_callers
```

Разработчики ничего не устанавливают — TeamCity сам собирает и загружает индекс.

**SQLite схема:**

```sql
CREATE TABLE functions (name TEXT, file TEXT, package TEXT, line_start INT, line_end INT);
CREATE TABLE imports   (file TEXT, module TEXT, type TEXT, line INT);
CREATE TABLE globals   (file TEXT, varname TEXT);
CREATE TABLE calls     (caller_file TEXT, caller_line INT, callee_name TEXT);
CREATE INDEX idx_symbol ON functions(name);
CREATE INDEX idx_callee ON calls(callee_name);
```

**Статус реализации:**

- `build_index.pl` — написан, ждёт проверки на реальном `.pm` файле проекта
- `POST /index/upload` — реализован в `server.py`
- `lookup_symbol`, `get_file_structure`, `get_callers`, `index_status` — реализованы
- TeamCity конфиг — инструкция в `docs/teamcity_setup.md`, настраивает администратор

**Следующий шаг:** разработчик запускает `perl tools/build_index.pl One/Module.pm`
и показывает JSON-вывод. Особо смотрим раздел `calls` — там может быть шум.

**Граница ответственности между mcp-drospr и mcp-bitbucket:**

```
Вопрос                        mcp-drospr (PPI)    mcp-bitbucket
Где определена функция         ✅                  ❌
Что импортирует модуль         ✅                  ❌
Кто вызывает функцию           ✅ точно, из SQLite  ❌ text search — находит комментарии тоже
Кто менял файл / git blame     ❌                  ✅
Прочитать строки файла         ❌                  ✅
```

Итоговая формула:

- PPI SQLite → знает СТРУКТУРУ (где что, кто кого вызывает)
- MCP Bitbucket → достаёт СОДЕРЖИМОЕ (текст файлов, история)
- Феникс → ДУМАЕТ над тем что получил

**Новые тулы (MVP — все три):**

- `lookup_symbol(name)` → файл + строка (где определена функция)
- `get_file_structure(filepath)` → функции + импорты + globals файла
- `get_callers(name)` → кто реально вызывает функцию — только из PPI, не Bitbucket

Тулы регистрируются в `tools/list` только если `index.db` существует (аналогично `PERLCRITIC_AVAILABLE`).

**Атомарная замена индекса:**
При загрузке пишем в `index_new.db`, затем `os.replace("index_new.db", "index.db")`.
Читающие запросы не видят полуготовый индекс.

**Сбор callers в build_index.pl:**
PPI::Token::Word перед PPI::Structure::List → статические вызовы функций.
Покрывает ~70% реальных вызовов (динамику через AUTOLOAD/can() не поймать — ожидаемо).

**TeamCity Build Configuration "Perl Symbol Index Builder":**

- VCS Trigger на push в main
- Токен `MCP_INDEX_TOKEN` как Password-параметр (в логах показывается как `******`)
- `cpan PPI` на агенте один раз

### Шаг 2 — RAG (ChromaDB + Ollama)

Добавлять только когда индексов не хватит для семантических вопросов ("как работает биллинг?").
Дополнительная инфраструктура (2 контейнера), поэтому — после Шага 1.

```
Вопрос структурный ("где функция X") → PPI SQLite  (уже есть)
Вопрос семантический ("как работает биллинг") → RAG (ChromaDB + Ollama)
Никогда не смешивать потоки
```

### Шаг 3 — Новые тулы для анализа диффов и impact analysis

Добавлять после того как Шаг 1 (Symbol Index) работает.

---

#### analyze_perl_diff — анализ только изменений

```python
@mcp.tool()
def analyze_perl_diff(diff: str, filename: str = "input.pl") -> dict:
    """
    Анализирует только добавленные строки из git diff.
    Используй для быстрой проверки изменений в PR или перед коммитом.
    В отличие от analyze_perl_code — проверяет не весь файл,
    а только строки начинающиеся с + (новый код разработчика).
    Экономит токены, фокусирует внимание на изменениях.
    НЕ видит контекст — строка сама по себе ок, но в сочетании
    со старым кодом может быть проблема. Для контекста → analyze_perl_diff_smart.
    """
```

**Когда использовать:**

- JARVIS PR Bot — быстрая проверка что добавил разработчик
- pre-commit hook — быстрая проверка перед коммитом

**Как извлечь добавленные строки:**

```python
added_lines = []
for line in diff.split('\n'):
    if line.startswith('+') and not line.startswith('+++'):
        added_lines.append(line[1:])  # убираем +
code = '\n'.join(added_lines)
# передаём в analyze_perl_code(code=code, filename=filename)
```

---

#### analyze_perl_diff_smart — умный анализ с контекстом

```python
@mcp.tool()
def analyze_perl_diff_smart(
    diff: str,
    full_file_code: str,
    filename: str = "input.pl"
) -> dict:
    """
    Анализирует ВЕСЬ файл через perlcritic но разделяет результат
    на новые проблемы (в изменённых строках) и существующие (технический долг).
    Используй когда нужен полный контекст — видит проблемы которые возникают
    из-за сочетания нового и старого кода.
    full_file_code берёт из MCP Bitbucket (read_file).
    """
    # 1. Извлечь номера изменённых строк из diff header @@ -42,7 +52,8 @@
    # 2. Прогнать perlcritic по всему файлу
    # 3. Разделить issues по номерам строк:
    #    new_issues      — проблемы в изменённых строках
    #    existing_issues — были до PR, технический долг
```

**Возвращает:**

```json
{
  "new_issues": [...],
  "existing_issues": [...],
  "total_new": 3,
  "total_existing": 12
}
```

**Как JARVIS PR Bot использует:**

```python
# 1. MCP Bitbucket: read_file → full_file_code
# 2. analyze_perl_diff_smart(diff, full_file_code, filename)
# 3. Комментируем только new_issues
# 4. existing_issues игнорируем — технический долг, не наша вина
```

---

#### analyze_before_commit — мега-сеньор перед коммитом

Главный тул. Объединяет perlcritic + PPI impact analysis.
**Требует работающего Symbol Index (Шаг 1).**

```python
@mcp.tool()
def analyze_before_commit(
    diff: str,
    full_file_code: str,
    filename: str = "input.pl"
) -> dict:
    """
    Полный анализ перед git commit:
    1. perlcritic — стиль и синтаксис (через analyze_perl_diff_smart)
    2. PPI impact analysis — что сломается если изменить функцию
    Используй в pre-commit hook для полной проверки изменений.
    Требует index.db — регистрируется только если индекс существует.
    """
    # 1. perlcritic через analyze_perl_diff_smart
    # 2. Извлечь изменённые функции из diff
    # 3. Для каждой: get_callers() из SQLite
    # 4. Если callers > 5 → риск HIGH, предупреждение
```

**Что видит разработчик в терминале:**

```
git commit -m "fix get_rate"

🔍 Проверяем код...

📋 Стиль (perlcritic):
  billing.pm:42 [3] Длинная строка

⚠️  Impact analysis (PPI):
  Ты изменил get_rate()
  Вызывается в 12 местах:
    → calculate_commission()  Finance/Billing.pm:89
    → apply_discount()        Finance/Discount.pm:34
    ... и ещё 10 мест
  Риск: ВЫСОКИЙ — проверь обратную совместимость

❓ Продолжить коммит? (y/n):
```

**Логика блокировки:**

⚠️ ВАЖНО: severity в Perl::Critic — обратная шкала:

- severity=5 → КРИТИЧЕСКИЕ (самые серьёзные)
- severity=1 → СТРОЖАЙШИЕ (включая стиль)

```
perlcritic severity 5    → КРИТИЧЕСКИЕ  → БЛОКИРОВАТЬ
perlcritic severity 4    → СЕРЬЁЗНЫЕ    → БЛОКИРОВАТЬ
perlcritic severity 3    → СРЕДНИЕ      → предупреждение, не блокировать
perlcritic severity 1-2  → СТИЛЬ        → не показывать в hook вообще
PPI: callers > 5         → предупреждение + запрос подтверждения
PPI: callers 1-5         → информация
PPI: callers = 0         → "возможно мёртвый код?"
```

В коде: блокируем при `issue["severity"] >= 4`

---

#### Граница ответственности тулов для анализа диффов

```
Тул                        Когда использовать
──────────────────────────────────────────────────────────
analyze_perl_code          полный аудит модуля
analyze_perl_diff          быстрая проверка, нет контекста
analyze_perl_diff_smart    PR ревью с контекстом (нужен Bitbucket)
analyze_before_commit      pre-commit: стиль + impact (нужен SQLite)
check_before_push          git hook: только severity блокировка (уже есть)
```

**Для pre-commit hook — два режима:**

```bash
# Режим 1: только линтер (SQLite недоступен или нет индекса)
→ check_before_push (уже работает)

# Режим 2: линтер + impact analysis (SQLite есть)
→ analyze_before_commit (новый)

# Hook сам определяет режим:
if index.db exists → analyze_before_commit
else               → check_before_push
```

**Статус:** ❌ не реализовано
**Зависимость:** analyze_before_commit требует Шаг 1 (Symbol Index)
**Приоритет:** после Symbol Index и Guardian middleware

### Отдельный сервис — PR Reviewer Bot

Bitbucket webhook → читает diff → вызывает `perlcritic_analyze` этого MCP → пишет комментарии в PR.
Держится отдельным репо намеренно: разные зависимости, разный жизненный цикл.
**Статус: webhook настроен и протестирован на тестовом репозитории.**
Нужно создать `API.md` в этом репо — зафиксировать публичный контракт тулов.

---

## Стратегический контекст (AI DISRUPT PDLC v3.5)

Документ: AI DISRUPT PDLC v3.5, Кирилл Меньшов, апрель 2026.
Скинут руководством для ориентира. Наша система реализует ключевые принципы.

### Принцип 1 — Harness over Model (раздел 2.2)

Реверс-инжиниринг Claude Code показал: ~98,4% кодовой базы — детерминированная
инфраструктура harness, только ~1,6% — AI decision logic.

```
Феникс/Qwen     = model (заменяемая, ~1.6%)
mcp-drospr      = harness (perlcritic, PPI индекс, tool routing)
mcp-bitbucket   = harness (git history, blame, file content)
pr-reviewer-bot = harness (webhook, diff processing, PR comments)
```

Когда Феникс сменит модели — наш harness останется. Это capital asset.

### Принцип 2 — Context Engineering (раздел 2.10)

```
❌ Не делаем: отправить весь файл (2000 строк) в Феникс
✅ Делаем:    PPI говорит ЧТО важно → Bitbucket достаёт только это →
             Феникс получает 70 строк вместо 2000
```

Экономия токенов ~95% на запрос. `raw_output` намеренно не передаётся LLM — уровень 1 pipeline.

### Принцип 3 — Двухпетлевая модель (раздел 2.1)

```
Intent Loop:        Jira тикет → спецификация → acceptance criteria
Implementation Loop: код → тесты → PR → CI → деплой

Наша точка между петлями:
  JARVIS PR Bot = checkpoint качества перед merge
  MCP сервер   = контекст для агента в Implementation Loop
```

### Принцип 4 — Токеномика (раздел 5.5)

- perlcritic перед LLM: −70% токенов на PR ревью
- PPI индекс вместо чтения файлов: −95% токенов на символьные запросы
- `raw_output` не в контекст: −30% шума в ответах

### Принцип 5 — Orchestrator-Workers (раздел 2.9)

```
IDE (Kilo/opencode) = оркестратор
  → mcp-drospr     = worker (структура кода)
  → mcp-bitbucket  = worker (история и содержимое)
  → Феникс         = worker (объяснение и рекомендации)
```

### Что это значит для архитектурных решений

1. **Harness first**: логика в коде, не в промпте
2. **Just-in-time context**: давать агенту ровно столько сколько нужно
3. **Token budget**: каждый тул должен минимизировать токены на вызов
4. **AX-friendly**: структурированный JSON, никакого сырого текста в LLM
5. **Human in the loop**: необратимые действия требуют подтверждения

---

## Дорожная карта развития

```
L2 — AI-assisted    ← мы сейчас (JARVIS работает, PPI в разработке)
L3 — AI-augmented   ← цель: evals, audit trail, Guardian Agent
L4 — AI-native      ← горизонт: агент ведёт от тикета до PR
```

### Evals (сделать первым)

```python
evals = [
    {"question": "объясни process_billing", "expected": "функция, зависимости, контекст"},
    {"question": "что сломается если удалить get_rate", "expected": "12 мест, план"},
    # ... ещё 18 реальных вопросов от команды
]
# Оцениваешь ответы 1-5, фиксируешь baseline, прогоняешь после каждого изменения
```

### Audit trail

```python
{"ts": "2026-05-03T10:23:11Z", "user": "dev1@company.ru",
 "tool": "explain_function", "input_tokens": 280,
 "output_tokens": 420, "latency_ms": 1240}
```

### Guardian Agent (для банка не опция)

```python
class GuardianMiddleware:
    BLOCKED_PATTERNS = ["rm -rf", "DROP TABLE", "password", "secret"]

    def check(self, tool_name: str, arguments: dict) -> bool:
        # блокировать запросы к секретным данным
        # логировать все вызовы
        # эскалировать необратимые действия
```

### LangFuse observability (под вопросом)

Спросить на встрече с Фениксом: планируют ли встроенный observability?
Если нет — поднять LangFuse (MIT, docker-compose, ~4 CPU / 16GB RAM).
**Статус:** ⏸ ждём ответа от Феникса.

---

## Антипаттерны — чего не делать

**❌ Всё в один MCP сервер** — граница проведена правильно, не нарушать:

- mcp-drospr = структура кода
- mcp-bitbucket = история и содержимое
- pr-reviewer-bot = PR workflow

**❌ Fine-tuning вместо context engineering** — сначала улучшить контекст.
Fine-tuning дорого, медленно и устаревает при смене модели.

**❌ Автоматически применять изменения кода** — агент предлагает патч,
человек нажимает "применить", стандартный PR. Всегда.

---

## Текущий статус системы

```
Компонент              Статус        Следующее действие
───────────────────────────────────────────────────────────────
perlcritic_analyze     ✅ prod        —
check_before_push      ✅ prod        —
pr-reviewer-bot        ✅ webhook     протестирован на тестовом репо
POST /index/upload     ✅ готов       тест на реальном .pm
lookup_symbol          ✅ готов       тест на реальном .pm
get_file_structure     ✅ готов       тест на реальном .pm
get_callers            ✅ готов       тест callers — смотреть шум
build_index.pl         ✅ написан     запустить на One/Module.pm
TeamCity job           📋 инструкция  администратор настраивает
analyze_perl_diff      ❌ план        после Symbol Index
analyze_perl_diff_smart ❌ план       после Symbol Index
analyze_before_commit  ❌ план        после Symbol Index
Evals                  ❌ нет         написать 20 вопросов
Audit trail            ❌ нет         включить в LiteLLM
Guardian middleware    ❌ нет         после evals
RAG                    ⏸ отложен     после Шага 1 индекса
LangFuse               ⏸ отложен     ждём ответа от Феникса
```
