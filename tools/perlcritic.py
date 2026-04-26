#!/usr/bin/env python3
"""
Модуль для анализа Perl кода с помощью Perl::Critic.
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
    """Запускает команду perlcritic для анализа."""
    if not os.path.exists(target):
        return f"Error: Path '{target}' does not exist", 1
    
    severity = max(1, min(5, severity))
    is_dir = os.path.isdir(target)
    
    perlcritic_path = find_perlcritic_path()
    if not perlcritic_path:
        return "Error: perlcritic not found", 1
    
    # Используем дефолтный формат (без --verbose) как у Григория
    cmd = [perlcritic_path, "--severity", str(severity)]
    if statistics:
        cmd.append("--statistics")
    if count_only:
        cmd.append("--count")
    
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
            encoding='utf-8',
            errors='ignore',
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
    """Нормализует severity к диапазону 1-5."""
    try:
        severity = int(severity_str)
        return max(1, min(5, severity))
    except (ValueError, TypeError):
        return 3


def parse_perlcritic_output(output: str, target_path: str) -> List[Dict]:
    """Парсит вывод perlcritic (дефолтный формат)."""
    issues = []
    base_name = os.path.basename(target_path) if target_path else "file"
    
    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Пропускаем служебные строки
        skip_patterns = ['source OK', '1 files.', 'Computing', 'Average McCabe', 'Use of']
        if any(p.lower() in line.lower() for p in skip_patterns):
            continue
        
        # Формат: "Issue text at line N, column M. ... (Severity: N)"
        # Или с путём: "/path/file.pl: Issue text at line N..."
        
        # Ищем line и severity
        line_match = re.search(r'at line\s+(\d+)', line)
        if not line_match:
            continue
        
        line_num = int(line_match.group(1))
        
        # Severity
        severity_match = re.search(r'\(Severity:\s*(\d+)\)', line)
        severity = normalize_severity(severity_match.group(1)) if severity_match else 3
        
        # Policy - ищем после "See" или "pages"
        policy_match = re.search(r'See\s+(?:page\s+\d+\s+(?:of\s+)?|pages\s+[\d,]+\s+(?:of\s+)?)?([\w:]+)', line)
        policy = policy_match.group(1) if policy_match else 'Unknown'
        
        # Issue text - между началом строки и " at line"
        issue_match = re.match(r'^(.+?)\s+at line', line)
        if issue_match:
            issue = issue_match.group(1).strip()
        else:
            # Пробуем другой паттерн для строк с путём
            issue_match = re.match(r'^.+?:\s*(.+?)\s+at line', line)
            issue = issue_match.group(1).strip() if issue_match else line[:50]
        
        issues.append({
            'file': base_name,
            'line': line_num,
            'issue': issue,
            'severity': severity,
            'policy': policy,
            'snippet': ''
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
    """Анализирует Perl код с помощью Perl::Critic."""
    temp_file = None
    
    if not target and not code:
        return {"path": None, "type": "unknown", "issues": [], "count": 0,
                "error": "Either 'target' or 'code' must be provided", "report_file": None}
    
    if not check_perlcritic_available():
        return {"path": target, "type": "unknown", "issues": [], "count": 0,
                "error": "perlcritic not found", "report_file": None}
    
    if code:
        if filename is None:
            filename = "analysis.pl"
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, filename)
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(code)
        target = temp_file
    
    if target and not os.path.exists(target):
        return {"path": target, "type": "unknown", "issues": [], "count": 0,
                "error": f"Path '{target}' does not exist", "report_file": None}
    
    target_type = "directory" if os.path.isdir(target) else "file"
    output, exit_code = run_perlcritic_command(target, recursive, severity, statistics, count_only)
    
    # Проверяем на критические ошибки парсинга
    parse_error_patterns = ["Problem while critiquing", "Can't parse code", "Can't locate"]
    if exit_code != 0 and any(p.lower() in output.lower() for p in parse_error_patterns):
        return {"path": target, "type": target_type, "issues": [], "count": 0,
                "error": output.strip(), "report_file": None}
    
    issues = parse_perlcritic_output(output, target)
    
    # Сохраняем отчет
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(target.rstrip('/\\')) or "analysis"
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
        "raw_output": output.strip(),
        "error": None,
        "report_file": report_path,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except (IOError, OSError):
        report["report_file"] = None
    
    if temp_file and os.path.exists(temp_file):
        try:
            os.unlink(temp_file)
        except:
            pass
    
    return report


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
        result = analyze_perl_critic(target)
        print(f"Issues: {result['count']}")
        if result.get('issues'):
            for i in result['issues'][:5]:
                print(f"  {i['file']}:{i['line']} [{i['severity']}] {i['policy']}")