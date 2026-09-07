---
name: comind-repo-converge
description: Collapse one entity's triple-written Repository implementations in comind-core (SQLiteAdapter + SQLiteTransactionAdapter + SqlJsAdapter) onto the shared entity/ module + Executor trait pattern. Use when migrating the next entity in the ADR-0018 repository-convergence rollout (Link, Property, RelationshipType, Template, Search, BlockVersion, Notification, SavedFilter, ScreenView, NotificationConfig).
agent_created: true
---

# Collapse a comind-core storage entity onto the shared module

Rolled out entity-by-entity per ADR-0018. Each entity: create `crates/comind-core/src/storage/entity/<name>.rs`, wire `mod.rs`, then replace the two rusqlite impls (`sqlite.rs`) with 1-line delegating stubs and rewrite the wasm impl (`sqljs.rs`) SELECTs to use the shared column list + row mapper.

## Trigger
User says "开 <Entity>" / "start <Entity>" / "collapse <Entity>" in the comind project while the `refactor-repository-convergence` branch is active.

## Hard rules (from AGENTS.md)
- Read `D:\comind\AGENTS.md` before editing.
- Touch ONLY the entity being migrated. Never refactor surrounding code.
- Verify with the three commands below before committing.
- Skip review gate: entities accumulate into the already-open PR #43 on branch `refactor-repository-convergence`.
- NEVER `git push origin` (SSH, fails). Always push remote `comind` (HTTPS) with token + credential helper disabled.

