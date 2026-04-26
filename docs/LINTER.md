# Единый Perl-линтер

**ДРОСПР · Техническая документация · 2026**

Автоматическая проверка Perl-кода до отправки в Bitbucket на базе MCP + Git Pre-Push Hook.

| Параметр | Значение |
|----------|----------|
| Версия документа | 1.0 |
| Дата | 2026 |
| Автор | ДРОСПР |
| Статус | MVP · Готово к внедрению |
| Технологии | Python · FastAPI · Docker · Perl::Critic · Git hooks |

---

## 1. Обзор решения

Единый линтер — это автоматическая предпроверка Perl-кода перед отправкой в Bitbucket. Работает как Husky для JavaScript: разработчик делает git push, хук срабатывает автоматически, отправляет изменённые файлы на MCP-сервер, получает результат анализа. Если найдены критичные ошибки — пуш блокируется.

**Ключевое:** MCP-сервер находится на виртуалке и недоступен для прямого обхода файловой системы проекта. Поэтому хук читает файлы локально и передаёт код строкой — MCP получает только содержимое, не пути.

Разработчику не нужно устанавливать Perl::Critic — он работает внутри Docker-контейнера MCP-сервера.

### 1.1 Как это работает

```
Разработчик → git push
    ↓
pre-push hook (bash скрипт в .githooks/)
    ↓
git diff → берёт только изменённые .pl и .pm файлы
    ↓
curl → отправляет код строкой на MCP-сервер (виртуалка)
    ↓
MCP → perlcritic внутри Docker → JSON с проблемами
    ↓
severity >= 4 найден → пуш ЗАБЛОКИРОВАН + список ошибок
severity < 4 или нет ошибок → пуш ПРОХОДИТ
```

### 1.2 Компоненты системы

| Компонент | Где живёт | Что делает |
|-----------|-----------|------------|
| pre-push hook | Машина разработчика (.githooks/) | Перехватывает git push, читает файлы, вызывает MCP |
| MCP-сервер | Виртуалка банка · Docker · :8000 | Принимает код, прогоняет perlcritic, возвращает JSON |
| perlcritic | Внутри Docker-образа MCP | Анализирует Perl-код по правилам Perl::Critic |
| Bitbucket | Инфраструктура банка | Принимает пуш только если хук вернул exit 0 |
| LLM (опционально) | Феникс · Qwen через MCP | Объясняет найденные проблемы на русском языке |

---

## 2. Требования

### 2.1 Серверная часть (виртуалка банка)

| Требование | Версия | Статус |
|------------|--------|--------|
| Python | 3.10+ | Требуется |
| Docker | 20.0+ | Требуется |
| FastAPI + Uvicorn | последняя | В Docker образе |
| Perl | 5.x | В Docker образе |
| Perl::Critic | 1.150+ | В Docker образе |
| Порт 8000 | открыт для разработчиков | Настройка сети |

### 2.2 Машина разработчика

| Требование | Версия | Зачем |
|------------|--------|-------|
| Git | 2.x+ | Для работы хука |
| bash | любая | Выполнение хука |
| curl | любая | HTTP запрос к MCP |
| python3 | 3.x | Парсинг JSON в хуке |
| Доступ к MCP URL | http://виртуалка:8000 | Сетевой доступ |
| Perl::Critic | **НЕ нужен** | Работает в Docker на сервере |

Разработчику нужна только одна команда для подключения:
```bash
git config core.hooksPath .githooks
```

---

## 3. Этапы реализации

### Этап 1: Новый тул в MCP-сервере · 0.5–1 день

Доб��вить тул `check_before_push` который принимает список файлов с кодом, прогоняет каждый через perlcritic и возвращает решение: разрешить пуш или заблокировать.

**Код тула (добавить в server.py):**

```python
@mcp.tool()
def check_before_push(files: list[dict], severity: int = 4) -> dict:
    """
    Проверяет Perl файлы перед git push.
    files: [{filename: str, code: str}]
    severity: 1-5, блокировать при >= этого значения
    """
    results = []
    has_blocker = False
    for file in files:
        analysis = analyze_perl_code(
            code=file["code"],
            filename=file["filename"]
        )
        blockers = [
            i for i in analysis["issues"]
            if i["severity"] >= severity
        ]
        if blockers:
            has_blocker = True
        results.append({
            "filename": file["filename"],
            "blockers": blockers,
            "warnings": [i for i in analysis["issues"] if i["severity"] < severity],
            "total": len(analysis["issues"])
        })
    return {
        "allow_push": not has_blocker,
        "files_checked": len(files),
        "files": results,
        "message": "OK — код проверен" if not has_blocker
                   else "СТОП — найдены критичные проблемы"
    }
```

