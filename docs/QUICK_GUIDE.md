# Perl Critic Quick Guide

## 🚀 Quick Start

### 1. Подготовка
Передай файл (НЕ через чат!):
- Email
- Git
- SFTP

### 2. Запуск
```
Analyze with perlcritic_analyze:
<code>
```
severity = 1

### 3. Результат
- ALL issues found = полный анализ ✓
- FEWER = код обрезан!

---

## ⚡ Quick Commands

### Kilo/Claude Prompt
```
Analyze this Perl with perlcritic_analyze severity=1.
Show ALL issues with line numbers!
```

### После анализа
```
Show me top 5 critical issues with exact line numbers.
Show code fix examples.
```

---

## 📊 Severity Levels

| # | Label | Цвет | Что делать |
|---|------|------|-----------|
| 1 | MOST STRICT | 🔴 | Исправь все |
| 2 | STRICT | 🟠 | Важно |
| 3 | MEDIUM | 🟡 | Рекомендации |
| 4 | HIGH | 🟢 | Можно отложить |
| 5 | CRITICAL | ⚡ | СРОЧНО! |

---

## 🔧 Quick Fixes

### Обязательно
```perl
# 1. Add at top
use strict;
use warnings;

# 2. For modules
our $VERSION = '1.00';

# 3. Subroutines
sub foo {
    my ($arg) = @_;
    # ... code ...
    return;  # <- DON'T FORGET!
}

# 4.Quotes
my $x = 'literal';  # not "literal"
```

### Опционально
```bash
# Format with perltidy
perltidy file.pl
```

---

## ⚠️ Common Issues

| Issue | Fix |
|-------|-----|
| No $VERSION | `our $VERSION = '1.00';` |
| No return | Add `return;` at end |
| print ignored | Usually OK |
| Not tidy | `perltidy file.pl` |
| Double-sigil @$x | OK in Perl, ignore |

---

## 🐛 Troubleshooting

| Problem | Cause | Fix |
|--------|-------|-----|
| FEWER issues than expected | Code was truncated before sending | Use file directly (email/Git), not copy-paste via chat |
| Different results | Different file versions | Use the same original file |
| No line numbers | Old MCP version | Update container |

---

## URL
- Docker: lenchik8/simple_mcp:latest