```bash
#!/usr/bin/env bash
# 人机交互式问题复现脚本
# 复制本文件，修改下方步骤后即可运行
# 由智能体执行脚本，用户根据终端提示进行操作
#
# 使用方法：
#   bash hitl-loop.template.sh
#
# 两个内置工具函数：
#   step "<操作说明>"          → 展示操作指引，按下回车键继续
#   capture 变量名 "<提问内容>" → 展示问题，将用户输入存入指定变量
#
# 脚本末尾会以 键=值 格式输出采集内容，供智能体解析

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [完成后按回车] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- 请在下方编辑内容 ---------------------------------------------------------

step "打开应用，访问地址：http://localhost:3000 并完成登录。"

capture ERRORED "点击「导出」按钮。是否弹出报错？(y/n)"

capture ERROR_MSG "粘贴报错信息（若无报错请输入 none）："

# --- 请在上方编辑内容 ---------------------------------------------------------

printf '\n--- 采集结果 ---\n'
printf 'ERRORED=%s\n' "$ERRORED"
printf 'ERROR_MSG=%s\n' "$ERROR_MSG"
```