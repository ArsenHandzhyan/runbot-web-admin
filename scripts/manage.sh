#!/bin/bash
# Автоматическое управление репозиториями RunBot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/repo_manager.py"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

case "$1" in
  status)
    echo -e "${YELLOW}Статус всех репозиториев:${NC}"
    python3 "$PYTHON_SCRIPT" status
    ;;
  push)
    REPO="${2:-web}"
    BRANCH="${3:-}"
    echo -e "${YELLOW}Пуш изменений в $REPO${NC}"
    python3 "$PYTHON_SCRIPT" push "$REPO" "$BRANCH"
    ;;
  pull)
    REPO="${2:-web}"
    BRANCH="${3:-}"
    echo -e "${YELLOW}Пул изменений в $REPO${NC}"
    python3 "$PYTHON_SCRIPT" pull "$REPO" "$BRANCH"
    ;;
  commit)
    MESSAGE="${2:-auto commit}"
    REPO="${3:-web}"
    echo -e "${YELLOW}Коммит в $REPO: $MESSAGE${NC}"
    python3 "$PYTHON_SCRIPT" commit "$MESSAGE" "$REPO"
    ;;
  push-all)
    echo -e "${YELLOW}Пуш всех репозиториев${NC}"
    for repo in web core; do
      echo -e "${YELLOW}Пуш $repo...${NC}"
      python3 "$PYTHON_SCRIPT" push "$repo"
    done
    ;;
  auto-pr)
    echo -e "${YELLOW}Автоматический PR через GitHub Actions${NC}"
    echo "Это действие запускается автоматически при пуше в ветки feat/*"
    echo "Для запуска вручную перейдите на GitHub и запустите workflow"
    ;;
  *)
    echo -e "${RED}Использование:${NC}"
    echo "  $0 status              - показать статус всех репозиториев"
    echo "  $0 push [web|core] [ветка] - запушить изменения"
    echo "  $0 pull [web|core] [ветка] - запулить изменения"
    echo "  $0 commit <сообщение> [web|core] - закоммитить изменения"
    echo "  $0 push-all            - запушить все репозитории"
    echo "  $0 auto-pr             - информация о автоматических PR"
    exit 1
    ;;
esac