## Step 1 — read the trait + 3 impls + type
Grep `trait <X>Repository`, the three `impl <X>Repository` sites (`sqlite.rs` native ~L445+, `sqlite.rs` transaction ~L2549+, `sqljs.rs`), and `types/<name>.rs`. Note:
- the struct field order (becomes canonical `COLS` order = native positional order),
- any SearchIndex side-effect in native `create`/`update`/`delete` (only Block has it; Page/Link/DateRef don't — see ADR-0018 Page landing record),
- **any explicit `transaction()`/`commit()` wrapper in native batch methods** (e.g. pre-pilot `Link::create_many` wrapped its loop in `self.conn.transaction()`; DateRef `create_many` / Notification `batch_create` do NOT wrap). If present, the delegating `SQLiteAdapter` stub MUST re-wrap: `let tx = self.conn.transaction()?; <x>_create_many(&tx, ...)?; tx.commit()?;` — the shared loop alone is NOT atomic on `&Connection` (real regression hit in PR #43: `link_create_many` lost atomicity). The tx-path stub passes `&self.conn` (`&Transaction`) and needs NO wrap (already atomic). Verify with: `grep -n "fn create_many\|fn batch_create" sqlite.rs` and eyeball each native batch stub against its pre-pilot body.
- WHERE-clause / INSERT-text divergences between native and wasm (keep wasm's text as-is unless converging is safe).

## Step 2 — create `entity/<name>.rs` (template)
Model exactly on `entity/link.rs` (smallest, cleanest). Key pieces:
- `pub const <NAME>_COLS: &[&str] = &["id", ...];` — canonical order = struct field order.
- `pub fn <name>_select_cols() -> String { <NAME>_COLS.join(", ") }`
- `#[cfg(not(wasm32))] pub fn <name>_insert_sql() -> String` built from `<name>_select_cols()` + `vec!["?"; N].join(", ")`.
- `#[cfg(not(wasm32))] pub fn row_to_<name>_native(row: &rusqlite::Row) -> Result<X, rusqlite::Error>` — `row.get(0)?` … in COLS order.
- `#[cfg(any(wasm32, test))] pub fn row_to_<name>_js(row: &HashMap<String,String>) -> X` — read by name; preserve wasm coercions (empty-string→None for Option<String>, parse-fail→None for `deleted_at`, numeric defaults `0`).
- `#[cfg(not(wasm32))] pub fn <name>_params(x: &X) -> Vec<&dyn ToSql>` in COLS order.
- `#[cfg(not(wasm32))] pub fn <name>_get_by_id<E: Executor>(exec: &E, id: &str) -> Result<X, Box<dyn Error>>` etc. — one free fn per repo method, generic over `E: Executor`. Use `exec.query_map(&sql, &params, |row| row_to_<name>_native(row)).map_err(bx)` and `exec.execute(&sql, &params)?`. For single-row getters, take `.into_iter().next().ok_or_else(|| NotFound)` like `block_get_by_id`.
- `#[cfg(test)] mod tests` with 2 `row_to_<name>_js` roundtrip cases.
- Imports gated: `use crate::storage::executor::Executor;` / `use rusqlite::ToSql;` / `use std::error::Error;` under `#[cfg(not(wasm32))]`; `use std::collections::HashMap;` always.

## Step 3 — wire `entity/mod.rs`
Add `pub mod <name>;` (alphabetical-ish, doesn't matter).

## Step 4 — replace the two sqlite.rs impls via the brace-matcher script
**DO NOT edit by hand — the two impls are large and byte-identical.** Use the string-literal-skipping brace matcher below. The trap we hit TWICE: a naive `\nimpl ` terminator or a bare brace counter overruns because impl bodies contain `format!("…IN ({})…")` whose `{}` looks like braces. The matcher must (a) skip string/char literals + comments when counting braces, and (b) match BOTH header forms via regex `impl(?:<[^>]*>)? <Trait> for`.

Write `replace_<name>_sqlite.py` next to `sqlite.rs`:
```python
import re, sys
PATH = "crates/comind-core/src/storage/sqlite.rs"
src = open(PATH, encoding="utf-8").read()
STUB_BODY = """    fn get_by_id(&self, id: &str) -> Result<X, Box<dyn Error>> {
        <name>_get_by_id(&self.conn, id)
    }
    # ... one 1-line delegating stub per trait method ...
"""
def find_block_end(s, o):
    i, depth = o, 0
    in_s = in_c = in_l = in_b = False
    while i < len(s):
        c = s[i]; n = s[i+1] if i+1 < len(s) else ""
        if in_l:
            if c == "\n": in_l = False
            i += 1; continue
        if in_b:
            if c == "*" and n == "/": in_b = False; i += 2; continue
            i += 1; continue
        if in_s:
            if c == "\\": i += 2; continue
            if c == '"': in_s = False
            i += 1; continue
        if in_c:
            if c == "\\": i += 2; continue
            if c == "'": in_c = False
            i += 1; continue
        if c == "/" and n == "/": in_l = True; i += 2; continue
        if c == "/" and n == "*": in_b = True; i += 2; continue
        if c == '"': in_s = True; i += 1; continue
        if c == "'": in_c = True; i += 1; continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i
        i += 1
    return -1
pat = re.compile(r"impl(?:<[^>]*>)? <Trait>Repository for")
out, last, n = [], 0, 0
for m in pat.finditer(src):
    bo = src.find("{", m.start())
    end = find_block_end(src, bo)
    assert end != -1, "no matching }"
    out.append(src[last:m.start()]); out.append(src[m.start():bo] + " {\n" + STUB_BODY + "}")
    n += 1; last = end + 1
open(PATH, "w", encoding="utf-8").write("".join(out) + src[last:])
print(f"replaced {n} impl block(s)")
```
Run: `cd /d/comind/comind && python3 crates/comind-core/src/storage/replace_<name>_sqlite.py`. Then VERIFY boundaries: grep `impl <Trait>Repository for` / `impl<'a> <Trait>Repository for` show exactly 2 hits with `&self.conn` stubs, and the adjacent `PropertyRepository` (and other) impls are untouched.

Also add the import line to `sqlite.rs` (under `#[cfg(not(wasm32))]`):
`use crate::storage::entity::<name>::{<name>_get_by_id, ...};`

## Step 5 — rewrite sqljs.rs
Add import `#[cfg(target_arch = "wasm32")] use crate::storage::entity::<name>::{<name>_select_cols, row_to_<name>_js};`.
Then for each SELECT method: `Self::query(&self.db, &format!("SELECT {} FROM <Table> WHERE …", <name>_select_cols()), &params)` and map via `row_to_<name>_js`. Remove the now-dead standalone `fn row_to_<name>`. **Keep wasm INSERT/UPDATE/DELETE text as-is** unless converging is provably behavior-preserving. (Optional, safe: convert a per-item loop `get_by_x` into a batch `IN (...)` to match native — Link did this for `get_by_source_block_ids`.)

## Step 6 — verify
```
cd /d/comind/comind
cargo check -p comind-core --tests            # native, expect 0 warnings
cargo check -p comind-core --target wasm32-unknown-unknown   # wasm, expect 0 warnings
cargo test -p comind-core --lib               # expect +2 new js tests; 4 pre-existing failures
```
The 4 pre-existing failures are ALWAYS: `services::block_service_test::test_build_tree`, `services::render_segment_service_test::test_chinese_content_char_offsets`, `services::render_segment_service_test::test_link_to_nonexistent_page_skipped`, `sync::engine::tests::test_full_sync_export_empty`. If the failure SET changes, you broke something.

## Step 7 — commit + push
Stage ONLY the entity files (link.rs, mod.rs, sqlite.rs, sqljs.rs, the two docs). Do NOT stage `replace_*.py` (untracked, leave on disk) and do NOT touch the user's unrelated `.vue` changes.
```
git add <the 6 paths>
git commit -m "refactor(storage): converge <Entity> repo impls via shared module + Executor trait"
TOKEN=$(gh auth token) && GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c "url.https://x-access-token:${TOKEN}@github.com/.insteadOf=https://github.com/" push comind refactor-repository-convergence
```
Then append a "## Pilot landing record — <Entity>" section to `docs/adr/0018-repository-convergence.md` and update "Done/Remaining" in `docs/refactor-repository-convergence.md`.

## Rollout order
DateRef ✅ Block ✅ Page ✅ Link ✅ → **Property → RelationshipType → Template → Search → BlockVersion → Notification → SavedFilter → ScreenView → NotificationConfig** → delete `SQLiteTransactionAdapter` (Q3a).
