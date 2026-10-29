# """测试 API 连接"""
# import os
# from pathlib import Path
# import sys
#
# # 加载 .env 文件（从项目根目录）
# _project_root = Path(__file__).parent.parent.parent  # tests/unit/ -> tests/ -> 项目根目录
# _env_path = _project_root / ".env"
#
# print(f"尝试加载 .env 文件: {_env_path}")
# print(f"文件存在: {_env_path.exists()}")
#
# if _env_path.exists():
#     for line in _env_path.read_text(encoding="utf-8").splitlines():
#         line = line.strip()
#         if line and not line.startswith("#") and "=" in line:
#             key, val = line.split("=", 1)
#             os.environ.setdefault(key.strip(), val.strip())
#     print("✅ .env 文件加载成功\n")
# else:
#     print("❌ .env 文件不存在，使用系统环境变量\n")
#
# print("当前配置:")
# api_key = os.environ.get('ANTHROPIC_API_KEY')
# base_url = os.environ.get('ANTHROPIC_BASE_URL')
# model = os.environ.get('ANTHROPIC_MODEL')
#
# print(f"  BASE_URL: {base_url or '未设置（使用默认）'}")
# print(f"  API_KEY: {'已配置' if api_key else '未配置'}")
# if api_key:
#     print(f"           {api_key[:10]}...")
# print(f"  MODEL: {model or '未设置（使用默认 claude-3-sonnet-20240229）'}")
#
# # 尝试调用 API
# try:
#     if not api_key:
#         raise ValueError("ANTHROPIC_API_KEY 未配置")
#
#     import anthropic
#
#     client = anthropic.Anthropic(
#         api_key=api_key,
#         base_url=base_url or None
#     )
#
#     model_name = model or "claude-3-sonnet-20240229"
#
#     print(f"\n正在测试模型: {model_name}")
#     response = client.messages.create(
#         model=model_name,
#         max_tokens=100,
#         messages=[{"role": "user", "content": "你好，请回复'连接成功'"}]
#     )
#
#     print(f"✅ API 连接成功！")
#     print(f"   响应: {response.content[0].text}")
#     print(f"\n📝 说明:")
#     print(f"   - 你的 API 密钥有效")
#     print(f"   - 代理服务器 {base_url} 正常工作")
#     print(f"   - 模型 '{model_name}' 可用")
#
# except Exception as e:
#     print(f"\n❌ API 连接失败: {e}")
#     print(f"\n可能的原因:")
#     print(f"  1. API 密钥无效或过期")
#     print(f"  2. 模型名称不正确（'{model}' 可能不是有效模型）")
#     print(f"  3. BASE_URL 指向的服务不可用 ({base_url})")
#     print(f"\n建议:")
#     print(f"  - 联系 API 提供方确认正确的模型名称")
#     print(f"  - 当前配置的模型: '{model}'")
#     print(f"  - 常见的 Claude 模型:")
#     print(f"    • claude-3-haiku-20240307 (快速、便宜)")
#     print(f"    • claude-3-sonnet-20240229 (推荐)")
#     print(f"    • claude-3-opus-20240229 (最强)")
#     sys.exit(1)


"""测试 API 连接 - 支持交互式对话"""
import os
from pathlib import Path
import sys

# 加载 .env 文件（从项目根目录）
_project_root = Path(__file__).parent.parent.parent  # tests/unit/ -> tests/ -> 项目根目录
_env_path = _project_root / ".env"

print(f"尝试加载 .env 文件: {_env_path}")
print(f"文件存在: {_env_path.exists()}")

if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())
    print(".env 文件加载成功\n")
else:
    print(".env 文件不存在，使用系统环境变量\n")

print("当前配置:")
api_key = os.environ.get('ANTHROPIC_API_KEY')
base_url = os.environ.get('ANTHROPIC_BASE_URL')
model = os.environ.get('ANTHROPIC_MODEL')

print(f"  BASE_URL: {base_url or '未设置（使用默认）'}")
print(f"  API_KEY: {'已配置' if api_key else '未配置'}")
if api_key:
    print(f"           {api_key[:10]}...")
print(f"  MODEL: {model or '未设置（使用默认 claude-3-sonnet-20240229）'}")

# 尝试调用 API
try:
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 未配置")

    import anthropic

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url or None
    )

    model_name = model or "claude-3-sonnet-20240229"

    print(f"\n正在测试模型: {model_name}")
    response = client.messages.create(
        model=model_name,
        max_tokens=100,
        messages=[{"role": "user", "content": "你好，请回复'连接成功'"}]
    )

    print(f"API 连接成功！")
    print(f"   响应: {response.content[0].text}")
    print(f"\n 说明:")
    print(f"   - 你的 API 密钥有效")
    print(f"   - 代理服务器 {base_url} 正常工作")
    print(f"   - 模型 '{model_name}' 可用")

except Exception as e:
    print(f"\nAPI 连接失败: {e}")
    print(f"\n可能的原因:")
    print(f"  1. API 密钥无效或过期")
    print(f"  2. 模型名称不正确（'{model}' 可能不是有效模型）")
    print(f"  3. BASE_URL 指向的服务不可用 ({base_url})")
    print(f"\n建议:")
    print(f"  - 联系 API 提供方确认正确的模型名称")
    print(f"  - 当前配置的模型: '{model}'")
    print(f"  - 常见的 Claude 模型:")
    print(f"    • claude-3-haiku-20240307 (快速、便宜)")
    print(f"    • claude-3-sonnet-20240229 (推荐)")
    print(f"    • claude-3-opus-20240229 (最强)")
    if __name__ == "__main__":
        sys.exit(1)


def chat_with_claude(message: str, max_tokens: int = 1000) -> str:
    """
    与 Claude 模型进行单次对话

    Args:
        message: 用户输入的消息
        max_tokens: 最大输出长度

    Returns:
        AI 的回复内容
    """
    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": message}]
        )
        return response.content[0].text
    except Exception as e:
        return f"API 调用失败: {e}"


def interactive_chat():
    """交互式对话模式"""
    print("\n" + "=" * 60)
    print(" Claude 交互式对话模式")
    print("=" * 60)
    print("输入 'quit' 或 'exit' 退出")
    print("输入 'clear' 清空屏幕")
    print("=" * 60 + "\n")

    conversation_history = []

    while True:
        user_input = input("👤 你: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ['quit', 'exit', 'q']:
            print("\n 再见！")
            break

        if user_input.lower() == 'clear':
            print("\n" * 50)
            continue

        print("\n⏳ AI 思考中...")
        response = chat_with_claude(user_input)

        print(f"\n AI: {response}\n")
        print("-" * 60)

        # 保存对话历史（可选）
        conversation_history.append({
            "user": user_input,
            "ai": response
        })


if __name__ == "__main__":
    # 如果直接运行此脚本，启动交互式对话
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        interactive_chat()
    else:
        print("\n💡 提示: 运行 'python test_a_api_connection.py --chat' 进入交互对话模式")


