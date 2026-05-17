# Implementation Plan: убрать утечку JSON-отчётов perlcritic на диск

**Branch**: `003-fix-perlcritic-report-leak` | **Date**: 2026-05-17
**Spec**: `specs/003-fix-perlcritic-report-leak/spec.md`

## Summary

Удалить из `tools/perlcritic.py` запись JSON-отчёта на диск. Поле `report_file` в ответе оставить как `None` для обратной совместимости.

## Technical Context

- **Файл изменения:** `tools/perlcritic.py`, функция `analyze_perl_critic()`
- **Строки:** ~246–272 (создание `report_filename`, выбор `report_path`, `json.dump`)
- **Объём:** ~25 строк удалить, 1 строка добавить (`"report_file": None`)
- **Тестирование:** `test_server.py` + ручной curl-проверка отсутствия файлов в `/tmp` после серии вызовов

## Изменения в коде

**Удаляется:**
```python
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
base_name = os.path.basename(target.rstrip("/\\")) or "analysis"
report_filename = f"perlcritic_report_{base_name}_{timestamp}.json"

if os.path.isdir(target):
    report_path = os.path.join(target, report_filename)
else:
    report_path = os.path.join(os.path.dirname(target), report_filename)
```

**И блок записи:**
```python
try:
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
except (IOError, OSError):
    report["report_file"] = None
```

**В `report` dict поле остаётся, но всегда `None`:**
```python
report = {
    "path": os.path.abspath(target),
    "type": target_type,
    "issues": issues,
    "count": len(issues),
    "error": None,
    "report_file": None,   # ранее — путь к JSON на диске; теперь не пишется (см. spec 003)
    "timestamp": datetime.now().isoformat()
}
```

## Проверки перед PR

1. **Грепнуть проект** на использование `report_file`:
   ```
   grep -r "report_file" --include="*.py" --include="*.sh"
   ```
   Убедиться, что нигде не читается с диска (только устанавливается в `perlcritic.py` и, возможно, передаётся в ответе).

2. **Локальный smoke test:**
   ```bash
   python test_server.py
   ```

3. **Ручная проверка:**
   ```bash
   docker build -t mcp-drospr-test .
   docker run --rm -d --name mcp-test -p 8000:8000 mcp-drospr-test

   # 10 раз дёрнуть тул
   for i in {1..10}; do
     curl -s -X POST http://localhost:8000/sse \
       -H "Content-Type: application/json" \
       -d '{"jsonrpc":"2.0","id":'$i',"method":"tools/call","params":{"name":"perlcritic_analyze","arguments":{"code":"open(FILE,$f);","filename":"test.pl"}}}' \
       > /dev/null
   done

   # Убедиться, что в /tmp нет perlcritic_report_*.json
   docker exec mcp-test ls /tmp/ | grep perlcritic_report || echo "OK — нет утечки"

   docker stop mcp-test
   ```

## Архитектурные решения

| Вопрос | Решение | Почему |
|--------|---------|--------|
| Удалить поле `report_file` из ответа полностью или оставить `None`? | Оставить `None` | Обратная совместимость с клиентами, которые могут проверять `if response.get("report_file")` |
| Удалить ли импорты `json` и `datetime`? | Не удалять | `datetime` используется в `timestamp` поле; `json` используется в других местах модуля при необходимости |
| Добавить флаг env `MCP_KEEP_REPORTS=1` для дебага? | Нет | Дебаг-режим — отдельная задача, не нужно сейчас. Audit trail в roadmap (P2) делается централизованно, не через файлы |
| Обернуть cleanup временного `.pl` в `try/finally`? | Отдельной задачей | Это P1, не входит в скоуп этой спеки (риск утечки только при unhandled exception, что редко) |

## Граница ответственности

```
В скоупе:
  ✅ Удалить запись JSON-отчёта на диск из analyze_perl_critic
  ✅ Поле report_file = None в ответе
  ✅ Smoke test что в /tmp ничего не растёт

Не в скоупе (отдельные задачи):
  ❌ tempfile.NamedTemporaryFile для временного .pl (race + path traversal) — P1
  ❌ try/finally для удаления временного .pl при exception — P1
  ❌ Ограничение размера code — P2
  ❌ Audit trail — P2, см. roadmap в CLAUDE.md / PROJECT_CONSTITUTION.md
```

## Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| `pr-reviewer-bot` или хук читают `report_file` с диска | Низкая | MCP-сервер удалённый — файлового доступа нет; грепнуть на всякий случай |
| Тесты валятся из-за изменения формы ответа | Низкая | Поле остаётся, просто всегда `None` |
| Кто-то внешний (внешний интегратор) полагается на наличие файла | Очень низкая | Контракт публичный только через JSON-RPC; файл на диске — внутренняя деталь, никогда не документировался |
