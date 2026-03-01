"""
================================================================================
凭证管理命令行工具
================================================================================

【使用方法】
python credential_cli.py <命令> [参数]

【可用命令】
  login           登录凭证管理器
  add             添加新账号
  list            列出所有账号
  search <关键词>  搜索账号
  delete <id>     删除账号
  status          查看状态
  export <文件>   导出账号
  import <文件>   导入账号
  reset           重置凭证库

【示例】
# 登录/初始化
python credential_cli.py login

# 添加账号
python credential_cli.py add

# 列出所有账号
python credential_cli.py list

# 搜索账号
python credential_cli.py search 淘宝

# 查看状态
python credential_cli.py status

# 删除账号
python credential_cli.py delete <id>

# 导出/导入
python credential_cli.py export backup.json
python credential_cli.py import backup.json

# 重置凭证库
python credential_cli.py reset
================================================================================
"""

import sys
import os
import getpass
import msvcrt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from credential_manager import (
    CredentialManager,
    CredentialError,
    AuthenticationError,
    CredentialNotFoundError
)

_manager = None
_logged_in = False


def get_password_with_mask(prompt: str) -> str:
    """带星号遮罩的密码输入"""
    print(prompt, end='', flush=True)
    password = []
    while True:
        ch = msvcrt.getch()
        if ch == b'\r' or ch == b'\n':
            print()
            break
        elif ch == b'\x08' or ch == b'\x7f':
            if password:
                password.pop()
                print('\b \b', end='', flush=True)
        elif ch == b'\x03':
            print("\n已取消")
            return ""
        else:
            try:
                char = ch.decode('utf-8')
                password.append(char)
                print('*', end='', flush=True)
            except:
                pass
    return ''.join(password)


def ensure_manager():
    """确保管理器已初始化"""
    global _manager
    if _manager is None:
        _manager = CredentialManager()
    return _manager


def cmd_login(args):
    """登录凭证管理器"""
    global _logged_in
    manager = ensure_manager()
    
    if not manager.is_setup_complete():
        print("📌 首次使用，请设置主密码")
        print("   （主密码用于加密所有账号信息，请牢记！）")
        
        password = get_password_with_mask("请输入主密码: ")
        if not password:
            print("❌ 主密码不能为空")
            return False
        
        confirm = get_password_with_mask("请再次输入主密码: ")
        if password != confirm:
            print("❌ 两次密码不一致")
            return False
        
        if len(password) < 6:
            print("❌ 主密码长度不能少于6位")
            return False
        
        manager.setup(password)
        print("✅ 主密码设置成功！")
        _logged_in = True
        return True
    
    password = get_password_with_mask("主密码: ")
    if not password:
        print("❌ 密码不能为空")
        return False
    
    try:
        manager.login(password)
        print("✅ 登录成功！")
        _logged_in = True
        return True
    except AuthenticationError:
        print("❌ 主密码错误！")
        return False


def cmd_add(args):
    """添加新账号"""
    global _logged_in
    manager = ensure_manager()
    
    if not _logged_in:
        if not cmd_login([]):
            return
    
    print("\n📝 添加新账号凭证")
    print("-"*40)
    
    platform = input("平台/服务名称: ").strip()
    if not platform:
        print("❌ 平台名称不能为空")
        return
    
    username = input("用户名/账号: ").strip()
    if not username:
        print("❌ 用户名不能为空")
        return
    
    password = get_password_with_mask("密码: ")
    if not password:
        print("❌ 密码不能为空")
        return
    
    alias = input("别名 (可选): ").strip()
    notes = input("备注 (可选): ").strip()
    tags_str = input("标签 (逗号分隔，可选): ").strip()
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
    
    try:
        cred = manager.add_credential(
            platform=platform,
            username=username,
            password=password,
            alias=alias,
            notes=notes,
            tags=tags
        )
        print(f"\n✅ 添加成功！")
        print(f"   ID: {cred.id[:8]}...")
        print(f"   平台: {cred.platform}")
        print(f"   用户名: {cred.username}")
    except Exception as e:
        print(f"❌ 添加失败: {e}")


def cmd_list(args):
    """列出所有账号"""
    global _logged_in
    manager = ensure_manager()
    
    if not _logged_in:
        if not cmd_login([]):
            return
    
    creds = manager.list_all_credentials()
    
    if not creds:
        print("📭 暂无保存的账号")
        return
    
    print(f"\n📋 已保存 {len(creds)} 条账号:")
    print("="*60)
    for cred in creds:
        print(f"  [{cred['id'][:8]}] {cred['platform']}")
        print(f"           用户名: {cred['username']}")
        if cred.get('alias'):
            print(f"           别名: {cred['alias']}")
        if cred.get('tags'):
            print(f"           标签: {', '.join(cred['tags'])}")
        print()


