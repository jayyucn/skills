#!/usr/bin/env bash
# 修复「本地 ref 指向缺失对象」造成的 fetch 自举死锁。
#
# 症状:
#   fatal: missing object <sha> for refs/remotes/<remote>/<branch>
#   git fetch <remote>  ->  fatal: bad object <sha>
#                            error: ... did not send all necessary objects
#   git log --all / for-each-ref -> fatal（因为要解析坏 ref）
#   git count-objects -v -> warning: no corresponding .pack: ...idx
#
# 根因: 远端分支存在且 sha 与本地 ref 一致，但对象从没拉到本地
#       （ref 是凭 `git ls-remote` 手工建进 packed-refs 的，对象从未到达）。
#       fetch 在「枚举本地 ref 当作 have 上报」阶段解析这些 ref -> 直接 fatal，
#       于是 fetch 永远无法补齐对象 = 自举死锁。
#
# 本脚本的解法: 完全不碰 ref —— 在仓库外建一个干净的临时裸库把对象拉下来，
#       再把生成的 pack 文件拷进主库对象库。对象一到位，坏 ref 自愈，
#       fetch / 维护任务随即恢复正常。
#
# 用法: bash heal-missing-refs.sh <repo-dir> <remote> <https-url-with-token>
#   例: bash heal-missing-refs.sh "D:/comind" comind "https://x-access-token:$TOKEN@github.com/jayyucn/comind.git"
#
# 绝不: 删分支 / update-ref -d / prune / gc --prune / 动 main / 推任何东西。
set -u

REPO="${1:?repo dir, e.g. D:/comind}"
REMOTE="${2:?remote name, e.g. comind}"
URL="${3:?https url (可内嵌 token)}"

GIT="git -C $REPO"
SCRATCH="$REPO/outputs/heal-scratch"   # 必须在 .gitignore 内，勿污染工作区

echo "== 1/5 采集坏 ref =="
BROKEN=""
while read -r ref sha; do
  if ! $GIT cat-file -e "$sha^{commit}" >/dev/null 2>&1; then
    echo "MISSING  $ref  $sha"
    BROKEN="$BROKEN $ref"
  fi
done < <($GIT for-each-ref --format='%(refname) %(objectname)' "refs/remotes/$REMOTE" 2>/dev/null)
if [ -z "$BROKEN" ]; then echo "无坏 ref，无需修复。"; exit 0; fi

echo "== 2/5 生成 refspec（去重分支名）=="
SPECS=""
BRANCHES=""
for ref in $BROKEN; do
  b="${ref#refs/remotes/$REMOTE/}"
  case " $BRANCHES " in *" $b "*) continue ;; esac
  BRANCHES="$BRANCHES $b"
  SPECS="$SPECS +refs/heads/$b:refs/heads/$b"
  echo "  -> $b"
done

echo "== 3/5 干净临时库拉取（无坏 ref，协商正常）=="
rm -rf "$SCRATCH"
$GIT --version >/dev/null
git init --bare -q "$SCRATCH" || exit 1
GIT_TERMINAL_PROMPT=0 git -C "$SCRATCH" fetch "$URL" $SPECS || {
  echo "临时库 fetch 失败：检查 token / URL。"; exit 1; }

echo "== 4/5 拷贝 pack 进主库对象库（只添加对象，零 ref 写入）=="
copied=0
for f in "$SCRATCH"/objects/pack/pack-*; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  if [ -e "$REPO/.git/objects/pack/$base" ]; then echo "  已存在，跳过 $base"; continue; fi
  cp "$f" "$REPO/.git/objects/pack/$base" && copied=$((copied+1))
done
echo "  拷入 $copied 个文件"

echo "== 5/5 核验 =="
bad=0; n=0
while read -r ref sha; do
  n=$((n+1))
  $GIT cat-file -e "$sha^{commit}" >/dev/null 2>&1 || { bad=$((bad+1)); echo "  仍缺失 $ref"; }
done < <($GIT for-each-ref --format='%(refname) %(objectname)' refs/heads refs/remotes refs/tags)
echo "  refs=$n  仍缺失=$bad"
echo "  git log --all 提交数: $($GIT log --all --oneline 2>/dev/null | wc -l)"
echo "  git fsck: $($GIT fsck --connectivity-only --no-progress >/dev/null 2>&1 && echo OK || echo FAIL)"

if [ "$bad" -eq 0 ]; then
  echo
  echo "修复完成。建议再跑一次 'git fetch $REMOTE --dry-run' 确认死锁已解除。"
  echo "临时库留在 $SCRATCH（可作备份，也可直接删）。"
else
  echo "仍有缺失 —— 可能这些分支在远端已被删除；此时才需要考虑清理 ref（先问用户）。"
fi
