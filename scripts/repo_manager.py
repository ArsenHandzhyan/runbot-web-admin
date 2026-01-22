#!/usr/bin/env python3
"""
Автоматический менеджер репозиториев RunBot
Позволяет выполнять действия в репозиториях через единый интерфейс
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import json

class RepoManager:
    """Управление репозиториями"""

    REPOS = {
        'web': {
            'path': '/Users/arsen/Desktop/RunBot/runbot-web-repo',
            'default_branch': 'main',
            'auto_branch': 'feat/moderation-stabilize'
        },
        'core': {
            'path': '/Users/arsen/Desktop/RunBot/runbot',
            'default_branch': 'master',
            'auto_branch': 'master'
        }
    }

    def __init__(self, repo_name: str):
        if repo_name not in self.REPOS:
            raise ValueError(f"Репозиторий {repo_name} не найден")
        self.repo_name = repo_name
        self.repo_path = Path(self.REPOS[repo_name]['path'])
        self.default_branch = self.REPOS[repo_name]['default_branch']
        self.auto_branch = self.REPOS[repo_name]['auto_branch']

    def run_command(self, command: str, capture_output: bool = True) -> subprocess.CompletedProcess:
        """Выполнить команду в репозитории"""
        full_command = f"cd {self.repo_path} && {command}"
        if capture_output:
            result = subprocess.run(full_command, shell=True, capture_output=True, text=True)
        else:
            result = subprocess.run(full_command, shell=True, text=True)
        return result

    def status(self) -> Dict[str, Any]:
        """Получить статус репозитория"""
        status_result = self.run_command("git status --short")
        branch_result = self.run_command("git rev-parse --abbrev-ref HEAD")
        ahead_behind_result = self.run_command("git rev-list --left-right --count HEAD...@{u} 2>/dev/null || echo '0 0'")

        return {
            'repo': self.repo_name,
            'branch': branch_result.stdout.strip(),
            'status': status_result.stdout.strip(),
            'ahead_behind': ahead_behind_result.stdout.strip(),
            'clean': not status_result.stdout.strip()
        }

    def add_and_commit(self, message: str, files: str = ".") -> bool:
        """Добавить и закоммитить изменения"""
        add_result = self.run_command(f"git add {files}")
        if add_result.returncode != 0:
            print(f"Ошибка git add: {add_result.stderr}")
            return False

        commit_result = self.run_command(f'git commit -m "{message}"')
        if commit_result.returncode != 0:
            if "nothing to commit" in commit_result.stdout:
                print("Нечего коммитить")
                return True
            print(f"Ошибка git commit: {commit_result.stderr}")
            return False

        return True

    def push(self, branch: Optional[str] = None, force: bool = False) -> bool:
        """Запушить изменения"""
        branch = branch or self.auto_branch
        force_flag = "-f" if force else ""
        push_result = self.run_command(f"git push {force_flag} -u origin {branch}")
        return push_result.returncode == 0

    def pull(self, branch: Optional[str] = None) -> bool:
        """Запулить изменения"""
        branch = branch or self.auto_branch
        pull_result = self.run_command(f"git pull origin {branch}")
        return pull_result.returncode == 0

    def create_branch(self, branch_name: str, from_branch: Optional[str] = None) -> bool:
        """Создать новую ветку"""
        from_branch = from_branch or self.default_branch
        checkout_result = self.run_command(f"git checkout {from_branch}")
        if checkout_result.returncode != 0:
            return False

        branch_result = self.run_command(f"git checkout -b {branch_name}")
        return branch_result.returncode == 0

    def merge_branch(self, source_branch: str, target_branch: Optional[str] = None) -> bool:
        """Слить ветку"""
        target_branch = target_branch or self.default_branch
        checkout_result = self.run_command(f"git checkout {target_branch}")
        if checkout_result.returncode != 0:
            return False

        merge_result = self.run_command(f"git merge {source_branch} --no-edit")
        if merge_result.returncode != 0:
            print(f"Конфликт при слиянии: {merge_result.stderr}")
            return False

        return True

    def create_feature_branch(self, feature_name: str) -> bool:
        """Создать feature ветку"""
        branch_name = f"feat/{feature_name}"
        return self.create_branch(branch_name)

    def auto_commit_and_push(self, message: str) -> bool:
        """Автоматически добавить, закоммитить и запушить"""
        if not self.add_and_commit(message):
            return False
        return self.push()

    def log(self, count: int = 5) -> str:
        """Показать логи"""
        log_result = self.run_command(f"git log --oneline -{count}")
        return log_result.stdout

def manage_all_repos() -> None:
    """Управление всеми репозиториями"""
    manager_web = RepoManager('web')
    manager_core = RepoManager('core')

    print("=" * 50)
    print("СТАТУС ВСЕХ РЕПОЗИТОРИЕВ")
    print("=" * 50)

    for manager in [manager_web, manager_core]:
        status = manager.status()
        print(f"\n{status['repo'].upper()}:")
        print(f"  Ветка: {status['branch']}")
        print(f"  Чисто: {status['clean']}")
        print(f"  Статус: {status['status']}")
        print(f"  Впереди/Позади: {status['ahead_behind']}")

        if not status['clean']:
            print("  Есть изменения!")
            print(f"  Лог (последние коммиты):\n{manager.log()}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Использование: python repo_manager.py <команда> [аргументы]")
        print("\nКоманды:")
        print("  status          - показать статус всех репозиториев")
        print("  push [web|core] [ветка] - запушить изменения")
        print("  pull [web|core] [ветка] - запулить изменения")
        print("  commit <message> [web|core] - закоммитить изменения")
        print("  create-branch <имя> [web|core] - создать ветку")
        print("  merge <исходная> <целевая> [web|core] - слить ветки")
        sys.exit(1)

    command = sys.argv[1]

    if command == "status":
        manage_all_repos()

    elif command == "push":
        repo = sys.argv[2] if len(sys.argv) > 2 else "web"
        branch = sys.argv[3] if len(sys.argv) > 3 else None
        manager = RepoManager(repo)
        if manager.push(branch):
            print(f"✅ Успешно запушено {repo} -> {branch}")
        else:
            print(f"❌ Ошибка при пуше {repo}")

    elif command == "pull":
        repo = sys.argv[2] if len(sys.argv) > 2 else "web"
        branch = sys.argv[3] if len(sys.argv) > 3 else None
        manager = RepoManager(repo)
        if manager.pull(branch):
            print(f"✅ Успешно запулено {repo} -> {branch}")
        else:
            print(f"❌ Ошибка при пуле {repo}")

    elif command == "commit":
        message = sys.argv[2] if len(sys.argv) > 2 else "auto commit"
        repo = sys.argv[3] if len(sys.argv) > 3 else "web"
        manager = RepoManager(repo)
        if manager.add_and_commit(message):
            print(f"✅ Успешно закоммичено {repo}")
        else:
            print(f"❌ Ошибка при коммите {repo}")

    elif command == "create-branch":
        branch_name = sys.argv[2] if len(sys.argv) > 2 else "new-feature"
        repo = sys.argv[3] if len(sys.argv) > 3 else "web"
        manager = RepoManager(repo)
        if manager.create_feature_branch(branch_name):
            print(f"✅ Создана ветка feat/{branch_name} в {repo}")
        else:
            print(f"❌ Ошибка при создании ветки {repo}")

    elif command == "merge":
        source = sys.argv[2] if len(sys.argv) > 2 else None
        target = sys.argv[3] if len(sys.argv) > 3 else None
        repo = sys.argv[4] if len(sys.argv) > 4 else "web"
        manager = RepoManager(repo)
        if source and target and manager.merge_branch(source, target):
            print(f"✅ Слияние {source} -> {target} в {repo} выполнено")
        else:
            print(f"❌ Ошибка при слиянии {repo}")

    else:
        print(f"Неизвестная команда: {command}")
        sys.exit(1)
