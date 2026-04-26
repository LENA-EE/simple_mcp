# Implementation Plan

Добавить новый MCP инструмент perlcritic_analyze для анализа Perl кода с помощью Perl::Critic, который принимает путь к файлу или директории, запускает perlcritic --verbose 11, парсит вывод и сохраняет результаты в JSON файл с timestamp, возвращая путь к файлу отчета.

[Overview]
Добавление нового инструмента perlcritic_analyze в существующий MCP сервер для статического анализа Perl кода.

Текущий MCP сервер имеет простую архитектуру с одним инструментом drospr, который возвращает фиксированное сообщение. Нужно добавить новый инструмент perlcritic_analyze, который будет выполнять статический анализ Perl кода с помощью Perl::Critic. Инструмент должен принимать путь к файлу или директории, запускать perlcritic --verbose 11, парсить вывод через regex, сохранять результаты в JSON файл с timestamp и возвращать путь к этому файлу. Реализация должна быть модульной с минимальными изменениями в существующем коде.

[Types]
Добавление новых структур данных для представления результатов анализа Perl::Critic.

- **PerlCriticIssue**: Структура для представления одной проблемы в коде
  - file: string (путь к файлу относительно целевого пути)
  - line: integer (номер строки с проблемой)
  - issue: string (описание проблемы)
  - severity: integer (1-5, нормализованная серьезность)
  - policy: string (название политики Perl::Critic)
  - snippet: string (фрагмент кода с проблемой)

- **PerlCriticReport**: Структура для полного отчета анализа
  - path: string (исходный путь к файлу или директории)
  - type: string ("file" или "directory")
  - issues: List[PerlCriticIssue] (список найденных проблем)
  - count: integer (количество проблем)
  - error: string | null (ошибка анализа или null)
  - report_file: string (путь к сохраненному JSON файлу)
  - timestamp: string (время создания отчета в ISO формате)

- **PerlCriticAnalyzeInput**: Входные параметры для инструмента
  - target: string (путь к файлу или директории для анализа)
  - recursive: boolean (true для рекурсивного анализа директорий, по умолчанию true)

[Files]
Создание нового модуля tools/perlcritic.py и минимальные изменения в server.py.

**Новые файлы:**

- `mcp_drospr/tools/perlcritic.py`: Основной модуль для анализа Perl::Critic
  - Функция `analyze_perl_critic(target, recursive=True)`: Основная функция анализа
  - Функция `parse_perlcritic_output(output, target_path)`: Парсинг вывода perlcritic
  - Функция `save_report(report, target_path)`: Сохранение отчета в JSON файл
  - Функция `run_perlcritic_command(target, recursive)`: Запуск команды perlcritic
  - Константы для regex паттернов парсинга

**Изменения в существующих файлах:**

- `mcp_drospr/server.py`: Добавить импорт нового модуля и обработку нового инструмента
  - Добавить импорт: `from tools.perlcritic import analyze_perl_critic`
  - В функции `handle_mcp_request` добавить обработку `perlcritic_analyze` в ветку `tools/call`
  - Обновить `tools/list` для включения нового инструмента с описанием схемы входных данных

**Структура каталогов:**

```
mcp_drospr/
├── server.py          (минимальные изменения)
├── tools/             (новая директория)
│   └── perlcritic.py  (новый файл)
├── pyproject.toml     (без изменений)
├── Dockerfile         (без изменений)
└── README.md          (обновить документацию)
```

[Functions]
Добавление новых функций в модуль perlcritic.py и обновление handle_mcp_request.

**Новые функции в tools/perlcritic.py:**

- `analyze_perl_critic(target: str, recursive: bool = True) -> dict`
  - **Параметры**: target (путь к файлу/директории), recursive (рекурсивный анализ)
  - **Возвращает**: Словарь с отчетом или ошибкой
  - **Описание**: Основная функция, координирующая весь процесс анализа

- `run_perlcritic_command(target: str, recursive: bool) -> tuple[str, int]`
  - **Параметры**: target (целевой путь), recursive (рекурсивный анализ)
  - **Возвращает**: (stdout, exit_code) вывод команды и код выхода
  - **Описание**: Запускает команду `perlcritic --verbose 11 <target>`

- `parse_perlcritic_output(output: str, target_path: str) -> list[dict]`
  - **Параметры**: output (вывод perlcritic), target_path (исходный путь)
  - **Возвращает**: Список словарей с проблемами
  - **Описание**: Парсит вывод perlcritic с помощью regex паттернов

