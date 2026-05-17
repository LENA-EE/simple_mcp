# Implementation Plan: analyze_perl_diff

**Branch**: `001-analyze-perl-diff` | **Date**: 2026-05-17
**Spec**: `specs/001-analyze-perl-diff/spec.md`

## Summary

Добавить MCP-тул `analyze_perl_diff(diff, severity=1)` в `server.py`. Логика:
парсить unified diff, извлечь добавленные строки с их **реальными** номерами в
новом файле, прогнать через существующий `analyze_perl_critic`, переписать
`line` в каждом issue на реальный номер.

Главное архитектурное решение — **парсер diff'а с правильной нумерацией
строк**. Без этого фидбек бесполезен (бот не сможет привязать комментарий
к строке).

## Technical Context

- **Файлы изменения:**
  - `server.py` — регистрация тула в `tools/list`, обработка в `tools/call`
  - `tools/perlcritic.py` — переиспользуется `analyze_perl_critic` без изменений
  - **Новый файл:** `tools/diff_parser.py` — парсер unified diff (изолирован, легко тестируется)
- **Тестирование:** unit-тесты на `diff_parser.py` (приоритет), smoke в Docker
- **Зависимости:** только стандартная библиотека (`re` для hunk-хедеров)

## Что уже есть (переиспользуем)

```
tools/perlcritic.py            ← analyze_perl_critic вызываем без изменений
server.py                       ← добавляем тул рядом с perlcritic_analyze
```

Основная работа — корректный парсер unified diff. Сам анализ — это вызов
существующего тула.

## Project Structure

```text
specs/001-analyze-perl-diff/
├── spec.md          ✅ готово
├── plan.md          ← этот файл
└── _smoke.py        ← создать в конце фазы 3 (по образцу spec 003)

server.py            ← +регистрация analyze_perl_diff в tools/list и tools/call
tools/
├── perlcritic.py    ← не трогаем
└── diff_parser.py   ← новый файл, ~80 строк
```

---

## Фазы реализации

### Фаза 1 — Парсер unified diff (`tools/diff_parser.py`)

Изолированный модуль, проще тестируется. Контракт:

```python
def extract_added_lines(diff: str) -> list[tuple[str, int, str]]:
    """
    Returns list of (filepath, new_file_line_number, content) for each
    line starting with '+' in any hunk.

    Lines starting with '+++' (file header) are skipped.
    Hunk headers '@@ -X,Y +A,B @@' set the current new-file line counter.
    Context lines (starting with ' ') and removed lines (starting with '-')
    do not appear in the output but are used to advance the counter.
    """
```

**Алгоритм:**

```
current_file = None
current_new_line = None
for line in diff.split('\n'):
    if line.startswith('+++ b/'):
        current_file = line[6:]
        continue
    if line.startswith('+++ ') or line.startswith('--- '):
        continue
    if line.startswith('@@'):
        m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
        if m:
            current_new_line = int(m.group(1))
        continue
    if current_new_line is None:
        continue                          # before first hunk
    if line.startswith('+'):
        yield (current_file, current_new_line, line[1:])
        current_new_line += 1
    elif line.startswith('-'):
        pass                              # don't advance new-file counter
    else:
        current_new_line += 1             # context line
```

**Edge cases (покрыть тестами):**

- diff с `@@ -0,0 +1,N @@` (новый файл, все строки `+`)
- diff с переименованием (`rename from / rename to` без hunks)
- `Binary files differ` (нет hunks)
- множественные файлы (несколько `+++ b/...`)
- hunk без указания counts: `@@ -42 +52 @@` (одна строка)

### Фаза 2 — MCP-тул `analyze_perl_diff` в `server.py`

**Контракт:**

```
Input:  diff: str, severity: int = 1
Output: {path, type, issues, count, error, report_file, timestamp}
        — тот же формат, что у perlcritic_analyze
```

**Логика:**

