#!/usr/bin/env python3
"""
Модуль для анализа Perl кода с помощью Perl::Critic.

ВАЖНО про severity в Perl::Critic (все LLM часто путают это!):
  severity=1 = САМЫЙ СТРОГИЙ (все нарушения, включая стилистические)
  severity=2 = строгий
  severity=3 = средний
  severity=4 = мягкий (только серьёзное)
  severity=5 = ТОЛЬКО КРИТИЧЕСКИЕ ошибки
  Это ПРОТИВОПОЛОЖНО интуиции.

Про удалённый режим работы MCP:
  MCP-сервер работает на виртуалке в Docker. Прямого доступа к файловой
  системе разработчика нет. Поэтому:
  - Параметр code (строка кода) — рекомендуется, работает всегда.
    Snippet извлекается из переданного кода по номеру строки.
  - Параметр target (путь) — работает только если путь доступен
    внутри контейнера. При удалённом деплое snippet будет пустым.
"""

import re
import os
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def find_perlcritic_path() -> Optional[str]:
    """Ищет perlcritic в системе через PATH."""
    import shutil
    return shutil.which("perlcritic")


def check_perlcritic_available() -> bool:
    """Проверяет, доступен ли perlcritic в системе."""
    perlcritic_path = find_perlcritic_path()
    if not perlcritic_path:
        return False
    try:
        result = subprocess.run(
            [perlcritic_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def run_perlcritic_command(
    target: str,
    recursive: bool = True,
    severity: int = 1,
    statistics: bool = True,
    count_only: bool = False
) -> Tuple[str, int]:
    """Запускает perlcritic с кастомным TSV verbose-форматом.

    Используем TSV вместо дефолтного формата или --verbose 5:
    - Дефолтный формат: нет полного имени policy, только ссылка на PBP (книгу).
    - --verbose 5: добавлял путь к файлу в начало строки — regex ломался
      на строках без пути (например анализ одного файла).
    - TSV ("%f\t%p\t%m\t%l\t%c\t%s\n"): каждая ошибка = одна строка,
      ровно 6 полей, предсказуемый формат.

    Поля TSV:
      %f = имя файла (важно при анализе директории)
      %p = полное имя policy (InputOutput::ProhibitTwoArgOpen)
      %m = текст сообщения об ошибке
      %l = номер строки
      %c = колонка
      %s = severity числом

    ВАЖНО: severity=1 строжайший (все нарушения), severity=5 только критические.
    """
    if not os.path.exists(target):
        return f"Error: Path {target!r} does not exist", 1

    severity = max(1, min(5, severity))
    is_dir = os.path.isdir(target)

    perlcritic_path = find_perlcritic_path()
    if not perlcritic_path:
        return "Error: perlcritic not found", 1

    cmd = [perlcritic_path, "--severity", str(severity)]
    if count_only:
        cmd.append("--count")
    else:
        # TSV формат: каждая ошибка = одна строка, 6 полей через TAB
        verbose_format = "%f\t%p\t%m\t%l\t%c\t%s\n"
        cmd.extend(["--verbose", verbose_format])

    if is_dir and recursive:
        cmd.extend(["--force", target])
    else:
        cmd.append(target)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="ignore",
            shell=(sys.platform == "win32")
        )
        output = result.stdout
        if result.stderr:
            output = f"{output}\n{result.stderr}" if output else result.stderr
        return output, result.returncode
    except subprocess.TimeoutExpired:
        return "Error: perlcritic timed out", 1
    except Exception as e:
        return f"Error: {str(e)}", 1


def normalize_severity(severity_str: str) -> int:
    """Нормализует severity к диапазону 1-5.
    Напоминание: 1=строжайший, 5=только критические.
    """
    try:
        severity = int(severity_str)
        return max(1, min(5, severity))
    except (ValueError, TypeError):
        return 3


def parse_perlcritic_output_tsv(output: str, code_lines: List[str] = None) -> List[Dict]:
    """Парсит TSV-вывод perlcritic.

    Формат: filename<TAB>policy<TAB>message<TAB>line<TAB>col<TAB>severity
    """
    issues = []

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) != 6:
            continue

        filename_raw, policy, message, line_str, col_str, severity_str = parts

        try:
            line_num = int(line_str.strip())
        except ValueError:
            continue
        try:
            col_num = int(col_str.strip())
        except ValueError:
            col_num = 1

        severity = normalize_severity(severity_str)
        file_basename = os.path.basename(filename_raw.strip()) if filename_raw.strip() else "unknown"

        snippet = ""
        if code_lines is not None and 1 <= line_num <= len(code_lines):
            snippet = code_lines[line_num - 1]

        issues.append({
            "file": file_basename,
            "line": line_num,
            "col": col_num,
            "issue": message.strip(),
            "severity": severity,
            "policy": policy.strip(),
            "snippet": snippet,
        })

    return issues


