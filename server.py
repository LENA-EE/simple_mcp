#!/usr/bin/env python3
"""
Минимальный MCP-сервер с инструментом DROSPR_JARVIS.
Запускает SSE-сервер на порту 8000 по адресу http://0.0.0.0:8000/sse
"""

import asyncio
import json
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn

# Импорт нового инструмента perlcritic_analyze
try:
    from tools.perlcritic import analyze_perl_critic
    PERLCRITIC_AVAILABLE = True
except ImportError:
    PERLCRITIC_AVAILABLE = False


app = FastAPI(title="MCP DROSPR Server")

# Хранилище для активных соединений
connections = {}


def get_recommendation(policy):
    """Возвращает рекомендацию на русском языке для каждой policy."""
    recs = {
        "RequireTidyCode": "Отформатируйте код с помощью perltidy",
        "RequireExplicitPackage": "Добавьте явный package в начале файла: 'package MyApp; use strict; use warnings;'",
        "RequireVersionVar": "Добавьте переменную версии: our $VERSION = '1.00';",
        "RequireCheckedSyscalls": "Проверяйте возвращаемое значение или игнорируйте: eval { ... } или do { ... } or die",
        "RequireEndWithOne": "Файл должен заканчиваться на '1;', чтобы модуль возвращал истину",
        "ProhibitTwoArgOpen": "Используйте трехаргументный open: open my $fh, '<', $filename",
        "ProhibitBacktickCommands": "Избегайте обратных кавычек, используйте IPC::Open2/3",
        "ProhibitBooleanGrep": "grep возвращает список, используйте его в list context или проверяйте элементы иначе",
        "RequireBarewordIncludes": "Используйте короткие имена модулей в include: 'use My::Module;' вместо полного пути",
        "ProhibitMagicNumbers": "Используйте константы вместо чисел: my $MAX = 100;",
        "RequireUpperCaseHashKeys": "Ключи хеша должны быть в верхнем регистре: 'MyKey' instead of 'mykey'",
        "ProhibitStringySplit": "Используйте split с явным списком: split / /, $string вместо split",
        "ProhibitUnusedVariables": "Удалите неиспользуемые переменные или используйте их",
        "ProhibitLeadingZeros": "Уберите ведущие нули: 007 -> 7, 012 -> 10",
        "RequireFlags": "Добавьте use flags ':runtime'; и используйте flags в подпрограммах",
        "ProhibitBuiltinRefs": "Не используйте ref() как функцию, используйте ref($var)",
        "RequireScalarStorage": "Явно укажите скалярное хранилище: $var = \\'test';",
        "ProhibitLaxComments": "Используйте '# POD =cut' для документирования, не комментарии в POD",
        "RequireDeterministicSorting": "Используйте явную функцию сортировки: sort { $a cmp $b } @list",
        "ProhibitCommentedOutCode": "Удалите закомментированный код",
        "RequireUseStrict": "Добавьте 'use strict;' в начале файла",
        "RequireUseWarnings": "Добавьте 'use warnings;' в начале файла",
        "ProhibitBarewordRegex": "Используйте qr// для регулярок: my $re = qr/pattern/;",
        "ProhibitComplexRegexes": "Упростите регулярное выражение или используйте named regex",
        "ProhibitEmptyCase": "Удалите пустой switch/case или добавьте код",
        "ProhibitEvilMaintenance": "Не используйте флаги обслуживания (только для разработки)",
        "ProhibitExcessMaintainedCode": "Удалите устаревший код обслуживания",
        "ProhibitLowPrecedenceMath": "Используйте скобки для математических операций: ($a + $b) * $c",
        "ProhibitMixedCaseVars": "Используйте один стиль именования переменных: $my_var или $MyVar",
        "ProhibitMultipleCalls": "Не вызывайте несколько раз то же самое",
        "ProhibitNoWarnings": "Не отключайте warnings без крайней необходимости",
        "ProhibitNumericStrStr": "Используйте строковые операции для строк, numeric для чисел",
        "ProhibitOneArgDiamond": "Используйте @ARGV явно: while (my $file = shift @ARGV)",
        "ProhibitParenUnion": "Хотя бы одно условие верно: ($a || $b || $c)",
        "ProhibitPostfixControls": "Используйте блок { } вокруг postfix if/unless",
        "ProhibitPrivateSubs": "Не вызывайте приватные субрутины: _private() -> private()",
        "ProhibitRegexpMatchArgs": "Используйте m// без аргументов: m/$pattern/ вместо m/$pattern/, $str",
        "ProhibitSmart::": "Не используйте Smart::, используйте if/elsif/else",
        "ProhibitUnlessBlocks": "Используйте if вместо unless",
        "ProhibitUntilBlocks": "Используйте while вместо until, поменяв условие",
        "RequireBarewordReferences": "Используйте \\$var для ссылок",
        "RequireBlockGrep": "Используйте { } в grep: grep { ... } @list",
        "RequireBlockMap": "Используйте { } в map: map { ... } @list",
        "RequireCapitalConfiguration": "Конфигурация должна быть в верхнем регистре",
        "RequireCharacterClassML": "Используйте [a-z] вместо [:lower:]",
        "RequireEncodingWithUTF8": "Используйте 'use utf8;' и кодировку UTF-8",
        "RequireFiveDotZero": "Минимальная версия Perl 5.0",
        "RequireLexicalDynamic": "Используйте my для динамических переменных: my $var",
        "RequirePackagedVars": "Используйте Exporter или Object-Perl для экспорта переменных",
        "RequireVersionSpecificity": "Требуйте минимальную версию Perl: use 5.010;",
        "ProhibitVaryingStrings": "Не меняйте length строки в регулярке",
        "ProhibitVoidSafes": "Удалите неиспользуемые return или use $x if 0;",
        "ProhibitUniversalRefs": "Не используйте универсальные ссылки: \\$var, \\@arr, \\%hash",
        "ProhibitExplicitReturn": "Возвращайте явно: return @result;",
        "ProhibitExitWithoutSeparator": "Используйте separators: exit() if $cond; или exit $code;",
    }
    # Match partial policy name
    for key, val in recs.items():
        if key.lower() in policy.lower() or policy.lower() in key.lower():
            return val
    return "Исправьте согласно требованиям Perl Best Practices"


