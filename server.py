#!/usr/bin/env python3
"""
Минимальный MCP-сервер с инструментом drospr.
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
                    "name": "mcp-drospr",
                    "version": "0.1.0"
                }
            }
        elif method == "tools/list":
            tools = [
                {
                    "name": "drospr",
                    "description": "Возвращает приветственное сообщение от MCP ДРОСПР",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            ]
            
            # Добавляем perlcritic_analyze, если модуль доступен
            if PERLCRITIC_AVAILABLE:
                tools.append({
                    "name": "perlcritic_analyze",
                    "description": "Анализирует Perl код с помощью Perl::Critic и сохраняет отчет в JSON файл",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "Путь к файлу или директории для анализа"
                            },
                            "code": {
                                "type": "string",
                                "description": "Perl код напрямую (альтернатива target)"
                            },
                            "filename": {
                                "type": "string",
                                "description": "Имя файла для временного файла (опционально)"
                            },
                            "severity": {
                                "type": "integer",
                                "description": "Уровень строгости 1-5 (1 - самый строгий, 5 - мягкий)",
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
                        "required": ["target"]
                    }
                })
            
            return {"tools": tools}
        elif method == "tools/call":
            params = request_data.get("params", {})
            tool_name = params.get("name")
            
            if tool_name == "drospr":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Привет от MCP ДРОСПР! :)"
                        }
                    ]
                }
            elif tool_name == "perlcritic_analyze" and PERLCRITIC_AVAILABLE:
                arguments = params.get("arguments", {})
                target = arguments.get("target")
                code = arguments.get("code")
                filename = arguments.get("filename")
                severity = arguments.get("severity", 1)
                recursive = arguments.get("recursive", True)
                statistics = arguments.get("statistics", True)
                count_only = arguments.get("count_only", False)
                
                if not target and not code:
                    return {"error": {"code": -32602, "message": "Missing required parameter: target or code"}}
                
                # Выполняем анализ Perl::Critic
                result = analyze_perl_critic(
                    target=target,
                    code=code,
                    filename=filename,
                    recursive=recursive,
                    severity=severity,
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
                    
                    # Сначала raw output - максимально подробно как в perlcritic
                    raw = result.get("raw_output", "")
                    if raw:
                        response_content.append({
                            "type": "text",
                            "text": raw
                        })
                    
                    # Краткая сводка
                    output_lines = [f"\n=== Summary ===\nTarget: {result.get('path')}\nType: {result.get('type')}\nSeverity level: {severity}\nTotal issues found: {result['count']}\n"]
                    
                    if issues:
                        output_lines.append("\n--- Parsed Issues ---\n")
                        for i, issue in enumerate(issues, 1):
                            file_path = issue.get('file', '')
                            line_num = issue.get('line', '')
                            severity = issue.get('severity', '')
                            policy = issue.get('policy', '')
                            issue_text = issue.get('issue', '')
                            snippet = issue.get('snippet', {})
                            
                            output_lines.append(f"{i}. [{severity}] {file_path}:{line_num}\n")
                            output_lines.append(f"   Policy: {policy}\n")
                            output_lines.append(f"   Issue: {issue_text}\n")
                            
                            if snippet:
                                before = snippet.get('before', [])
                                line = snippet.get('line', '')
                                after = snippet.get('after', [])
                                context = snippet.get('context', '')
                                output_lines.append(f"   Snippet ({context}):\n")
                                for b in before:
                                    output_lines.append(f"     | {b}\n")
                                output_lines.append(f"     > {line}\n")
                                for a in after:
                                    output_lines.append(f"     | {a}\n")
                            output_lines.append("\n")
                    else:
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
