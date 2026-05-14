# Tasks: check_before_push

**Branch**: `002-check-before-push`
**Spec**: `specs/002-check-before-push/spec.md`
**Plan**: `specs/002-check-before-push/plan.md`

---

## Phase 1: Foundational — MCP-тул (блокирует всё остальное)

**Цель**: добавить `check_before_push` в `server.py`. Без этого хук нечего вызывать.

- [ ] T001 [US1] Добавить обработку `check_before_push` в `tools/list` в `server.py` — рядом с `perlcritic_analyze`, регистрировать только если `PERLCRITIC_AVAILABLE`
- [ ] T002 [US1] Добавить обработку `check_before_push` в `tools/call` в `server.py` — цикл по `files`, вызов `analyze_perl_critic()` для каждого, фильтрация по severity
- [ ] T003 [US1] Отфильтровать нарушения: `blockers` = severity >= 4, `warnings` = severity == 3, severity 1-2 — не включать в ответ
- [ ] T004 [US1] Собрать итоговый ответ: `allow_push`, `files_checked`, `files:[{filename, blockers, warnings}]`, текстовый отчёт с `❌`/`⚠`

**Checkpoint**: вызвать тул напрямую через curl, убедиться что `allow_push: false` на файле с `open(FILE, $path)` и `allow_push: true` на чистом файле.

```bash
curl -s -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"check_before_push",
       "arguments":{"files":[{"filename":"test.pl","code":"open(FILE,$f);"}]}}}'
```

---

## Phase 2: US1 + US2 — Bash pre-push хук

**Цель**: скрипт на машине разработчика который вызывает тул и блокирует пуш.

- [ ] T005 [US1] Создать файл `.githooks/pre-push` с shebang и базовой структурой (переменные `MCP_URL`, `SEVERITY`)
- [ ] T006 [US1] Получить список изменённых `.pl`/`.pm` файлов: `git diff --name-only @{u} HEAD` с fallback на `HEAD~1 HEAD` для первого пуша
- [ ] T007 [US1] Собрать JSON-массив `files` из содержимого найденных файлов через `python3 -c`
- [ ] T008 [US1] Отправить POST на MCP через `curl --max-time 30`, распарсить ответ
- [ ] T009 [US1] Exit 1 если `allow_push: false`, вывести список блокирующих нарушений с именем файла и строкой
- [ ] T010 [US2] Показать предупреждения severity=3 даже если пуш проходит (`allow_push: true`)
- [ ] T011 [US2] Если нет изменённых `.pl`/`.pm` файлов — завершиться молча, exit 0

**Checkpoint**: сделать `git push` с файлом содержащим `open(FILE, $path)` — пуш должен заблокироваться с читаемым сообщением.

---

## Phase 3: US3 — Несколько файлов

**Цель**: убедиться что несколько файлов обрабатываются корректно. Фактически уже работает после Phase 1 (цикл по `files`), но нужна проверка вывода.

- [ ] T012 [P] [US3] Проверить вывод при двух файлах: один чистый, второй с блокером — в выводе должно быть видно какой именно файл с проблемой
- [ ] T013 [P] [US3] Проверить что два чистых файла дают `allow_push: true` без лишних сообщений

---

## Phase 4: US4 — Fail open при недоступном MCP

- [ ] T014 [US4] В bash-скрипте: если `curl` завершился с ошибкой (exit != 0 или таймаут) — вывести `⚠ MCP недоступен — проверка пропущена` и exit 0

---

## Phase 5: Подключение к проекту

- [ ] T015 [P] Создать `setup.sh` в корне репозитория: `git config core.hooksPath .githooks` + `chmod +x .githooks/pre-push`
- [ ] T016 [P] Добавить `.githooks/pre-push` в `.gitignore` исключение (чтобы хук попал в репо)
- [ ] T017 [P] Обновить `README.md`: секция "Подключение pre-push хука" — одна команда `./setup.sh`

---

## Dependencies & Execution Order

```
T001 → T002 → T003 → T004   # фаза 1, строго последовательно
         ↓
T005 → T006 → T007 → T008 → T009   # фаза 2, строго последовательно
                              ↓
                        T010, T011  # параллельно между собой

T012, T013  # параллельно, после T009
T014        # после T009

T015, T016, T017  # параллельно между собой, после T009
```

## Параллельные возможности

- T012 и T013 — параллельно
- T015, T016, T017 — параллельно
- Phase 4 (T014) и Phase 5 (T015-T017) — параллельно между собой после T009

## Итог по файлам

| Файл | Что делаем |
|------|-----------|
| `server.py` | добавить тул `check_before_push` в `tools/list` и `tools/call` |
| `.githooks/pre-push` | новый файл, bash-скрипт |
| `setup.sh` | новый файл, одна команда подключения |
| `README.md` | добавить секцию про хук |