def handle_mcp_request(request_data):
    """Обрабатывает MCP запросы."""
    try:
        method = request_data.get("method")
        
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "mcp-DROSPR_JARVIS",
                    "version": "0.1.0"
                }
            }
        elif method == "tools/list":
            tools = [
                {
                    "name": "DROSPR_JARVIS",
                    "description": "Приветствие — просто знакомство, НЕ ищет файлы",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            ]
            
            # Добавляем perlcritic_analyze
            if PERLCRITIC_AVAILABLE:
                tools.append({
                    "name": "perlcritic_analyze",
                    "description": "Анализирует Perl код с помощью Perl::Critic. Output: группировка по Severity (1-5), с номерами строк и рекомендациями на русском.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "REQUIRED: Pass FULL code. DO NOT TRUNCATE - send entire file content."
                            },
                            "filename": {
                                "type": "string",
                                "description": "Имя файла для временного файла (опционально)"
                            },
                            "severity": {
                                "type": "integer",
                                "description": "REQUIRED: Use severity=1 (most strict, shows ALL problems). 1=САМЫЙ СТРОГИЙ, 5=Только критические.",
                                "default": 1,
                                "minimum": 1,
                                "maximum": 5
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Рекурсивный анализ директорий (по умолчанию true)",
                                "default": True
                            },
                            "statistics": {
                                "type": "boolean",
                                "description": "Включить статистику (по умолчанию true)",
                                "default": True
                            },
                            "count_only": {
                                "type": "boolean",
                                "description": "Только количество проблем (по умолчанию false)",
                                "default": False
                            }
                        },
                        "required": ["code"]
                    }
                })
            
            return {"tools": tools}
        elif method == "tools/call":
            params = request_data.get("params", {})
            tool_name = params.get("name")
            
            if tool_name == "DROSPR_JARVIS":
                return {
                    "content": [{
                        "type": "text",
                        "text": "Привет! Я DROSPR_JARVIS — твой Perl Code Review Assistant.\n\nИспользуй perlcritic_analyze для анализа Perl кода.\n\nОсобенности:\n- severity=1 показывает ВСЕ проблемы\n- Показывает номер строки для каждой проблемы\n- Рекомендации на русском языке"
                    }]
                }
            elif tool_name == "perlcritic_analyze" and PERLCRITIC_AVAILABLE:
                arguments = params.get("arguments", {})
                code = arguments.get("code")
                filename = arguments.get("filename")
                severity = arguments.get("severity", 1)
                recursive = arguments.get("recursive", True)
                statistics = arguments.get("statistics", True)
                count_only = arguments.get("count_only", False)
                
                if not code:
                    return {
                        "content": [{
                            "type": "text",
                            "text": "ERROR: Missing required parameter 'code'. Pass the Perl code as a string to analyze."
                        }]
                    }
                