def analyze_perl_critic(
    target: str = None,
    code: str = None,
    filename: str = None,
    recursive: bool = True,
    severity: int = 1,
    statistics: bool = True,
    count_only: bool = False
) -> Dict:
    """Анализирует Perl код с помощью Perl::Critic.

    ВАЖНО: severity=1 строжайший (все нарушения), severity=5 только критические.

    Snippet:
    - code-параметр: snippet всегда есть (из переданного кода)
    - target локально в контейнере: snippet есть (файл читается)
    - target удалённо: snippet пустой (нет доступа к FS) — ожидаемо для MVP
    """
    temp_file = None
    code_lines = None

    if not target and not code:
        return {"path": None, "type": "unknown", "issues": [], "count": 0,
                "error": "Either target or code must be provided", "report_file": None}

    if not check_perlcritic_available():
        return {"path": target, "type": "unknown", "issues": [], "count": 0,
                "error": "perlcritic not found", "report_file": None}

    if code:
        if filename is None:
            filename = "analysis.pl"
        code_lines = code.splitlines()
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, filename)
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(code)
        target = temp_file

    if target and not os.path.exists(target):
        return {"path": target, "type": "unknown", "issues": [], "count": 0,
                "error": f"Path {target!r} does not exist", "report_file": None}

    # Для target-файла читаем содержимое для snippet.
    # Работает только если файл доступен внутри контейнера.
    if code_lines is None and target and os.path.isfile(target):
        try:
            with open(target, "r", encoding="utf-8", errors="ignore") as f:
                code_lines = f.read().splitlines()
        except (IOError, OSError):
            code_lines = None  # snippet будет пустым — не критично

    target_type = "directory" if os.path.isdir(target) else "file"
    output, exit_code = run_perlcritic_command(target, recursive, severity, statistics, count_only)

    parse_error_patterns = ["Problem while critiquing", "Can't parse code", "Can't locate"]
    if exit_code != 0 and any(p.lower() in output.lower() for p in parse_error_patterns):
        return {"path": target, "type": target_type, "issues": [], "count": 0,
                "error": output.strip(), "report_file": None}

    issues = parse_perlcritic_output_tsv(output, code_lines)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(target.rstrip("/\\")) or "analysis"
    report_filename = f"perlcritic_report_{base_name}_{timestamp}.json"

    if os.path.isdir(target):
        report_path = os.path.join(target, report_filename)
    else:
        report_path = os.path.join(os.path.dirname(target), report_filename)

    report = {
        "path": os.path.abspath(target),
        "type": target_type,
        "issues": issues,
        "count": len(issues),
        # raw_output намеренно не включён: не нужен LLM, засоряет контекст.
        # Для отладки раскомментировать:
        # "raw_output": output.strip(),
        "error": None,
        "report_file": report_path,
        "timestamp": datetime.now().isoformat()
    }

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except (IOError, OSError):
        report["report_file"] = None

    if temp_file and os.path.exists(temp_file):
        try:
            os.unlink(temp_file)
        except Exception:
            pass

    return report


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
        result = analyze_perl_critic(target)
        print(f"Issues: {result['count']}")
        if result.get("issues"):
            for i in result["issues"][:5]:
                print(f"  {i['file']}:{i['line']} [{i['severity']}] {i['policy']}")
                if i.get("snippet"):
                    print(f"    > {i['snippet']}")