```python
def analyze_perl_diff(diff: str, severity: int = 1) -> dict:
    added = list(extract_added_lines(diff))
    if not added:
        return {
            "path": None, "type": "diff", "issues": [], "count": 0,
            "error": None, "report_file": None,
            "timestamp": datetime.now().isoformat()
        }

    # Склейка для perlcritic + карта обратного маппинга
    blob_lines = [content for (_, _, content) in added]
    blob = "\n".join(blob_lines)
    line_map = {i + 1: (added[i][0], added[i][1]) for i in range(len(added))}
    # 1-based индекс в blob → (real_file, real_line)

    result = analyze_perl_critic(code=blob, filename="diff.pl", severity=severity)

    # Переписать line и file в issues
    for issue in result.get("issues", []):
        blob_line = issue.get("line")
        if blob_line in line_map:
            real_file, real_line = line_map[blob_line]
            issue["file"] = real_file
            issue["line"] = real_line

    result["type"] = "diff"
    result["path"] = None
    return result
```

**Регистрация в `server.py`:**

- В `tools/list` — рядом с `perlcritic_analyze`, только если `PERLCRITIC_AVAILABLE`
- В `tools/call` — новый `elif tool_name == "analyze_perl_diff"`

### Фаза 3 — Smoke test + документация

- `specs/001-analyze-perl-diff/_smoke.py` — по образцу `specs/003-.../_smoke.py`:
  - искусственный diff с одной строкой `+open(FILE, $path);` в hunk `@@ -42,3 +52,4 @@`
  - проверка: `issues[0].line == 52`, `issues[0].severity == 5`
  - запуск внутри Docker
- Обновить `README.md` — добавить `analyze_perl_diff` в раздел Инструменты с JSON-примером.

---

## Архитектурные решения

| Вопрос | Решение | Почему |
|--------|---------|--------|
| Парсер diff'а — в `server.py` или отдельным модулем? | Отдельный модуль `tools/diff_parser.py` | Изолированно тестируется, переиспользуется будущим `analyze_perl_diff_smart` |
| Номера строк в ответе — индексы blob'а или реальные? | Реальные (через карту) | Фидбек бесполезен без привязки к реальной строке файла |
| Что с issues, у которых `line` не нашёлся в карте? | Оставить как есть | Может быть multiline issue от perlcritic; не теряем информацию |
| Регистрировать тул даже без `perlcritic`? | Нет, только если `PERLCRITIC_AVAILABLE` | Симметрично с `perlcritic_analyze` |
| Принимать `filename` как у perlcritic_analyze? | Нет | `filename` берётся из `+++ b/<file>` хедера; параметр будет избыточен и source of truth раздвоится |
| Возвращать сводку по файлам, если diff содержит несколько? | На v1 — нет, плоский список issues с полем `file` | Минимизируем поверхность контракта; группировку делает PR-бот |

## Граница ответственности

```
analyze_perl_diff:
  ✅ парсит unified diff
  ✅ извлекает добавленные строки с реальными номерами
  ✅ прогоняет через perlcritic
  ✅ переписывает номера строк в issues на реальные

Не делает:
  ❌ не читает git (получает diff на входе)
  ❌ не комментирует в Bitbucket — это работа pr-reviewer-bot
  ❌ не знает про impact analysis — это analyze_before_commit (после Symbol Index)
  ❌ не фильтрует issues по severity порогу — это работа вызывающего (PR-бот / хук)
```

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| `perlcritic` падает на синтаксически неполном фрагменте | Средняя | Существующий `analyze_perl_critic` уже ловит parse error → `error` поле + пустые issues. Это ожидаемая «частичная картина», см. spec assumptions |
| Кривой diff (не unified) → парсер выдаёт мусор | Низкая | git везде использует unified; если получен мусор — `extract_added_lines` вернёт пустой список → тул вернёт `count=0` |
| Регресс в нумерации строк | Высокая (если без тестов) | Unit-тесты на парсер с покрытием edge cases — обязательное условие приёмки фазы 1 |
| Падение на огромных diff'ах | Низкая | Лимит на стороне MCP — можно добавить P2, сейчас полагаемся на здравый смысл вызывающего |

## Следующие шаги после реализации

После того как `analyze_perl_diff` в проде:

1. PR-бот переключается с `perlcritic_analyze` на `analyze_perl_diff` — меньше шума в PR.
2. Готовится спека `004-analyze-perl-diff-smart` — добавляет `full_file_code` из mcp-bitbucket для контекстного анализа.
3. После Symbol Index — спека `005-analyze-before-commit` поверх diff_smart + PPI.