- `save_report(report: dict, target_path: str) -> str`
  - **Параметры**: report (отчет), target_path (целевой путь)
  - **Возвращает**: Путь к сохраненному JSON файлу
  - **Описание**: Сохраняет отчет в JSON файл с timestamp в имени

- `normalize_severity(severity_str: str) -> int`
  - **Параметры**: severity_str (строка серьезности из perlcritic)
  - **Возвращает**: Нормализованное число 1-5
  - **Описание**: Нормализует серьезность к диапазону 1-5

**Изменения в server.py:**

- В функции `handle_mcp_request` добавить ветку для `perlcritic_analyze`:
  ```python
  elif params.get("name") == "perlcritic_analyze":
      target = params.get("arguments", {}).get("target")
      recursive = params.get("arguments", {}).get("recursive", True)
      result = analyze_perl_critic(target, recursive)
      return {
          "content": [{
              "type": "text",
              "text": f"Отчет сохранен: {result.get('report_file', 'N/A')}"
          }],
          "report": result
      }
  ```

[Classes]
Без изменений классов, так как текущая архитектура использует функциональный подход.

**Нет изменений классов:**

- Текущая реализация использует функциональный подход без классов
- Нет необходимости добавлять классы для этой функциональности
- Все функции будут реализованы как чистые функции в модуле

[Dependencies]
Добавление зависимости на наличие Perl::Critic в системе, но не в Python зависимостях.

**Зависимости системы (не Python):**

- `perlcritic` (Perl::Critic) должен быть установлен в системе
- Команда `perlcritic --version` должна быть доступна
- Perl 5.x должен быть установлен

**Python зависимости (без изменений):**

- Существующие зависимости остаются: `fastapi>=0.104.0`, `uvicorn[standard]>=0.24.0`
- Нет новых Python зависимостей, так как анализ выполняется через subprocess

**Проверка зависимостей:**

- Функция `analyze_perl_critic` будет проверять доступность `perlcritic`
- При отсутствии perlcritic возвращать ошибку: `{"error": "perlcritic not found", "report_file": null}`

[Testing]
Добавление тестов для нового модуля perlcritic.py.

**Новые тестовые файлы:**

- `tests/test_perlcritic.py`: Тесты для модуля perlcritic.py
  - Тест парсинга вывода perlcritic
  - Тест нормализации серьезности
  - Тест обработки ошибок (файл не найден, perlcritic недоступен)
  - Мок-тесты для избежания реального запуска perlcritic

**Обновление существующих тестов:**

- `test_server.py`: Добавить проверку наличия нового инструмента в списке
- Проверить, что server.py корректно импортирует новый модуль

**Тестовые данные:**

- Мок-вывод perlcritic для тестирования парсинга
- Тестовые Perl файлы для интеграционного тестирования (опционально)

[Implementation Order]
Последовательная реализация от модуля perlcritic.py к интеграции в server.py.

1. **Создать структуру каталогов**: Создать папку `mcp_drospr/tools/`
2. **Реализовать модуль perlcritic.py**: Создать все функции анализа
   - Сначала `run_perlcritic_command` и проверка доступности perlcritic
   - Затем `parse_perlcritic_output` с regex паттернами
   - Потом `normalize_severity` для нормализации серьезности
   - Затем `save_report` для сохранения JSON файла
   - Наконец `analyze_perl_critic` как основную функцию
3. **Интегрировать в server.py**: Добавить импорт и обработку инструмента
   - Добавить импорт модуля
   - Обновить `tools/list` с описанием нового инструмента
   - Добавить ветку в `tools/call` для `perlcritic_analyze`
4. **Обновить документацию**: Добавить описание нового инструмента в README.md
5. **Добавить тесты**: Создать тесты для нового модуля
6. **Протестировать интеграцию**: Запустить сервер и протестировать через curl
7. **Обновить Dockerfile**: При необходимости добавить Perl::Critic в образ (опционально)

**Критические моменты:**

- Regex парсинг вывода perlcritic должен быть надежным
- Обработка ошибок (файл не найден, директория недоступна, perlcritic недоступен)
- Формат имени файла отчета с timestamp для избежания перезаписи
- Возврат пути к файлу отчета, а не самого JSON
