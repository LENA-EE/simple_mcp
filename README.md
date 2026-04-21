# MCP DROSPR Server

Минимальный MCP-сервер с инструментом `drospr` для проверки доступности.

## Описание

Сервер предоставляет один инструмент `drospr`, который возвращает текстовое сообщение:

```
Привет от MCP ДРОСПР! :)
```

Сервер работает через SSE (Server-Sent Events) транспорт на порту 8000 и может быть легко интегрирован с LiteLLM и другими MCP клиентами для удаленного подключения.

## Требования

- Python >= 3.10
- Зависимости: `fastapi`, `uvicorn` (минимальные зависимости)

## Установка

### Локальная установка

```bash
cd mcp_drospr
pip install .
```

### Запуск сервера

```bash
python server.py
```

Сервер запустится на `http://0.0.0.0:8000` и будет доступен для SSE соединений по адресу `/sse`.

## Docker

### Сборка образа

```bash
docker build -t mcp-drospr .
```

### Запуск контейнера

```bash
docker run -p 8000:8000 mcp-drospr
```

## Использование с MCP клиентом

Сервер работает через SSE транспорт:

- **URL**: `http://<IP>:8000/sse`
- **Протокол**: HTTP SSE (Server-Sent Events)
- **Методы**: GET для SSE соединения, POST для отправки запросов
- **Инструмент**: `drospr` (не требует параметров)

### Работа в KILO

```
{
  "$schema": "https://app.kilo.ai/config.json",
  "model": "openrouter/deepseek/deepseek-v3.2",//поменять
  "permission": {
    "bash": "allow"
  },
  "mcp": {
    "drospr": {
      "type": "remote",
      "url": "http://192.168.1.106:8000",
      "enabled": true,
      "timeout": 60000
    }
  }
}
```

### Интеграция с LiteLLM

Для использования с LiteLLM добавьте в конфигурацию:

```json
{
  "mcpServers": {
    "drospr": {
      "url": "http://<IP>:8000/sse",
      "transport": "sse"
    }
  }
}
```

### Тестирование MCP запросов

Вы можете протестировать сервер с помощью curl (JSON-RPC 2.0 формат):

```bash
# Проверка работоспособности
curl http://localhost:8000/

# Инициализация MCP соединения
curl -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}, "id": 1}'

# Получение списка инструментов
curl -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 2}'

# Вызов инструмента drospr
curl -X POST http://localhost:8000/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "drospr"}, "id": 3}'
```

Ожидаемые ответы:

```json
// Инициализация
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mcp-drospr", "version": "0.1.0"}}}

// Список инструментов
{"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "drospr", "description": "Возвращает приветственное сообщение от MCP ДРОСПР", "inputSchema": {"type": "object", "properties": {}, "required": []}}]}}

// Вызов drospr
{"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "Привет от MCP ДРОСПР! :)"}]}}
```

## Структура проекта

```
mcp_drospr/
├── server.py          # Основной код сервера
├── pyproject.toml     # Зависимости Python
├── Dockerfile         # Конфигурация Docker
├── README.md          # Документация
└── test_server.py     # Тестовый скрипт для проверки
```

## Тестирование

### Быстрая проверка зависимостей и кода

Перед запуском сервера можно выполнить проверку:

```bash
cd mcp_drospr
python test_server.py
```

Скрипт проверит:

- Наличие всех необходимых модулей (`mcp`, `fastapi`, `uvicorn`)
- Корректность кода `server.py`
- Наличие всех необходимых компонентов (инструмент `drospr`, порт 8000, хост 0.0.0.0, SSE эндпоинт)

### Запуск и проверка сервера

1. Установите зависимости (если еще не установлены):

   ```bash
   pip install mcp fastapi uvicorn
   ```

2. Запустите сервер:

   ```bash
   python server.py
   ```

3. Проверьте доступность эндпоинта:

   ```bash
   curl http://localhost:8000/sse
   ```

4. Используйте MCP клиент для вызова инструмента `drospr`

## Развертывание в банке

1. Соберите Docker образ
2. Перенесите образ в контур банка
3. Запустите контейнер на виртуальной машине
4. Сервер будет доступен по URL: `http://<IP>:8000/sse`
