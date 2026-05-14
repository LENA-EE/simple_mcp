#!/bin/bash
# Подключение pre-push хука к проекту — одна команда для разработчика

git config core.hooksPath .githooks
chmod +x .githooks/pre-push

echo "✅ Pre-push хук подключён."
echo "Теперь при git push Perl-код автоматически проверяется через MCP JARVIS."
echo ""
echo "Адрес MCP-сервера прописан в .githooks/pre-push (MCP_URL)."
echo "При необходимости поменяй его на актуальный адрес виртуалки."
