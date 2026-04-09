"""
================================================================================
Web UI Agent - 主程序入口
================================================================================

【模块概述】
这是 Web UI Agent 的主程序入口。程序从这里启动，负责：
1. 检查环境变量配置
2. 创建 Agent 实例
3. 执行测试任务

【项目结构】
web_ui_agent/
├── config.py              # 配置常量
├── state.py               # 状态定义
├── utils.py               # 辅助函数
├── nodes.py               # 图节点实现
├── agent.py               # Agent 类封装
├── step_manager.py        # 动态步骤数调整
├── completion_evaluator.py # 任务完成度评估
├── termination_manager.py # 多条件终止机制
├── user_interaction.py    # 用户交互接口
├── checkpoint_manager.py  # 状态保存与恢复
├── agent_logger.py        # 日志记录系统
└── main.py                # 主程序入口（本文件）

【命令行用法】
python main.py                              # 执行默认任务
python main.py --list-checkpoints           # 列出检查点
python main.py --resume cp_xxxxx_xxxxx      # 从检查点恢复
python main.py --objective "搜索教程"       # 自定义目标
python main.py --url "https://example.com"  # 自定义起始URL
python main.py --max-steps 50               # 自定义最大步骤数
python main.py --cleanup                    # 清理过期检查点
================================================================================
# 同时设置目标和起始URL
python main.py -o "在京东搜索手机" -u "https://www.jd.com"

# 或者使用完整参数名
python main.py --objective "在淘宝搜索笔记本电脑" --url "https://www.taobao.com"

# 还可以同时设置最大步骤数
python main.py -o "购买 iPhone" -u "https://www.apple.com.cn" -m 50
"""

import argparse

from agent import WebUIAgent
from llm_config_store import (
    get_available_model_catalog,
    get_default_model_id,
    get_model_config,
)
from output_handler import reset_output_handler


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Web UI Agent - Web UI 自动化代理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py                                    # 执行默认任务
  python main.py --list-checkpoints                 # 列出所有检查点
  python main.py --resume cp_xxxxx_xxxxx            # 从检查点恢复
  python main.py -o "在京东搜索手机" -u "https://jd.com"  # 自定义目标和URL
  python main.py --max-steps 50                     # 设置最大步骤数
  python main.py --cleanup --max-age 24             # 清理24小时前的检查点

