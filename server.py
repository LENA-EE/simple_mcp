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
            return {
                "tools": [
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
            }
        elif method == "tools/call":
            params = request_data.get("params", {})
            if params.get("name") == "drospr":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Привет от MCP ДРОСПР! :)"
                        }
                    ]
                }
            else:
                return {"error": {"code": -32601, "message": f"Unknown tool: {params.get('name')}"}}
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
        request_data = await request.json()
        
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
            "health": "/"
        }
    }


if __name__ == "__main__":
    print("Запуск MCP DROSPR Server на http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
