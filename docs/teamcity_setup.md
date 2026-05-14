# TeamCity: настройка Perl Symbol Index Builder

Новая Build Configuration которая собирает PPI-индекс Perl-проекта
и загружает его на MCP-сервер. Запускается автоматически после каждого push в main.

---

## 1. Создать Build Configuration

**Administration → Projects → [ваш проект] → Create Build Configuration**

- Name: `Perl Symbol Index Builder`
- Build configuration ID: `PerlSymbolIndexBuilder`

---

## 2. VCS Root

Подключить тот же VCS Root что использует основной билд проекта.
Checkout directory: стандартный (`%system.teamcity.build.checkoutDir%`).

---

## 3. Triggers

**Add Trigger → VCS Trigger**

- Trigger on changes in: все ветки → нет, только `main` (или `master`)
- Quiet period: 60 секунд (чтобы не запускаться на каждый коммит при пуше пачки)

---

## 4. Build Steps

### Step 1 — Установить PPI (если не установлен)

- Runner type: `Command Line`
- Run: `Executable with parameters`
- Command: `perl`
- Parameters: `-MCPAN -e "CPAN::Shell->notest('install', 'PPI', 'JSON::PP')"`
- Name: `Install PPI`

> Можно пропустить после первой успешной установки на агенте.
> Или поставить вручную на агенте: `cpan -i PPI JSON::PP`

---

### Step 2 — Собрать индекс

- Runner type: `Command Line`
- Script:
```bash
perl tools/build_index.pl %system.teamcity.build.checkoutDir% | gzip > perl_index.json.gz
```
- Name: `Build PPI index`
- Working directory: `%system.teamcity.build.checkoutDir%`

> `tools/build_index.pl` берётся из этого репо (mcp-drospr).
> Его нужно положить на агент или добавить этот репо как отдельный VCS Root.

---

### Step 3 — Загрузить на MCP-сервер

- Runner type: `Command Line`
- Script:
```bash
curl -f -X POST http://MCP_SERVER_HOST:8000/index/upload \
     -H "Authorization: Bearer %env.MCP_INDEX_TOKEN%" \
     -H "Content-Encoding: gzip" \
     -H "Content-Type: application/json" \
     --data-binary @perl_index.json.gz
```
- Name: `Upload index to MCP`

> Заменить `MCP_SERVER_HOST` на реальный адрес MCP-сервера.

---

## 5. Параметры (секреты)

**Administration → [Project] → Parameters → Add new parameter**

| Name | Kind | Value |
|------|------|-------|
| `env.MCP_INDEX_TOKEN` | Password | токен из `.env` MCP-сервера |

В логах сборки будет отображаться как `******`.

---

## 6. Agent Requirements (опционально)

Если Perl установлен не на всех агентах:

**Agent Requirements → Add requirement**
- Parameter name: `env.PERL_PATH` или `system.agent.name`
- Condition: equals → имя конкретного агента с Perl

---

## 7. Проверка

После первого запуска:
```bash
curl http://MCP_SERVER_HOST:8000/sse \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"index_status","arguments":{}}}'
```

Ожидаемый ответ:
```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "Индекс актуален на: 2026-05-02T03:00:00Z\nПроект: billing-core\nФайлов: 1247\nОшибок парсинга: 3"
    }]
  }
}
```
