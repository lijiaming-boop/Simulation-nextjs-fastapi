#!/bin/bash
# 实时查看 Streamlit 应用日志的脚本

echo "=== 查看 Streamlit 应用日志 ==="
echo ""

# 查找最新的后台任务日志文件
LOG_DIR="C:\Users\GAOZHE~1\AppData\Local\Temp\claude\D--source-ai-conditioner-saving\tasks"
LATEST_LOG=$(ls -t "$LOG_DIR"/*.output 2>/dev/null | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "❌ 未找到日志文件"
    echo "提示：确保应用正在后台运行"
    exit 1
fi

echo "📄 日志文件: $LATEST_LOG"
echo "---"
echo ""

# 实时监控日志
tail -f "$LATEST_LOG"