**Проверка тула:**

```bash
curl -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call",
       "params":{"name":"check_before_push",
       "arguments":{"files":[{"filename":"test.pl","code":"open(FILE,$f);"}]}},
       "id":1}'
```

Ожидаемый ответ: `allow_push: false`, найдена проблема `Two-argument open`

### Этап 2: Git pre-push hook · 1 день

Создать bash-скрипт который перехватывает git push, собирает изменённые Perl файлы и вызывает MCP-серв��р.

**Структура файлов в репозитории:**

```
perl-project/
  .githooks/
    pre-push          # ← bash скрипт (создаём здесь)
  src/
    module.pl
  README.md
```

**Содержимое .githooks/pre-push:**

```bash
#!/bin/bash
# pre-push hook — проверка Perl кода через MCP

MCP_URL="http://192.168.1.106:8000"  # ← поменять на адрес виртуалки
SEVERITY=4                            # ← блокировать при severity >= 4

# берём только изменённые .pl и .pm файлы
CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -E '\.(pl|pm)$')

if [ -z "$CHANGED" ]; then
    echo "ℹ Perl файлов не изменено — пропускаем проверку"
    exit 0
fi

echo "🔍 Проверяем Perl код через MCP..."

# собираем JSON массив файлов
FILES_JSON="["
FIRST=true
for FILE in $CHANGED; do
    if [ -f "$FILE" ]; then
        CODE=$(cat "$FILE" | python3 -c "
import sys, json
print(json.dumps(sys.stdin.read()))
")
        [ "$FIRST" = true ] && FIRST=false || FILES_JSON="$FILES_JSON,"
        FILES_JSON="${FILES_JSON}{"filename":"$FILE","code":$CODE}"
    fi
done
FILES_JSON="${FILES_JSON}]"

# вызываем MCP тул
RESULT=$(curl -s -X POST "$MCP_URL/sse" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",
       \"params\":{\"name\":\"check_before_push\",
       \"arguments\":{\"files\":$FILES_JSON,\"severity\":$SEVERITY}},
       \"id\":1}")

# парсим результат
ALLOW=$(echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
text = data[\"result\"][\"content\"][0][\"text\"]
result = json.loads(text)
print(result[\"allow_push\"])
")

if [ "$ALLOW" = "False" ]; then
    echo "❌ Пуш заблокирован — найдены критичные проблемы:"
    echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
text = data[\"result\"][\"content\"][0][\"text\"]
result = json.loads(text)
for f in result[\"files\"]:
    if f[\"blockers\"]:
        print(f\"\\n📁 {f['filename']}:\")
        for b in f[\"blockers\"]:
            print(f\"  - [{b['severity']}] {b['issue']} (line {b['line']})\")
"
    exit 1
fi

echo "✅ Пуш разрешён — код прошёл проверку"
exit 0
```

### Этап 3: Подключение к проекту · 0.5 дня

Создать скрипт установки и README для разработчиков.

**setup.sh:**

```bash
#!/bin/bash
# Подключение pre-push хука к проекту

# копируем хук
mkdir -p .githooks
cp pre-push .githooks/
chmod +x .githooks/pre-push

# указываем git использовать наши хуки
git config core.hooksPath .githooks

echo "✅ Pre-push hook установлен!"
echo "Теперь при git push будет проверяться Perl код"
```

---

## 4. Преимущества решения

1. **Единый стандарт** — все разработчики используют одинаковые правила проверки
2. **Без установки** — разработчику не нужен Perl::Critic, работает на сервере
3. **Блокировка критичных** — можно настроить уровень severity для блокировки
4. **LLM-объяснения** — опционально объясняет проблемы на русском через Феникс/Qwen
5. ** Husky для Perl** — аналог популярного инструмента для JS

---

## 5. Развертывание

### На виртуалке банка:

```bash
# скачать Docker образ
docker pull lenchik8/simple_mcp:latest

# запустить
docker run -d --name mcp-drospr -p 8000:8000 lenchik8/simple_mcp:latest

# проверить
curl http://localhost:8000/
```

### У разработчика:

```bash
# клонировать проект
git clone git@bitbucket.org:bank/perl-project.git
cd perl-project

# установить хук
./setup.sh

# работать как обычно
git add .
git commit -m "fix: исправление ошибки"
git push  # ← автоматическая проверка!
```