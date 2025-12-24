#!/bin/bash
# 验证合并后的工作流程

echo "========================================="
echo "验证合并后的工作流程"
echo "========================================="

# 检查skill是否存在
echo "1. 检查新的 skill 是否存在..."
if [ -f ".claude/skills/extract-and-check-data/SKILL.md" ]; then
    echo "   ✅ SKILL.md 存在"
else
    echo "   ❌ SKILL.md 不存在"
    exit 1
fi

if [ -f ".claude/skills/extract-and-check-data/scripts/extract_and_check_data.py" ]; then
    echo "   ✅ 脚本存在"
else
    echo "   ❌ 脚本不存在"
    exit 1
fi

# 运行单元测试
echo ""
echo "2. 运行单元测试..."
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/ -v
if [ $? -eq 0 ]; then
    echo "   ✅ 单元测试通过"
else
    echo "   ❌ 单元测试失败"
    exit 1
fi

# 运行集成测试
echo ""
echo "3. 运行集成测试..."
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/ -v
if [ $? -eq 0 ]; then
    echo "   ✅ 集成测试通过"
else
    echo "   ❌ 集成测试失败"
    exit 1
fi

# 检查文档更新
echo ""
echo "4. 检查文档是否更新..."
if grep -q "extract-and-check-data" CLAUDE.md; then
    echo "   ✅ CLAUDE.md 已更新"
else
    echo "   ❌ CLAUDE.md 未更新"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ 所有验证通过!"
echo "========================================="