运行时交互命令:
  continue (c)     - 继续执行暂停的任务
  pause (p)        - 暂停当前任务
  abort (a)        - 终止任务
  extend (e) [n]   - 增加步骤限制 n (默认5)
  reduce (r) [n]   - 减少步骤限制 n (默认5)
  status (s)       - 显示当前状态
  save             - 保存检查点
  load             - 加载检查点
  timeout [n]      - 设置超时时间(秒)
  intervene (i) [n]- 人工干预：暂停终止倒计时 n秒 (默认60秒)
  fast (f)         - 切换快速模式（使用更严格的终止条件）
  model (m)        - 显示当前模型状态
  models           - 列出所有可用模型
  switch <model>   - 切换到指定模型
  help (h/?)       - 显示此帮助
        """,
    )

    parser.add_argument(
        "-o",
        "--objective",
        type=str,
        default="""用我的126邮箱发邮件给wbq20071104@163.com,正文：晚上好
        """,
        help="任务目标描述 (默认: 无)",
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        default="https://www.baidu.com",
        help="起始页面URL (默认: 百度)",
    )

    parser.add_argument(
        "-m", "--max-steps", type=int, default=30, help="最大步骤数 (默认: 30)"
    )

    parser.add_argument(
        "--no-browser", action="store_true", help="任务完成后自动关闭浏览器"
    )

    parser.add_argument(
        "--list-checkpoints", action="store_true", help="列出可用的检查点"
    )

    parser.add_argument(
        "-r",
        "--resume",
        type=str,
        default=None,
        metavar="CHECKPOINT_ID",
        help="从指定检查点恢复任务",
    )

    parser.add_argument("--cleanup", action="store_true", help="清理过期检查点")

    parser.add_argument(
        "--max-age",
        type=int,
        default=24,
        help="清理检查点的最大保留时间(小时) (默认: 24)",
    )

    parser.add_argument(
        "--keep-count", type=int, default=5, help="清理时保留的最少检查点数 (默认: 5)"
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="指定使用的模型ID（留空时使用第一条启用的自定义模型配置）",
    )

    parser.add_argument("--list-models", action="store_true", help="列出所有可用模型")

    return parser


def main():
    """
    主函数 - 程序入口

    【执行流程】
    1. 解析命令行参数
    2. 检查环境变量
    3. 创建 Agent 实例
    4. 执行任务或管理检查点
    """
    parser = create_parser()
    args = parser.parse_args()

    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "Web UI Agent 启动程序" + " " * 21 + "║")
    print("╚" + "═" * 58 + "╝\n")

    print("📌 正在检查自定义模型配置...")
    requested_model = args.model or get_default_model_id()
    if not requested_model:
        print("❌ 当前没有可用的自定义模型配置")
        print("请先在前端 API CONFIG 中添加并启用至少一条自定义 Provider 配置。")
        return 1

    selected_model_config = get_model_config(requested_model, include_secret=True)
    if not selected_model_config:
        print(f"❌ 未知模型: {requested_model}")
        return 1

    if not selected_model_config.get("api_key"):
        print("❌ 当前模型缺少 API Key")
        print("请在前端 API CONFIG 中补全该自定义模型的密钥。")
        return 1
    if not selected_model_config.get("api_base"):
        print("❌ 当前模型缺少 Base URL")
        print("请在前端 API CONFIG 中补全该自定义模型的 Base URL。")
        return 1
    print("✅ 自定义模型配置检查通过\n")

    reset_output_handler()

    if args.list_models:
        print("\n📋 可用模型列表:")
        print("=" * 60)
        for model_id, config in get_available_model_catalog(
            include_secrets=False
        ).items():
            is_default = " (默认)" if model_id == requested_model else ""
            is_auto = " [自定义配置]"
            print(f"\n  {model_id}{is_default}{is_auto}")
            print(f"    名称: {config['name']}")
            print(f"    描述: {config['description']}")
            print(f"    标签: {', '.join(config['tags'])}")
        print("\n" + "=" * 60)
        print(f"💡 使用 --model <模型ID> 指定初始模型")
        return 0

    try:
        agent = WebUIAgent(model=args.model)

        if args.list_checkpoints:
            print("\n📋 可用的检查点:")
            agent.list_checkpoints(limit=10)
            return 0

        if args.cleanup:
            print(
                f"\n🧹 清理过期检查点 (保留 {args.max_age} 小时内的, 至少保留 {args.keep_count} 个)..."
            )
            agent.cleanup_old_checkpoints(
                max_age_hours=args.max_age, keep_count=args.keep_count
            )
            return 0

        if args.resume:
            print(f"\n📂 从检查点恢复: {args.resume}")
            if args.max_steps:
                print(f"📊 最大步骤: {args.max_steps}")
            agent.run(
                objective=args.objective,
                resume_from_checkpoint=args.resume,
                max_steps=args.max_steps,
                keep_browser_open=not args.no_browser,
            )
        else:
            print(f"\n🎯 任务目标: {args.objective}")
            print(f"🌐 起始页面: {args.url}")
            if args.max_steps:
                print(f"📊 最大步骤: {args.max_steps}")

            agent.run(
                objective=args.objective,
                start_url=args.url,
                max_steps=args.max_steps,
                keep_browser_open=not args.no_browser,
            )

        print("\n" + "╔" + "═" * 58 + "╗")
        print("║" + " " * 18 + "程序执行完毕" + " " * 24 + "║")
        print("╚" + "═" * 58 + "╝\n")

        return 0

    except ValueError as e:
        print(f"\n❌ 配置错误: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