def cmd_search(args):
    """搜索账号"""
    global _logged_in
    manager = ensure_manager()
    
    if not _logged_in:
        if not cmd_login([]):
            return
    
    keyword = args[0] if args else input("搜索关键词: ").strip()
    if not keyword:
        print("❌ 请输入搜索关键词")
        return
    
    creds = manager.search_credentials(keyword=keyword)
    
    if not creds:
        print(f"🔍 未找到匹配 '{keyword}' 的账号")
        return
    
    print(f"\n🔍 找到 {len(creds)} 条匹配账号:")
    print("="*60)
    for cred in creds:
        print(f"  [{cred['id'][:8]}] {cred['platform']}")
        print(f"           用户名: {cred['username']}")
        if cred.get('alias'):
            print(f"           别名: {cred['alias']}")
        print()


def cmd_delete(args):
    """删除账号"""
    global _logged_in
    manager = ensure_manager()
    
    if not _logged_in:
        if not cmd_login([]):
            return
    
    cred_id = args[0] if args else input("要删除的账号ID: ").strip()
    if not cred_id:
        print("❌ 请输入账号ID")
        return
    
    try:
        cred = manager.get_credential(cred_id)
        print(f"\n将要删除: {cred['platform']} - {cred['username']}")
        
        confirm = input("确认删除? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        manager.delete_credential(cred_id)
        print("✅ 删除成功！")
    except CredentialNotFoundError:
        print("❌ 账号不存在")
    except Exception as e:
        print(f"❌ 删除失败: {e}")


def cmd_status(args):
    """查看状态"""
    global _logged_in
    manager = ensure_manager()
    
    print("\n🔐 凭证管理器状态")
    print("="*40)
    print(f"  已初始化: {'是' if manager.is_setup_complete() else '否'}")
    print(f"  已登录: {'是' if _logged_in else '否'}")
    
    if manager.is_setup_complete() and not _logged_in:
        print("\n  💡 登录后可查看账号数量")
        try_login = input("  是否登录查看详情? (y/n): ").strip().lower()
        if try_login == 'y':
            if cmd_login([]):
                status = manager.get_status()
                print(f"\n  账号数量: {status.get('credential_count', 0)}")
                print(f"  平台数量: {status.get('platform_count', 0)}")
                print(f"  标签数量: {status.get('tag_count', 0)}")
    elif _logged_in:
        status = manager.get_status()
        print(f"  账号数量: {status.get('credential_count', 0)}")
        print(f"  平台数量: {status.get('platform_count', 0)}")
        print(f"  标签数量: {status.get('tag_count', 0)}")


def cmd_export(args):
    """导出账号"""
    global _logged_in
    manager = ensure_manager()
    
    if not _logged_in:
        if not cmd_login([]):
            return
    
    output_file = args[0] if args else "credentials_export.json"
    
    try:
        count = manager.export_data(output_file, include_passwords=True)
        print(f"✅ 已导出 {count} 条账号到 {output_file}")
    except Exception as e:
        print(f"❌ 导出失败: {e}")


def cmd_import(args):
    """导入账号"""
    global _logged_in
    manager = ensure_manager()
    
    if not _logged_in:
        if not cmd_login([]):
            return
    
    input_file = args[0] if args else input("导入文件路径: ").strip()
    if not input_file:
        print("❌ 请输入文件路径")
        return
    
    try:
        stats = manager.import_data(input_file)
        print(f"✅ 导入完成:")
        print(f"   添加: {stats['added']}")
        print(f"   跳过: {stats['skipped']}")
        print(f"   错误: {stats['error']}")
    except Exception as e:
        print(f"❌ 导入失败: {e}")


def cmd_reset(args):
    """重置凭证库"""
    print("\n⚠️ 警告: 此操作将删除所有已保存的账号！")
    confirm = input("确认重置? (输入 'yes' 确认): ").strip().lower()
    
    if confirm != 'yes':
        print("已取消")
        return
    
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credential_data")
    
    import shutil
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    
    global _manager, _logged_in
    _manager = None
    _logged_in = False
    
    print("✅ 凭证库已重置")
    print("请使用 'python credential_cli.py login' 重新初始化")


def print_help():
    """打印帮助信息"""
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_help()
        return
    
    command = sys.argv[1].lower()
    args = sys.argv[2:]
    
    commands = {
        'login': cmd_login,
        'add': cmd_add,
        'list': cmd_list,
        'search': cmd_search,
        'delete': cmd_delete,
        'status': cmd_status,
        'export': cmd_export,
        'import': cmd_import,
        'reset': cmd_reset,
        'help': lambda x: print_help(),
    }
    
    if command in commands:
        commands[command](args)
    else:
        print(f"❌ 未知命令: {command}")
        print("使用 'python credential_cli.py help' 查看帮助")


if __name__ == "__main__":
    main()
