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
├── config.py      # 配置常量
├── state.py       # 状态定义
├── utils.py       # 辅助函数
├── nodes.py       # 图节点实现
├── agent.py       # Agent 类封装
└── main.py        # 主程序入口（本文件）
================================================================================
"""

import os

from config import ENV_API_KEY_NAME
from agent import WebUIAgent


def main():
    """
    主函数 - 程序入口
    
    【执行流程】
    1. 检查环境变量
    2. 创建 Agent 实例
    3. 执行测试任务
    4. 输出结果
    """
    print("\n" + "╔"+"═"*58+"╗")
    print("║" + " "*15 + "Web UI Agent 启动程序" + " "*21 + "║")
    print("╚"+"═"*58+"╝\n")
    
    print("📌 正在检查环境变量...")
    api_key = os.environ.get(ENV_API_KEY_NAME)
    if not api_key:
        print(f"⚠️ 未检测到 {ENV_API_KEY_NAME} 环境变量")
        print("请设置环境变量后重试。")
        print("\nWindows PowerShell 设置方法:")
        print('  $env:LINGYAAI_API_KEY="你的API密钥"')
        return 1
    print("✅ 环境变量检查通过\n")
    
    try:
        agent = WebUIAgent()
        
        objective = "在百度搜索 LangGraph 教程"
        start_url = "https://www.baidu.com"
        
        agent.run(objective, start_url)
        """
        浏览器页面开关器使用方法
        # 默认行为：任务完成后保持浏览器打开
        agent.run("在百度搜索 LangGraph 教程", "https://www.baidu.com")

        # 自动关闭浏览器（原有行为）
        agent.run("在百度搜索 LangGraph 教程", "https://www.baidu.com", keep_browser_open=False)
        """
        
        print("\n" + "╔"+"═"*58+"╗")
        print("║" + " "*18 + "程序执行完毕" + " "*24 + "║")
        print("╚"+"═"*58+"╝\n")
        
        return 0
        
    except ValueError as e:
        print(f"\n❌ 配置错误: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
