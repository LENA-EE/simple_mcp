# CLAUDE.md — Исполнительный контракт агента

**Стандарт:** [AI Engineering Standard (AES) v1.2](https://github.com/LENA-EE/AI-Engineering-Standard-AES)
**Compliance Level:** AES-L2 (конституция + approved spec.md + plan.md в `specs/`)
**Цель в зрелости:** AES-L3 (CLAUDE.md настроен, 0 AES violations в последнем PR)

> Этот файл — нормативный контракт между Human Architect и AI-агентом для репозитория `mcp-drospr`.
> Базовые правила наследуются из AES v1.2 (`CLAUDE.md` стандарта) — см. ссылку выше. Здесь зафиксированы **проектно-специфичные дополнения и обязательные нотификации**, которые ловят реальные ошибки в этом проекте.
>
> При конфликте: `PROJECT_CONSTITUTION.md` > этот файл > AES v1.2 baseline > предположения агента.

---

## 0. Required Inputs

Перед любой реализацией агент **MUST** прочитать:

1. [`PROJECT_CONSTITUTION.md`](PROJECT_CONSTITUTION.md) — продуктовый и архитектурный авторитет проекта.
2. Этот файл целиком.
3. Релевантные документы из [`docs/`](docs/) и [`specs/`](specs/) под текущую задачу.

Если конституция отсутствует или противоречит запросу — агент **MUST STOP** и попросить разъяснение.

---

## 1. Roles & Authority

Наследуется из AES v1.2 §1 без изменений.

> The Agent executes decisions — it does not originate them.

В контексте `mcp-drospr`:

- Human Architect владеет продуктовыми и архитектурными решениями (см. roadmap в `PROJECT_CONSTITUTION.md`).
- Агент работает как senior software engineer, исполняющий согласованные шаги.
- **Феникс/Qwen не является агентом-исполнителем этого контракта** — Феникс получает от MCP только данные и отвечает разработчику. Контракт распространяется на coding-агентов в IDE (Claude Code, Kilo, opencode и т. п.).

---

## 2. Agent State Model

Наследуется из AES v1.2 §3 без изменений:

```
DISCOVERY → PLANNING → EXECUTION → REVIEW → DEPLOYMENT
```

Переходы между состояниями требуют артефактов — см. AES v1.2 §4.

Для нетривиальной фичи `spec.md` и `plan.md` хранятся в `specs/<NNN>-<slug>/` (см. существующие `001-analyze-perl-diff`, `002-check-before-push`).

---

## 3. Command Interface

Стандартные команды AES применяются «как есть» (см. AES v1.2 §5). Особенности проекта:

- `/explore` — обязательно показать, какие тулы регистрируются на старте при текущем окружении (наличие `perlcritic` в PATH и `data/index.db`).
- `/spec` и `/plan` — артефакты складываются в `specs/<NNN>-<slug>/spec.md` и `plan.md`.
- `/deploy` — финальная проверка обязательно включает: smoke test `test_server.py`, ручной `curl POST /sse` с `tools/list`, проверку, что `raw_output` не утекает в ответ.

---

## 4. Проектно-специфичные правила исполнения

Эти правила **дополняют** AES v1.2 §6 (Execution Constraints) и являются обязательными для `mcp-drospr`. Они отражают реальные ловушки, в которые проваливались люди и LLM в прошлом.

### 4.1 Severity в Perl::Critic — обратная шкала

```
severity=1 → СТРОЖАЙШИЙ (все нарушения, включая стиль)
severity=5 → только КРИТИЧЕСКИЕ
```

Агент **MUST** учитывать инверсию при работе с любой логикой severity. Блокировка push — `issue["severity"] >= 4`. Никогда не «исправлять» это на `<= 2`, даже если код выглядит подозрительно.

### 4.2 Параметр `code` — единственный продовый

MCP-сервер работает удалённо. Агент **MUST**:

- передавать содержимое файла через параметр `code` (читая файл локально на стороне IDE);
- **MUST NOT** использовать параметр `target` (путь) в продовых сценариях.

`target` оставлен для локальной отладки внутри контейнера; в проде он не работает и приводит к «сервер не видит файл».

### 4.3 `raw_output` никогда не отдаётся LLM

`tools/perlcritic.py` возвращает `raw_output` для отладки. Агент **MUST NOT**:

- включать `raw_output` в ответ MCP-клиенту;
- пробрасывать его в контекст LLM.

Это уровень-1 фильтрации контекста. Засоряет окно, теряется структура.

### 4.4 TSV verbose-формат `perlcritic`

`"%f\t%p\t%m\t%l\t%c\t%s\n"` — 6 полей. Менять формат разрешено только с одновременной правкой парсера в `tools/perlcritic.py` и тестов. Дефолтный формат и `--verbose 5` — **запрещены** (ломали regex на одиночных файлах в прошлом).

### 4.5 Атомарная замена индекса

Запись индекса — только через `index_new.db` + `os.replace`. Менять алгоритм без эквивалентной гарантии (читающие запросы не видят полуготовый индекс) — **запрещено**.

### 4.6 Контракт `build_index.pl` → `index_store.py`

JSON-схема вывода `tools/build_index.pl` (`functions / imports / globals / calls`) — публичный контракт. TeamCity-пайплайн на него завязан. Любое изменение схемы **MUST** идти через миграцию:

1. Спецификация изменений в `specs/`.
2. Согласование с Human Architect.
3. Согласованное обновление `index_store.py`, индексов SQLite и job-конфига TeamCity.

### 4.7 Регистрация тулов в `tools/list`

- `perlcritic_analyze` регистрируется только при `PERLCRITIC_AVAILABLE = True`.
- `lookup_symbol`, `get_file_structure`, `get_callers`, `index_status` регистрируются только при наличии `data/index.db`.

Это ожидаемое поведение для локальной разработки без Perl/индекса. Агент **MUST NOT** «чинить» отсутствие тулов добавлением статической регистрации.

### 4.8 Границы между MCP-серверами

`mcp-drospr` отвечает только за **структуру** Perl-кода. **Запрещено** добавлять сюда:

- чтение git blame / commit history (→ `mcp-bitbucket`);
- чтение содержимого файлов из Bitbucket (→ `mcp-bitbucket`);
- PR-комментирование, вебхуки Bitbucket (→ `pr-reviewer-bot`).

Если запрос пользователя пересекает границу — агент **MUST** явно указать на это и предложить разнести по правильным сервисам.

---

## 5. Universal Engineering Rules

Наследуется из AES v1.2 §7 без изменений. Точечные уточнения:

- **Типизация Python** — использовать аннотации в новом коде; `# type: ignore` запрещён (см. §6 ниже).
- **Изоляция внешних зависимостей** — `perlcritic` (subprocess) и SQLite инкапсулированы в `tools/perlcritic.py` и `tools/index_store.py` соответственно. Прямые вызовы из `server.py` запрещены.
- **Конфигурация через переменные окружения** — `MCP_INDEX_TOKEN` единственная обязательная; новые секреты добавлять только через env.

---

## 6. Forbidden Practices

К стандартному списку AES v1.2 §8 добавляются:

```
❌ Хардкод банковских IP / хостнеймов / URL prod-окружений
❌ Реальный Perl-код банка в фикстурах и тестах
❌ Прямой вызов perlcritic из server.py в обход tools/perlcritic.py
❌ Прямые SQL-запросы к index.db из server.py в обход tools/index_store.py
❌ raw_output в ответе MCP-клиенту или в контексте LLM
❌ Параметр target в продовых вызовах
❌ Подавление PERLCRITIC_AVAILABLE / отсутствия index.db (статическая регистрация тулов)
❌ Изменение TSV verbose-формата без согласованного обновления парсера и тестов
❌ Изменение JSON-схемы build_index.pl без миграции index_store + TeamCity
```

---

## 7. Protected Resources

Базовый набор AES v1.2 §10 действует целиком. Проектно-специфичные дополнения — изменять **только при явной просьбе человека как главной цели задачи**:

### Данные и индекс

```
❌ data/index.db                 — атомарная замена, не править руками
❌ data/*.db / *.db-journal       — артефакты SQLite, не коммитить
```

### Контракты с внешними системами

```
❌ tools/build_index.pl           — TeamCity-job завязан на формат вывода
❌ tools/perlcritic.py: TSV format — парсер и тесты завязаны на 6 полей
❌ tools/index_store.py: схема     — миграция требует обновления build_index.pl
❌ .githooks/pre-push              — раздаётся разработчикам через setup.sh
❌ setup.sh                        — onboarding-скрипт для новых разработчиков
```

### Инфраструктура

```
❌ Dockerfile                     — образ публикуется на Docker Hub
❌ pyproject.toml                 — зависимости только добавлять; удаление/даунгрейд только по запросу
❌ MCP_INDEX_TOKEN                — Bearer-токен, никогда в код, никогда в логи
```

Если задача косвенно требует трогать защищённый ресурс — агент **MUST** остановиться и подтвердить с человеком, прежде чем продолжать.

---

## 8. Operational Commands (developer reference)

Не часть нормативного контракта, но агент **MAY** использовать эти команды для проверок в EXECUTION/REVIEW:

```bash
# Локальный запуск
pip install -e .
python server.py

# Тесты
python test_server.py

# Docker
docker build -t mcp-drospr .
docker run -p 8000:8000 mcp-drospr

# Сервер живой?
curl http://localhost:8000/

# Список тулов в текущем окружении
curl -s -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

## 9. Failure & Stop Conditions

Наследуется из AES v1.2 §11. Дополнительные триггеры стопа для `mcp-drospr`:

- задача требует обхода `tools/perlcritic.py` / `tools/index_store.py`;
- задача требует менять TSV-формат или JSON-схему индекса;
- задача предполагает использование `target` параметра в проде;
- запрос пересекает границу с `mcp-bitbucket` или `pr-reviewer-bot`.

---

## 10. Priorities

Наследуется из AES v1.2 §12:

1. Works
2. Secure
3. Typed
4. Readable
5. Testable
6. Optimized

В проектном контексте «Secure» включает: банковские данные не утекают, `MCP_INDEX_TOKEN` не логируется, удалённый режим соблюдается.

---

## 11. Design Principle

> Humans design systems. AI executes them.
> PPI говорит ЧТО важно. Bitbucket говорит КТО и КОГДА менял. Феникс ДУМАЕТ. Агент-исполнитель — соблюдает контракт.

---

*Conforms to [AES v1.2](https://github.com/LENA-EE/AI-Engineering-Standard-AES). Compliance Level: L2 → L3 (target).*
