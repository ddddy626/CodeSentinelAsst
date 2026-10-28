"""Bootstrap the first administrator without a public registration endpoint."""

import argparse
import getpass

from .storage import Store

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    args = parser.parse_args()
    password = getpass.getpass("新管理员密码（至少 12 字符）: ")
    confirm = getpass.getpass("确认密码: ")
    if password != confirm:
        raise SystemExit("两次密码不一致")
    store = Store()
    user_id = store.create_user(args.username, password, is_admin=True)
    print(f"已创建管理员 {args.username} ({user_id})")

if __name__ == "__main__":
    main()
