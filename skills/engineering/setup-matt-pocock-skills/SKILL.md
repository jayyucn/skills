---
name: setup-matt-pocock-skills
description: 在 AGENTS.md/CLAUDE.md 以及 docs/agents/ 目录中生成 `## Agent skills` 配置区块，让工程类技能识别当前仓库的事项跟踪器（GitHub 或本地 Markdown）、分级处理标签规范以及领域文档目录结构。在首次使用 `to-issues`、`to-prd`、`triage`、`diagnose`、`tdd`、`improve-codebase-architecture`、`zoom-out` 前执行本技能；若上述技能在读取事项跟踪器、分级标签或领域文档时出现信息缺失，也需重新运行。
disable-model-invocation: true
---

# 配置 Matt Pocock 工具集
为本仓库生成配套配置，供各类工程技能正常调用，配置项包含：
- **事项跟踪器**：事项存放位置（默认支持 GitHub，也可直接使用本地 Markdown 文件）
- **分级处理标签**：五类标准分级状态对应的标签名称
- **领域文档**：`CONTEXT.md` 与架构决策记录（ADR）的存放路径，以及文档读取规则

本技能为交互式配置流程，并非固定自动化脚本。先检索仓库现有内容、展示检索结果，与用户确认信息后再写入配置。

## 执行流程
### 一、检索仓库现状
遍历仓库目录，核查现有文件与配置，不做主观预判：
- 执行 `git remote -v`、查看 `.git/config`，确认是否为 GitHub 仓库及仓库地址
- 检查仓库根目录是否存在 AGENTS.md、CLAUDE.md，以及文件内是否已有 `## Agent skills` 板块
- 检查根目录下的 CONTEXT.md、CONTEXT-MAP.md
- 检查 docs/adr/ 以及 src/*/docs/adr/ 等架构决策记录目录
- 检查 docs/agents/，判断是否已存在过往配置文件
- 检查 .scratch/ 目录，该目录存在则代表已启用本地 Markdown 事项跟踪模式

### 二、展示结果并逐项确认
汇总当前已有配置与缺失项，**分三项依次向用户确认**，不要一次性抛出所有问题。

默认假设用户不了解相关概念，每个板块先做简短说明（用途、技能依赖原因、不同选项的差异），再列出可选方案与默认配置。

#### 板块A — 事项跟踪器
> 说明：事项跟踪器用于存放项目待办事项。`to-issues`、`triage`、`to-prd`、`qa` 等技能都会读写该模块。工具需要明确调用 `gh issue create`、写入 `.scratch/` 下的 Markdown 文件，或是遵循其他自定义流程。请选择本仓库实际使用的事项管理方式。

默认规则：本工具集原生适配 GitHub。若 Git 远程地址指向 GitHub，默认推荐该项；若指向 GitLab（gitlab.com 或私有部署实例），则默认推荐 GitLab。其余场景或用户有其他需求，可选择以下选项：
- **GitHub**：事项托管在仓库的 GitHub 议题中（依赖 gh 命令行工具）
- **GitLab**：事项托管在仓库的 GitLab 议题中（依赖 [glab](https://gitlab.com/gitlab-org/cli) 命令行工具）
- **本地 Markdown**：事项以文件形式存放在仓库 `.scratch/<功能目录>/` 下（适合个人项目或无远程仓库的场景）
- **其他**（Jira、Linear 等）：请用一段话描述工作流程，本技能会以纯文本形式记录

#### 板块B — 分级处理标签
> 说明：`triage` 技能在处理新事项时，会按照状态流程流转，并匹配对应标签。请填写你仓库实际使用的标签名称，避免工具重复新建标签。

五类标准状态定义：
- `needs-triage`：待评估（维护人员需审核）
- `needs-info`：待补充信息（等待提单人回复）
- `ready-for-agent`：可交由智能体处理（信息完整，无需人工介入）
- `ready-for-human`：需人工开发
- `wontfix`：不予修复

默认配置：标签名与上述状态名称一致。可按需修改标签文本；若仓库暂无自定义标签，直接使用默认值即可。

#### 板块C — 领域文档
> 说明：`improve-codebase-architecture`、`diagnose`、`tdd` 等技能会读取 CONTEXT.md 获取项目领域术语，读取 docs/adr/ 查阅历史架构决策。需确认仓库是单套领域上下文还是多套上下文（例如前后端分离的单体多包仓库），确保工具能正确读取文档。

选择目录结构：
- **单上下文**：仓库根目录仅一份 CONTEXT.md，搭配根目录下的 docs/adr/，绝大多数仓库采用该模式
- **多上下文**：根目录存在 CONTEXT-MAP.md，由该文件指向各个业务模块独立的 CONTEXT.md（常见于单体多包仓库）

### 三、预览配置并确认
向用户展示以下内容的草稿版本，用户确认或修改后再执行写入：
1. 需要添加至 CLAUDE.md / AGENTS.md 的 `## Agent skills` 配置区块
2. 以下三份配置文件内容：`docs/agents/issue-tracker.md`、`docs/agents/triage-labels.md`、`docs/agents/domain.md`

### 四、写入配置文件
#### 选择目标编辑文件
1. 若存在 CLAUDE.md，优先编辑该文件
2. 若无 CLAUDE.md，但存在 AGENTS.md，则编辑 AGENTS.md
3. 两份文件均不存在时，询问用户新建哪一个，不自动创建

**规则**：已有其中一份文件时，绝不新建另一份；若目标文件内已存在 `## Agent skills` 区块，直接原地更新内容，不重复追加，同时保留文件内其他原有内容。

配置区块模板：
```markdown
## Agent skills

### Issue tracker
[一句话说明事项托管位置]。详见 docs/agents/issue-tracker.md。

### Triage labels
[一句话说明标签规则]。详见 docs/agents/triage-labels.md。

### Domain docs
[一句话说明文档结构：单上下文 / 多上下文]。详见 docs/agents/domain.md。
```

基于技能目录内的模板文件，生成三份独立配置文档：
- [issue-tracker-github.md](./issue-tracker-github.md)：GitHub 事项跟踪配置
- [issue-tracker-gitlab.md](./issue-tracker-gitlab.md)：GitLab 事项跟踪配置
- [issue-tracker-local.md](./issue-tracker-local.md)：本地 Markdown 事项跟踪配置
- [triage-labels.md](./triage-labels.md)：标签映射配置
- [domain.md](./domain.md)：领域文档读取规则与目录说明

若选择「其他」类型事项跟踪器，则根据用户描述手动编写 `docs/agents/issue-tracker.md`。

### 五、配置完成
告知用户配置已生效，并说明哪些工程类技能会加载当前配置。
后续可直接编辑 `docs/agents/` 下所有 md 文件；仅当需要切换事项跟踪器、重置全套配置时，才需要重新运行本技能。