# Выполняем анализ Perl::Critic
                result = analyze_perl_critic(
                    code=code,
                    filename=filename,
                    severity=severity,
                    recursive=recursive,
                    statistics=statistics,
                    count_only=count_only
                )
                
                # Формируем ответ MCP
                response_content = []
                
                if result.get("error"):
                    response_content.append({
                        "type": "text",
                        "text": f"Ошибка анализа: {result['error']}"
                    })
                else:
                    # Формируем подробный вывод для LLM
                    issues = result.get("issues", [])
                    
                    # raw_output намеренно не передаётся LLM — засоряет контекст.
                    # LLM получает только структурированный отчёт ниже.
                    
                    # Структурированный вывод для LLM
                    # ВАЖНО: severity=1 строжайший (все нарушения), severity=5 только критические
                    severity_label_map = {
                        1: "most strict (all violations)",
                        2: "strict",
                        3: "medium",
                        4: "high issues only",
                        5: "critical only"
                    }
                    sev_label = severity_label_map.get(severity, str(severity))
                    _sep = "=" * 41
                    output_lines = [f"PERL CODE ANALYSIS REPORT\n{_sep}\nFile    : {result.get('path')}\nType    : {result.get('type')}\nSeverity: {severity} ({sev_label})\nTotal   : {result['count']} issue(s) found\n"]
                    
                    if issues:
                        # Group by severity
                        by_sev = {1: [], 2: [], 3: [], 4: [], 5: []}
                        for iss in issues:
                            s = iss.get("severity", 3)
                            if s in by_sev:
                                by_sev[s].append(iss)
                            else:
                                by_sev[3].append(iss)
                        
                        # Severity labels in Russian
                        sev_labels = {
                            1: "САМЫЙ СТРОГИЙ (все нарушения)",
                            2: "СТРОГИЙ",
                            3: "СРЕДНИЙ",
                            4: "ВЫСОКИЙ",
                            5: "ТОЛЬКО КРИТИЧЕСКИЕ"
                        }
                        sev_labels_en = {1: "MOST STRICT", 2: "STRICT", 3: "MEDIUM", 4: "HIGH", 5: "CRITICAL"}
                        
                        output_lines.append(f"\n=== НАЙДЕНО {len(issues)} ПРОБЛЕМ ===\n")
                        output_lines.append(f"CRITICAL: You MUST show each issue with EXACT line number! Format: 'Line NNN: issue description'\n")
                        output_lines.append(f"Do NOT summarize - list EVERY issue separately! Showing ALL {len(issues)} issues is REQUIRED.\n\n")
                        
                        # Output in severity order: 1, 2, 3, 4, 5
                        for sev_level in [1, 2, 3, 4, 5]:
                            issues_by_level = by_sev[sev_level]
                            if not issues_by_level:
                                continue
                            
                            label = sev_labels.get(sev_level, f"Level {sev_level}")
                            output_lines.append(f"\n--- {label} ({len(issues_by_level)} шт.) ---\n")
                            
                            for i, issue in enumerate(issues_by_level, 1):
                                i_file = issue.get("file", "")
                                i_line = issue.get("line", "")
                                i_col = issue.get("col", "")
                                i_policy = issue.get("policy", "")
                                i_msg = issue.get("issue", "")
                                i_snippet = issue.get("snippet", "")
                                
                                col_str = f", Col {i_col}" if i_col else ""
                                
                                # Recommendation in Russian based on policy
                                rec = get_recommendation(i_policy)
                                
                                output_lines.append(f"{i}. Строка {i_line}: {i_msg}\n")
                                if rec:
                                    output_lines.append(f"   РЕКОМЕНДАЦИЯ: {rec}\n")
                                output_lines.append(f"   Policy: {i_policy} | Файл: {i_file}{col_str}\n")
                                if i_snippet:
                                    output_lines.append(f"   Код   : {i_snippet}\n")
                                output_lines.append("\n")
                    # Summary по severity
                    # Напоминание: 1=строжайший (все нарушения), 5=только критические
                    sev_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                    for iss in issues:
                        s = iss.get("severity", 3)
                        if s in sev_counts:
                            sev_counts[s] += 1
                    output_lines.append("\nSUMMARY\n-------\n")
                    output_lines.append(f"Severity 1 (most strict / all violations) : {sev_counts[1]}\n")
                    output_lines.append(f"Severity 2 (strict)                       : {sev_counts[2]}\n")
                    output_lines.append(f"Severity 3 (medium)                       : {sev_counts[3]}\n")
                    output_lines.append(f"Severity 4 (high)                         : {sev_counts[4]}\n")
                    output_lines.append(f"Severity 5 (critical only)                : {sev_counts[5]}\n")
                    if result.get("report_file"):
                        output_lines.append(f"\nReport saved: {result['report_file']}\n")
                    if not issues:
                        output_lines.append("\nNo issues found. Code is clean!\n")
                    
                    response_content.append({
                        "type": "text",
                        "text": "".join(output_lines)
                    })
                
