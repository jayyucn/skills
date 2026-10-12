---
name: comind-core-add-column
description: 给 comind-core 某个已收敛实体新增一个持久化列（字段）时的全触点清单与验证顺序。用于「X 要支持 Y，并且要落库」类需求（如 FieldDefinition.default_value）。覆盖双存储路径（native entity/*.rs 与 wasm storage/sqljs.rs）、双 CREATE TABLE、双迁移、双写 SQL，以及 wasm-pack 缓存造成假绿、原生 cargo check 对 sqljs 空过这两个静默陷阱。
agent_created: true
---

# 给 comind-core 实体新增一个持久化列

## 触发

用户说「X 要能设置 Y」「给 <Entity> 加个字段并保存」；或出现 `no such column: <new_col>`；或 UI 改好了、点保存**没有任何报错但也没进库**。

## 前提：实体有两条互不相干的存储路径

| | 读 SQL | 写 SQL | 建表/迁移 |
|---|---|---|---|
| **native**（Tauri, rusqlite） | `storage/sqlite.rs` → `storage/entity/<name>.rs` 的 `<name>_select_cols()` + `row_to_<name>_native`（按**位置**读） | `entity/<name>.rs` 里的 `<name>_create` / `<name>_update`（整个文件几乎全是 `#[cfg(not(wasm32))]`） | `sqlite.rs` 的 `init_schema` + `migrate_add_*` |
| **wasm**（sql.js） | `storage/sqljs.rs` 内联 SELECT + `row_to_<name>_js`（按**列名**读） | `sqljs.rs` 的 `impl <X>Repository for SqlJsAdapter` 里内联 INSERT/UPDATE 文本 | `sqljs.rs` 自己的那份 `init_schema` 与 `migrate_add_*` |

`entity/<name>.rs` **不是共享层** —— 它只对 native 生效。这是最容易踩的一处：改了它不代表浏览器侧生效。

## 清单（按顺序逐项过）

1. **`types/<name>.rs`**：加字段。若同时要给 `*CreateOptions` 加字段，注意下面第 9 条。
2. **`entity/<name>.rs`**：
   - `<NAME>_COLS` **追加到末尾**（native 按位置读，插中间会全列错位）。
   - `row_to_<name>_native`：`row.get(<最后一位索引>)?`。
   - `row_to_<name>_js`：按名读，空串 → `None`（`Option<String>` 的既有约定）。
   - `<name>_create` / `<name>_update` 的 SQL + params 带上新列。
3. **`sqlite.rs` 的 `CREATE TABLE`**：加列。**必须做** —— 见陷阱 ①。
4. **`sqljs.rs` 的 `CREATE TABLE`**：同一列，逐字对称。
5. **`sqlite.rs` 迁移**：照抄相邻 `migrate_add_*` 的写法（`pragma_table_info` 守卫的 `ALTER TABLE`，幂等）。
6. **`sqljs.rs` 迁移**：同名同逻辑的另一份（`rows.iter().any(|r| r.values().any(|v| v == col))` 判定列存在）。
7. **`sqljs.rs` 的 INSERT / UPDATE 文本**：这是**独立于第 2 步的另一份写 SQL**，改漏了就「读得到、存不进」。用 `grep -n "INSERT INTO <Table>\|UPDATE <Table> SET <first_col>" storage/sqljs.rs` 找全。
8. **`services/batch.rs`**：`<entity>/create` 与 `<entity>/update` 两个分支透传新参数。若支持「显式清空」，update 用 `if params.get("k").is_some()` 的语义配合 `optional_str_param`（空串 → None）。
9. **结构体字面量完整性**：给 `*CreateOptions` 加字段后，所有构造点都要补。**`cargo check -p comind-core`（不带 `--tests`）不会编译 `#[cfg(test)]` 模块里的构造点**，漏了就是「check 过了但 `cargo test` 编译失败」。

## 三个静默陷阱

**① `open_in_memory` 只建表，不跑迁移。**
内存库路径只调 `init_schema`，`migrate_add_*` 一个都不执行。所以**新列必须写进两份 `CREATE TABLE`**，迁移只是给存量磁盘库用的。漏了的表现：单测里报 `no such column`，而线上老库反而正常。

**② 原生 `cargo check` 对 `sqljs.rs` 空过。**
`sqljs.rs` 里所有 `impl ...Repository for SqlJsAdapter` 块（约 L577 起）都挂着 `#[cfg(target_arch = "wasm32")]`，原生构建直接跳过。`Finished in 5s` 之类的快速通过**不代表你的 sqljs 改动能编译**。唯一快速的真检查是带 wasm target：
```
cargo check -p comind-core --target wasm32-unknown-unknown   # ~10s
```

**③ `npm run wasm:build` 的缓存会制造假象。**
`wasm-pack` 输出 `Finished ... in 0.50s` = 命中缓存、**一行都没重编**，不能当作「改动编译通过」。真正的重编会出现 `Compiling comind-core` 且耗时 ~30s 以上。判断依据看这两点，别只看退出码。

## 验证顺序

```bash
cd /d/comind
cargo check -p comind-core --tests                          # 含 test 内的构造点
cargo check -p comind-core --target wasm32-unknown-unknown  # 唯一快速编译 sqljs 的通道
cargo test  -p comind-core --lib                            # 对照既存红基线
npm run wasm:build                                          # 确认出现 "Compiling comind-core" 且 ~30s+
```

`cargo test -p comind-core --lib` 的**既存 4 红**（`#79`，与本次改动无关）：
`block_service_test::test_build_tree`、`render_segment_service_test::test_chinese_content_char_offsets`、`render_segment_service_test::test_link_to_nonexistent_page_skipped`、`sync::engine::tests::test_full_sync_export_empty`。**失败集合只要变了，就是你弄坏的**。

产物落点是 `crates/pkg/`（根 `pkg/` 是死副本）。TS 侧改完还要配 `npx vue-tsc --build --force` 与 `npx eslint`。

## 相关

- 实体 repository 的**三实现收敛**（不是加列）走另一条：`comind-repo-converge`。
- 新列若附带业务语义（如「打标自动填默认」），同步在 `docs/adr/` 记一条决策；写代码注释前先确认 ADR 里该编号是否已被别的决策占用（本次就撞过：代码里写的 D12 其实是「设置入口」那条）。
