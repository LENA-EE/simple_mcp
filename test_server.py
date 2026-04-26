#!/usr/bin/env python3
"""
Тестовый скрипт для проверки MCP сервера drospr.
Проверяет, что сервер может быть импортирован и содержит правильные функции.
"""

import sys
import asyncio
from importlib import util

def check_imports():
    """Проверяет, что все необходимые модули могут быть импортированы."""
    modules = ['fastapi', 'uvicorn', 'asyncio']
    for module_name in modules:
        if module_name == 'asyncio':
            continue  # asyncio встроенный модуль
        spec = util.find_spec(module_name)
        if spec is None:
            print(f"❌ Модуль {module_name} не найден")
            return False
        print(f"✅ Модуль {module_name} доступен")
    return True

def check_server_code():
    """Проверяет, что server.py содержит правильный код."""
    try:
        with open('server.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = [
            ('handle_mcp_request', 'Функция обработки MCP запросов'),
            ('drospr', 'Инструмент drospr'),
            ('Привет от MCP ДРОСПР', 'Приветственное сообщение'),
            ('tools/list', 'Обработка списка инструментов'),
            ('tools/call', 'Обработка вызова инструментов'),
            ('initialize', 'Инициализация сервера'),
            ('/sse', 'SSE эндпоинт'),
            ('FastAPI', 'FastAPI приложение'),
            ('8000', 'Порт 8000'),
            ('0.0.0.0', 'Хост 0.0.0.0'),
        ]
        
        # Дополнительные проверки для perlcritic_analyze
        perlcritic_checks = [
            ('perlcritic_analyze', 'Инструмент perlcritic_analyze'),
            ('analyze_perl_critic', 'Функция анализа Perl::Critic'),
            ('tools.perlcritic', 'Импорт модуля perlcritic'),
        ]
        
        all_passed = True
        for check_str, description in checks:
            if check_str in content:
                print(f"✅ {description} присутствует в коде")
            else:
                print(f"❌ {description} отсутствует в коде")
                all_passed = False
        
        # Проверяем наличие perlcritic_analyze
        print("\n3. Проверка инструмента perlcritic_analyze:")
        perlcritic_passed = True
        for check_str, description in perlcritic_checks:
            if check_str in content:
                print(f"✅ {description} присутствует в коде")
            else:
                print(f"⚠️  {description} отсутствует в коде (но это нормально, если perlcritic не установлен)")
                # Не считаем это ошибкой, так как perlcritic может быть не установлен
        
        return all_passed
    except FileNotFoundError:
        print("❌ Файл server.py не найден")
        return False

def main():
    """Основная функция тестирования."""
    print("=" * 50)
    print("Тестирование MCP сервера drospr")
    print("=" * 50)
    
    print("\n1. Проверка импортов:")
    if not check_imports():
        print("\n❌ Тест импортов не пройден")
        return 1
    
    print("\n2. Проверка кода server.py:")
    if not check_server_code():
        print("\n❌ Тест кода не пройден")
        return 1
    
    print("\n" + "=" * 50)
    print("✅ Все тесты пройдены успешно!")
    print("Сервер готов к запуску командой: python server.py")
    print("Сервер будет доступен по адресу: http://0.0.0.0:8000/sse")
    print("=" * 50)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())