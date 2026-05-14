# Implementation Plan: check_before_push

**Branch**: `002-check-before-push` | **Date**: 2026-05-14
**Spec**: `specs/002-check-before-push/spec.md`

## Summary

Добавить MCP-тул `check_before_push` (обёртка над `perlcritic_analyze`) и bash-скрипт
`.githooks/pre-push` который вызывает его перед `git push`. Severity 4-5 блокирует пуш,
severity 3 — предупреждение, 1-2 — молчим.

## Technical Context

**Language/Version**: Python 3.10+, Bash  
**Primary Dependencies**: FastAPI (уже есть), `tools/perlcritic.py` (уже есть), curl (на машине разработчика)  
**Storage**: N/A  
**Testing**: вызов тула напрямую через curl + ручной тест хука  
**Target Platform**: MCP-сервер — Docker/Linux; хук — машина разработчика (bash)  
**Constraints**: таймаут хука — 30с; если MCP недоступен — fail open (пуш проходит)

## Что уже есть (переиспользуем)

```
server.py               ← добавляем новый тул сюда
tools/perlcritic.py     ← analyze_perl_critic() не трогаем
```

`check_before_push` — это просто цикл по файлам с вызовом `analyze_perl_critic()`
и фильтрацией по severity. Новой логики минимум.

## Project Structure

```text
specs/002-check-before-push/
├── spec.md          ✅ готово
├── plan.md          ← этот файл
└── tasks.md         ← создаст /speckit.tasks

server.py            ← добавить тул check_before_push
.githooks/
└── pre-push         ← новый bash-скрипт
```

---

## Фазы реализации

### Фаза 1 — MCP-тул `check_before_push` в server.py

**Что делает тул:**

```
Input:  files=[{filename, code}, ...], block_severity=4
Output: {allow_push, files_checked, files:[{filename, blockers, warnings}], message}
```

**Логика:**
```python
for file in files:
    result = analyze_perl_critic(code=file["code"], filename=file["filename"], severity=1)
    blockers = [i for i in result["issues"] if i["severity"] >= block_severity]
    warnings = [i for i in result["issues"] if i["severity"] == 3]
    # severity 1-2 игнорируем — не включаем в ответ
```

`block_severity` передаётся параметром, дефолт=4. Позволяет настраивать без изменения кода.

**Где добавить в server.py:**
- В `tools/list` рядом с `perlcritic_analyze` — всегда если `PERLCRITIC_AVAILABLE`
- В `tools/call` — новый `elif tool_name == "check_before_push"`

**Формат ответа тула (текст для LLM/хука):**
```
PUSH CHECK RESULT
=================
Files checked: 2
Decision: BLOCKED

❌ Finance/Billing.pm
  Line 42: Two-argument open — severity 5
  Line 89: Bareword file handle — severity 4

⚠ Finance/Rates.pm
  Line 12: Magic number — severity 3 (warning only)

СТОП: исправь ошибки и попробуй снова.
```

---

### Фаза 2 — Bash-скрипт `.githooks/pre-push`

**Что делает скрипт:**
1. Получает список изменённых `.pl`/`.pm` файлов через `git diff`
2. Читает каждый файл локально
3. Собирает JSON: `[{filename, code}, ...]`
4. Отправляет POST на MCP через curl (таймаут 30с)
5. Парсит ответ через python3
6. Exit 1 если `allow_push: false`, exit 0 если true

**Получение изменённых файлов:**
```bash
# берём файлы которые есть в пуше но не на удалённой ветке
git diff --name-only @{u} HEAD 2>/dev/null | grep -E '\.(pl|pm)$'
# fallback если нет upstream (первый пуш):
git diff --name-only HEAD~1 HEAD | grep -E '\.(pl|pm)$'
```

**Таймаут и fail open:**
```bash
RESULT=$(curl -s --max-time 30 -X POST "$MCP_URL/sse" ...)
if [ $? -ne 0 ]; then
    echo "⚠ MCP недоступен — проверка пропущена"
    exit 0  # fail open
fi
```

**Конфигурация в начале скрипта:**
```bash
MCP_URL="http://192.168.1.106:8000"  # адрес виртуалки
SEVERITY=4                            # блокировать при >= этого
```

---

### Фаза 3 — Подключение к проекту

Одна команда для разработчика:
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

Скрипт `setup.sh` в корне репозитория делает это автоматически.

---

## Архитектурные решения

| Вопрос | Решение | Почему |
|--------|---------|--------|
| Новый тул или вызов `perlcritic_analyze` напрямую? | Новый тул `check_before_push` | Хук получает готовое решение (`allow_push`), не парсит severity сам |
| Фильтрация severity в тule или в хуке? | В туле (сервер) | Логика блокировки — часть бизнес-правила, не bash-скрипта |
| `block_severity` хардкод или параметр? | Параметр, дефолт=4 | Можно настраивать под проект без изменения кода |
| Fail open или fail closed? | Fail open | Падение MCP не должно парализовать команду |
| JSON-парсинг в хуке через что? | `python3 -c` | python3 есть на всех машинах, bash-парсинг JSON хрупкий |

## Граница ответственности

```
MCP-тул check_before_push:
  ✅ запустить perlcritic на каждом файле
  ✅ отфильтровать по severity
  ✅ вернуть allow_push + структурированный список

Bash pre-push хук:
  ✅ найти изменённые .pl/.pm файлы
  ✅ прочитать содержимое
  ✅ вызвать MCP
  ✅ вывести результат в консоль
  ✅ exit 0 или exit 1

Что НЕ делает тул:
  ❌ не читает файлы с диска (нет доступа к FS разработчика)
  ❌ не знает про git — только код строкой
```

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| `git push --no-verify` обходит хук | Высокая | Это ожидаемо — вопрос культуры, не технический |
| Первый пуш без upstream (`HEAD~1` fallback) | Средняя | Оба варианта получения diff покрыты в скрипте |
| Большой файл → медленный perlcritic | Низкая | Таймаут 30с на весь запрос |
| Windows-машина разработчика (нет bash) | Средняя | Вне скоупа v1, можно добавить PowerShell-версию потом |