# Возвращаем ответ с дополнительными данными в report
                return {
                    "content": response_content,
                    "report": result
                }
            else:
                return {"error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        else:
            return {"error": {"code": -32601, "message": "Method not found"}}
    except Exception as e:
        return {"error": {"code": -32603, "message": str(e)}}


# Очередь сообщений для каждого соединения
message_queues = {}

@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE эндпоинт для MCP соединений."""
    
    async def event_stream():
        connection_id = str(uuid.uuid4())
        connections[connection_id] = True
        message_queues[connection_id] = asyncio.Queue()
        
        try:
            while connections.get(connection_id, False):
                try:
                    # Ждем сообщение из очереди с таймаутом
                    message = await asyncio.wait_for(
                        message_queues[connection_id].get(), 
                        timeout=30.0
                    )
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Отправляем ping для поддержания соединения
                    yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'notifications/ping'})}\n\n"
                
        except asyncio.CancelledError:
            pass
        finally:
            connections.pop(connection_id, None)
            message_queues.pop(connection_id, None)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


@app.post("/sse")
async def sse_post_endpoint(request: Request):
    """POST эндпоинт для отправки MCP запросов."""
    try:
        content_type = request.headers.get("content-type", "")
        
        # Парсим JSON
        try:
            body = await request.body()
            request_data = json.loads(body)
        except json.JSONDecodeError:
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid JSON"}}
        
        # Проверяем JSON-RPC 2.0 формат
        if request_data.get("jsonrpc") != "2.0":
            request_data["jsonrpc"] = "2.0"
        
        response = handle_mcp_request(request_data)
        
        # Формируем правильный JSON-RPC 2.0 ответ
        json_rpc_response = {
            "jsonrpc": "2.0",
            "id": request_data.get("id")
        }
        
        if "error" in response:
            json_rpc_response["error"] = response["error"]
        else:
            json_rpc_response["result"] = response
            
        return json_rpc_response
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id") if 'request_data' in locals() else None,
            "error": {"code": -32603, "message": str(e)}
        }


@app.get("/")
async def root():
    """Корневой эндпоинт для проверки работоспособности."""
    return {
        "name": "MCP DROSPR Server",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "sse": "/sse",
            "post": "/sse",
            "health": "/"
        }
    }


@app.post("/")
async def post_root(request: Request):
    """POST эндпоинт для MCP запросов."""
    try:
        body = await request.body()
        request_data = json.loads(body)
        
        if request_data.get("jsonrpc") != "2.0":
            request_data["jsonrpc"] = "2.0"
        
        response = handle_mcp_request(request_data)
        
        json_rpc_response = {
            "jsonrpc": "2.0",
            "id": request_data.get("id")
        }
        
        if "error" in response:
            json_rpc_response["error"] = response["error"]
        else:
            json_rpc_response["result"] = response
            
        return json_rpc_response
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32603, "message": str(e)}
        }


if __name__ == "__main__":
    print("Запуск MCP DROSPR Server на http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
