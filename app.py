# app.py（先頭）
import streamlit as st
st.set_page_config(page_title="月次入力", layout="wide")

from auth_guard import auth_guard
auth_guard()

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import calendar
from datetime import date, datetime, timedelta

# -----------------------------
# Path（先に定義）
# -----------------------------
TABLE = "records"

# ここにUIは置かない（関数定義がまだ）

# 取引先（売上）
CLIENT_COLS = ["U", "出", "R", "W", "menu", "しょんぴ", "Afrex", "Afresh", "ハコベル", "pickg", "その他"]

# スキーマ（並び保証）
COLUMNS = [
    "日付", "合計売上", "合計h", "frex h", "fresh h", "他 h", "合計時給", "5h+", "警告",
    *CLIENT_COLS,
    "メモ"
]

def ensure_clients_map():
    if "clients_map" not in st.session_state:
        st.session_state["clients_map"] = {c: "" for c in CLIENT_COLS}

def on_client_change():
    # 取引先を変えたら、その取引先の金額を入力欄に反映
    ensure_clients_map()
    c = st.session_state.get("client_sel", CLIENT_COLS[0])
    st.session_state["client_amount"] = int(st.session_state["clients_map"].get(c, 0) or 0)
    st.session_state["client_amount_text"] = "" if not st.session_state.get("client_amount") else str(st.session_state["client_amount"])

def on_amount_change():
    ensure_clients_map()
    c = st.session_state.get("client_sel", CLIENT_COLS[0])
    v = int(st.session_state.get("client_amount", 0) or 0)
    st.session_state["clients_map"][c] = v

from typing import Callable, TypeVar, Any
T = TypeVar("T")

def run_db(label: str, fn: Callable[[], T], default: T | None = None) -> T | None:
    """
    DB処理の共通ラッパー
    - 成功: fn()の結果を返す
    - 失敗: st.error でユーザー向け表示 + st.exception で詳細表示（ログにも出る）して default を返す
    """
    try:
        return fn()
    except Exception as e:
        st.error(f"DBエラー: {label} に失敗しました。設定や接続状態を確認してください。")
        st.caption(f"詳細: {type(e).__name__}: {e}")
        sys.stderr.write(f"[DB-ERROR] {label}: {type(e).__name__}: {e}\n"); sys.stderr.flush()
        st.exception(e)  # Railway Logsにも出る
        return default

# -----------------------------
# Supabase(Postgres) 固定
#   - SUPABASE_DB_URL が必須
# -----------------------------
def _pg_url() -> str:
    url = os.getenv("SUPABASE_DB_URL") or st.secrets.get("SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL が未設定だよ（Railway Variables / ローカルsecrets を確認）")
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    if "connect_timeout=" not in url:
        url += ("&" if "?" in url else "?") + "connect_timeout=5"
    return url

def _pg_connect():
    return psycopg2.connect(_pg_url())

def init_db():
    """Postgres にテーブルが無ければ作る（全カラムTEXT / PK=日付）"""
    col_defs = []
    for c in COLUMNS:
        if c == "日付":
            col_defs.append(f'"{c}" TEXT PRIMARY KEY')
        else:
            col_defs.append(f'"{c}" TEXT')

    create_sql = f'CREATE TABLE IF NOT EXISTS "{TABLE}" (\n  ' + ",\n  ".join(col_defs) + "\n);"

    pcon = _pg_connect()
    try:
        with pcon.cursor() as cur:
            cur.execute(create_sql)
        pcon.commit()
    finally:
        pcon.close()

# Railway Logs で確認用（postgres固定）
sys.stderr.write("[DB] backend=postgres\n")
sys.stderr.flush()

def load_df() -> pd.DataFrame:
    def _do():
        init_db()

        pcon = _pg_connect()
        try:
            with pcon.cursor() as cur:
                cur.execute(f'SELECT * FROM "{TABLE}";')
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
            df = pd.DataFrame(rows, columns=cols)
        finally:
            pcon.close()

        # 足りない列を補完して順番を揃える
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = ""
        df = df[COLUMNS]

        # 日付でソート
        if not df.empty:
            df["_sort"] = pd.to_datetime(df["日付"], errors="coerce")
            df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

        return df

    out = run_db("データ読み込み（load_df）", _do)
    return out if isinstance(out, pd.DataFrame) else pd.DataFrame(columns=COLUMNS)


def load_row_safe(date_key: str) -> dict | None:
    """DBエラー時は st.error を出して None を返す（UI側はこれを使う）"""
    def _do():
        return load_row(date_key)
    return run_db("データ取得（load_row）", _do, default=None)

def load_row(date_key: str) -> dict | None:
    init_db()

    pcon = _pg_connect()
    try:
        with pcon.cursor() as cur:
            cur.execute(f'SELECT * FROM "{TABLE}" WHERE "日付" = %s LIMIT 1;', (date_key,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
    finally:
        pcon.close()

    data = dict(zip(cols, row))
    for c in COLUMNS:
        data.setdefault(c, "")
    return data

def upsert_row(row: dict) -> bool:
    def _do() -> bool:
        init_db()

        cols = COLUMNS
        values = ["" if row.get(c) is None else str(row.get(c, "")) for c in cols]

        colnames = ", ".join([f'"{c}"' for c in cols])
        placeholders = ", ".join(["%s"] * len(cols))
        update_set = ", ".join([f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "日付"])

        sql = f"""
            INSERT INTO "{TABLE}" ({colnames})
            VALUES ({placeholders})
            ON CONFLICT("日付") DO UPDATE SET
            {update_set};
        """

        pcon = _pg_connect()
        try:
            with pcon.cursor() as cur:
                cur.execute(sql, values)
            pcon.commit()
            return True
        finally:
            pcon.close()

    # run_db は「失敗時に st.error + ログ出し」して False を返す想定
    return run_db("保存（upsert）", _do, default=False)

def delete_by_dates(date_keys: set[str]) -> bool:
    if not date_keys:
        return True

    def _do() -> bool:
        init_db()
        keys = [str(k) for k in sorted(date_keys)]

        placeholders = ", ".join(["%s"] * len(keys))
        sql = f'DELETE FROM "{TABLE}" WHERE "日付" IN ({placeholders});'

        pcon = _pg_connect()
        try:
            with pcon.cursor() as cur:
                cur.execute(sql, keys)
            pcon.commit()
            return True
        finally:
            pcon.close()

    return run_db("削除（delete_by_dates）", _do, default=False)

def delete_by_month_prefix(month_prefix: str) -> bool:
    """
    month_prefix: 'YYYY-MM' を想定
    例) 2026-02 を渡すと 2026-02- の全行を削除
    """
    if not month_prefix:
        return True

    def _do() -> bool:
        init_db()
        like = f"{month_prefix}-%"
        sql = f'DELETE FROM "{TABLE}" WHERE "日付" LIKE %s;'

        pcon = _pg_connect()
        try:
            with pcon.cursor() as cur:
                cur.execute(sql, (like,))
            pcon.commit()
            return True
        finally:
            pcon.close()

    return bool(run_db(f"削除（delete_by_month_prefix {month_prefix}）", _do, default=False))

# -----------------------------
# 入力パース（空欄OK）
# -----------------------------
def to_int(s):
    if s is None:
        return None
    # number_input から int/float が来てもOKにする
    if isinstance(s, (int, float)):
        try:
            return int(s)
        except:
            return None

    s = str(s).strip()
    if s == "":
        return None
    try:
        # "1,234" とか "6.0" とかも一応許す
        s = s.replace(",", "")
        return int(float(s))
    except:
        return None

def to_float(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        try:
            return float(s)
        except:
            return None

    s = str(s).strip()
    if s == "":
        return None
    try:
        s = s.replace(",", "")
        return float(s)
    except:
        return None

def to_cell_int(v):
    return "" if (v is None or v == 0) else int(v)

def to_cell_float(v):
    return "" if (v is None or v == 0) else float(v)
import json

def _norm_text(v) -> str:
    if v is None:
        return ""
    return str(v).strip()

def _current_payload() -> dict:
    """画面の入力状態を比較用に正規化してまとめる"""
    ensure_clients_map()
    m = st.session_state.get("clients_map", {}) or {}

    clients = {c: int(to_int(m.get(c)) or 0) for c in CLIENT_COLS}

    return {
        "total_h_s": _norm_text(st.session_state.get("total_h_s", "")),
        "frex_h_s":  _norm_text(st.session_state.get("frex_h_s", "")),
        "fresh_h_s": _norm_text(st.session_state.get("fresh_h_s", "")),
        "memo":      _norm_text(st.session_state.get("memo", "")),
        "clients":   clients,
    }

def _sig(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)

# -----------------------------
# 日付変更：入力のクリア/復元
# -----------------------------
def clear_inputs():
    st.session_state["memo"] = ""
    st.session_state["total_h_s"] = ""
    st.session_state["frex_h_s"] = ""
    st.session_state["fresh_h_s"] = ""
    st.session_state["clients_map"] = {c: "" for c in CLIENT_COLS}

def load_inputs_from_row(row: dict):
    st.session_state["memo"] = row.get("メモ", "") or ""
    st.session_state["total_h_s"] = str(row.get("合計h", "") or "")
    st.session_state["frex_h_s"] = str(row.get("frex h", "") or "")
    st.session_state["fresh_h_s"] = str(row.get("fresh h", "") or "")

    m = {}
    for c in CLIENT_COLS:
        m[c] = str(row.get(c, "") or "")
    st.session_state["clients_map"] = m

# -----------------------------
# UI
# -----------------------------
st.markdown("## 月次入力（Postgres / Supabase）")
df = load_df()
# -----------------------------
# 初回だけ：日付(d)の行を読み込んで session_state を先に埋める（ウィジェット生成前）
# -----------------------------

# --- 先に d を必ず初期化（_boot より前） ---
if "d" not in st.session_state or st.session_state["d"] is None:
    st.session_state["d"] = date.today()

if "_boot" not in st.session_state:
    st.session_state["_boot"] = True

    key0 = (st.session_state.get("d") or date.today()).isoformat()
    data0 = load_row_safe(key0)

    if not data0:
        st.session_state["total_h_s"] = ""
        st.session_state["frex_h_s"] = ""
        st.session_state["fresh_h_s"] = ""
        st.session_state["memo"] = ""
        st.session_state["clients_map"] = {c: 0 for c in CLIENT_COLS}
    else:
        st.session_state["total_h_s"] = data0.get("合計h", "") or ""
        st.session_state["frex_h_s"]  = data0.get("frex h", "") or ""
        st.session_state["fresh_h_s"] = data0.get("fresh h", "") or ""
        st.session_state["memo"]      = data0.get("メモ", "") or ""
        st.session_state["clients_map"] = {c: str(data0.get(c, "") or "") for c in CLIENT_COLS}

    st.session_state["client_sel"] = "U"
    st.session_state["client_amount"] = to_int(st.session_state["clients_map"].get("U", "")) or 0
    # 未保存検知：起動時に読み込んだ直後の状態を保存
    st.session_state["loaded_sig"] = _sig(_current_payload())

def on_date_change():
    key = st.session_state["d"].isoformat()
    data = load_row_safe(key)

    if data:
        load_inputs_from_row(data)
    else:
        clear_inputs()

    # その日付に切り替えた直後の状態を「読み込み済み」として記録
    st.session_state["loaded_sig"] = _sig(_current_payload())

    # 選択中取引先の入力欄も同期（UIがそういう作りなら）
    sel = st.session_state.get("client_sel", "U")
    st.session_state["client_amount"] = to_int(st.session_state["clients_map"].get(sel, "")) or 0

st.subheader("日付時間入力")
st.caption("同日なら上書き保存")

if "d" not in st.session_state:
    st.session_state["d"] = date.today()
d = st.date_input("日付", key="d", on_change=on_date_change)

c1, c2, c3 = st.columns(3)
with c1:
    st.text_input("合計h（例 6.5）", key="total_h_s")
with c2:
    st.text_input("frex h（例 2）", key="frex_h_s")
with c3:
    st.text_input("fresh h（例 1.5）", key="fresh_h_s")

st.text_area("メモ", key="memo", height=70)

ensure_clients_map()

st.markdown("### 取引先入力")
st.caption("ボタンで選択+金額直接入力")

# （任意）「その他」だけ折り返してデカくなるのを防ぐ
st.markdown(
    """
<style>
/* ボタン内の文字を折り返さない（高さが揃いやすい） */
div[data-baseweb="button"] button { white-space: nowrap; }
</style>
""",
    unsafe_allow_html=True,
)

# 2段に分割（Afrex以降を下段）
CLIENT_ROW1 = ["U", "出", "R", "W", "menu", "しょんぴ"]
CLIENT_ROW2 = ["Afrex","Afresh", "ハコベル", "pickg", "その他"]

# 初期化（ウィジェット生成前）
if "client_sel_row1" not in st.session_state:
    st.session_state["client_sel_row1"] = "U"
if "client_sel_row2" not in st.session_state:
    st.session_state["client_sel_row2"] = None

def on_row1_change():
    sel1 = st.session_state.get("client_sel_row1")
    if sel1:
        st.session_state["client_sel"] = sel1
        st.session_state["client_sel_row2"] = None
        on_client_change()

def on_row2_change():
    sel2 = st.session_state.get("client_sel_row2")
    if sel2:
        st.session_state["client_sel"] = sel2
        st.session_state["client_sel_row1"] = None
        on_client_change()

cA, cB = st.columns([2, 3])

with cA:
    st.pills(
        "取引先（上段）",
        CLIENT_ROW1,
        key="client_sel_row1",
        selection_mode="single",
        label_visibility="collapsed",
        width="stretch",
        on_change=on_row1_change,
    )

    st.pills(
        "取引先（下段）",
        CLIENT_ROW2,
        key="client_sel_row2",
        selection_mode="single",
        label_visibility="collapsed",
        width="stretch",
        on_change=on_row2_change,
    )

    # 念のため：client_sel が未定なら U に戻す
    if "client_sel" not in st.session_state or st.session_state["client_sel"] is None:
        st.session_state["client_sel"] = "U"
        on_client_change()

with cB:
    if "client_amount" not in st.session_state:
        on_client_change()

    # 表示用テキスト（初回だけ同期）
    if "client_amount_text" not in st.session_state:
        v = st.session_state.get("client_amount")
        st.session_state["client_amount_text"] = "" if not v else str(v)

    def on_amount_text_change():
        s = st.session_state.get("client_amount_text", "")
        num = int("".join(ch for ch in s if ch.isdigit()) or 0)
        st.session_state["client_amount"] = num
        on_amount_change()

    st.text_input(
        "金額（円）",
        key="client_amount_text",
        placeholder="例: 12000",
        on_change=on_amount_text_change,
    )

# ★保険：毎回 clients_map に同期（スマホで on_change が走らないケース対策）
ensure_clients_map()
sel = st.session_state.get("client_sel", CLIENT_COLS[0])
amt = to_int(st.session_state.get("client_amount")) or 0
st.session_state["clients_map"][sel] = amt

# 合計売上（右寄せ）
# 現在の入力プレビュー（合計売上は自動）
clients_map = st.session_state["clients_map"]
client_nums = {c: (to_int(v) or 0) for c, v in clients_map.items()}
total_sales = sum(client_nums.values())

st.markdown(f"#### 合計売上（自動）: {total_sales:,} 円")

nz = {k: v for k, v in client_nums.items() if int(v or 0) != 0}
if nz:
    st.dataframe(pd.DataFrame([nz]), width="stretch", hide_index=True)
else:
    st.caption("（入力なし）")

# -----------------------------
# 未保存警告（DBの読み込み状態と現在入力が違う）
# -----------------------------
cur_sig = _sig(_current_payload())
loaded_sig = st.session_state.get("loaded_sig", "")

dirty = (loaded_sig != "") and (cur_sig != loaded_sig)
st.session_state["dirty"] = dirty

if dirty:
    st.warning("未保存の変更があります。保存を押してね。")

# 保存
save = st.button("保存（同日なら上書き）", type="primary")
if save:
    key = st.session_state["d"].isoformat()
   
    total_h = to_float(st.session_state["total_h_s"]) or 0.0
    frex_h  = to_float(st.session_state["frex_h_s"]) or 0.0
    fresh_h = to_float(st.session_state["fresh_h_s"]) or 0.0

    other_h = max(0.0, float(total_h) - float(frex_h) - float(fresh_h))
    hourly = int(total_sales / total_h) if total_h > 0 else ""
    flag_5h = "5h+" if total_h >= 5.0 else ""
    warn = "⚠ 売上あり/時間0" if (total_sales > 0 and total_h <= 0) else ""

    row = {
        "日付": key,
        "合計売上": to_cell_int(total_sales),
        "合計h": to_cell_float(total_h),
        "frex h": to_cell_float(frex_h),
        "fresh h": to_cell_float(fresh_h),
        "他 h": to_cell_float(other_h),
        "合計時給": to_cell_int(hourly) if hourly != "" else "",
        "5h+": flag_5h,
        "警告": warn,
        "メモ": st.session_state.get("memo", "") or "",
    }

    for c in CLIENT_COLS:
        row[c] = to_cell_int(client_nums.get(c, 0))

    ok = upsert_row(row)
    if ok:
        st.session_state["loaded_sig"] = _sig(_current_payload())
        st.success(f"保存しました: {key}")
        st.session_state.pop("editor", None)
        st.rerun()
    # 失敗時は run_db が st.error を出すので、ここは何もしなくてOK

# -----------------------------
# データ閲覧＆削除
# -----------------------------
st.subheader("データ（DB）")

if df.empty:
    st.info("データがありません")
else:
    # --- 月で表示を切り替え（デフォルト：最新データの月） ---
    dcol = pd.to_datetime(df["日付"], errors="coerce")
    df2 = df.copy()
    df2["_d"] = dcol
    df2 = df2.dropna(subset=["_d"])

    months = sorted(df2["_d"].dt.strftime("%Y-%m").unique().tolist())
    latest_month = df2["_d"].max().strftime("%Y-%m") if not df2.empty else None

    sel_month = st.selectbox(
        "表示する月（YYYY-MM）",
        months,
        index=months.index(latest_month) if (latest_month in months) else 0,
        key="db_view_month",
    )

    # 選択月だけ表示（並びは月内で日付昇順）
    view = df2[df2["_d"].dt.strftime("%Y-%m") == sel_month].copy()
    view = view.sort_values("_d").drop(columns=["_d"]).reset_index(drop=True)
    if "選択" not in view.columns:
        view.insert(0, "選択", False)

    st.caption(f"表示中: {sel_month} / 件数: {len(view)} 行")

    edited = st.data_editor(
        view,
        width="stretch",
        hide_index=True,
        column_config={
            "選択": st.column_config.CheckboxColumn("選択", help="削除したい行にチェック")
        },
        disabled=[c for c in view.columns if c != "選択"],
        key=f"editor_{sel_month}"
    )

    picked = edited[edited["選択"] == True]

    st.caption("削除プレビュー（3行以上スクロールOK）")
    if picked.empty:
        st.caption("チェックされた行はありません")
    else:
        st.dataframe(picked.drop(columns=["選択"]), width="stretch", hide_index=True)
        confirm = st.checkbox("削除してOK（戻せません）", key=f"confirm_del_{sel_month}")

        if st.button("チェックした行を削除", key=f"btn_del_{sel_month}"):
            if not confirm:
                st.warning("チェックを入れてから押してね")
            else:
                del_keys = set(picked["日付"].astype(str).tolist())
                ok = delete_by_dates(del_keys)
                if ok:
                    st.success(f"削除しました: {', '.join(sorted(del_keys))}")
                    st.rerun()
                # 失敗時は run_db が st.error を出す

    # -----------------------------
    # CSVエクスポート（表示中の月 / 全データ）
    # -----------------------------
    export_view = view.drop(columns=["選択"], errors="ignore").copy()

    csv_month = export_view.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"📤 {sel_month} をCSVでダウンロード",
        data=csv_month,
        file_name=f"monthly_{sel_month}.csv",
        mime="text/csv",
        key=f"dl_month_{sel_month}",
    )
    
    today_str = date.today().isoformat()
    
    csv_all = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="📦 全データをCSVでダウンロード（バックアップ）",
        data=csv_all,
        file_name=f"monthly_all_{today_str}.csv",
        mime="text/csv",
        key="dl_all",
    )

# -----------------------------
# バックアップ/復元（CSV → DB）
# -----------------------------
# 2025年CSV読み込み ── app.py の「レポ生成」セクションの直前に追記
# ============================================================
# 貼り付け先:
#   st.subheader("レポ生成（月次レポ）") の直前
# ============================================================

# -----------------------------
# 2025年CSV専用の取引先（R は存在しない）
# -----------------------------
CLIENT_COLS_2025 = ["U", "出", "W", "menu", "しょんぴ", "Afrex", "Afresh", "ハコベル", "pickg", "その他"]

# -----------------------------
# 2025年CSV → 既存スキーマに変換
# -----------------------------
def parse_2025_csv(uploaded_files) -> pd.DataFrame:
    dfs = []
    for f in uploaded_files:
        try:
            raw = pd.read_csv(f, header=0, dtype=str)
        except Exception as e:
            st.warning(f"読み込みスキップ: {f.name} ({e})")
            continue

        cols = list(raw.columns)
        if cols[0] == "" or cols[0].startswith("Unnamed"):
            cols[0] = "日付"
        raw.columns = cols

        raw = raw[raw["日付"].notna()]
        raw = raw[raw["日付"].str.match(r"\d{4}/\d{2}/\d{2}", na=False)]

        def nc(s):
            if pd.isna(s): return None
            s = str(s).replace(",", "").replace('"', "").strip()
            try: return float(s)
            except: return None

        def nci(s):
            v = nc(s)
            return int(v) if v is not None else None

        def to_cell_i(v):
            return "" if (v is None or v == 0) else int(v)

        def to_cell_f(v):
            return "" if (v is None or v == 0.0) else float(v)

        rows = []
        for _, r in raw.iterrows():
            date_str = str(r["日付"]).strip()

            def g(col): return r.get(col, None)

            sou_calc = nci(g("計"))
            frex_h   = nc(g("frex"))
            fresh_h  = nc(g("fresh"))
            other_h  = nc(g("他"))

            if any(v is not None for v in [frex_h, fresh_h, other_h]):
                total_h = (frex_h or 0.0) + (fresh_h or 0.0) + (other_h or 0.0)
            else:
                total_h = None

            jikyu    = nci(g("時給"))
            clients  = {c: nci(g(c)) for c in CLIENT_COLS_2025}
            sevennow = nci(g("7now"))

            row = {
                "日付":    date_str,
                "合計売上": to_cell_i(sou_calc),
                "合計h":   to_cell_f(total_h),
                "frex h":  to_cell_f(frex_h),
                "fresh h": to_cell_f(fresh_h),
                "他 h":    to_cell_f(other_h),
                "合計時給": to_cell_i(jikyu),
                "5h+":    "",
                "警告":    "",
                **{c: to_cell_i(clients[c]) for c in CLIENT_COLS_2025},
                "R":      "",   # 2025年CSVには存在しない
                "メモ":    "",
            }
            rows.append(row)

        if rows:
            dfs.append(pd.DataFrame(rows))

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    combined["_sort"] = pd.to_datetime(combined["日付"], format="%Y/%m/%d", errors="coerce")
    combined = combined.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    # 列順を既存スキーマ（COLUMNS）に合わせる
    for c in COLUMNS:
        if c not in combined.columns:
            combined[c] = ""
    combined = combined[COLUMNS]

    return combined

def build_month_report_simple(df: pd.DataFrame, month_str: str) -> str:
    tmp = df.copy()
    tmp["日付"] = pd.to_datetime(tmp["日付"], errors="coerce", format="mixed")
    tmp = tmp.dropna(subset=["日付"])
    tmp["月"] = tmp["日付"].dt.to_period("M").astype(str)
    tmp = tmp[tmp["月"] == month_str].copy()

    if tmp.empty:
        return f"\nデータなし\n"

    tmp["合計売上_num"] = pd.to_numeric(tmp["合計売上"], errors="coerce").fillna(0)
    tmp["合計h_num"] = pd.to_numeric(tmp["合計h"], errors="coerce").fillna(0)

    sum_sales = int(tmp["合計売上_num"].sum())
    sum_h = float(tmp["合計h_num"].sum())
    hourly = int(sum_sales / sum_h) if sum_h > 0 else 0

    lines = []
    lines.append(f"【{month_str} 月次サマリ】")
    lines.append(f"売上合計: {sum_sales:,} 円")
    lines.append(f"時間合計: {sum_h:g} h")
    lines.append(f"時給: {hourly:,} 円/h")
    return "\n".join(lines)

def build_month_report_full(df: pd.DataFrame, month_str: str) -> str:
    tmp = df.copy()
    tmp["日付"] = pd.to_datetime(tmp["日付"], errors="coerce", format="mixed")
    tmp = tmp.dropna(subset=["日付"])
    tmp["月"] = tmp["日付"].dt.to_period("M").astype(str)
    tmp = tmp[tmp["月"] == month_str].copy()

    if tmp.empty:
        return "\nデータなし\n"

    # 数値化
    tmp["合計売上_num"] = pd.to_numeric(tmp["合計売上"], errors="coerce").fillna(0)
    tmp["合計h_num"] = pd.to_numeric(tmp["合計h"], errors="coerce").fillna(0)

    # 取引先列も数値化（存在するやつだけ）
    client_cols = [c for c in CLIENT_COLS if c in tmp.columns]
    for c in client_cols:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce").fillna(0)

    # 月合計
    MONTH_TARGET = 400000
    sum_sales = int(tmp["合計売上_num"].sum())
    sum_h = float(tmp["合計h_num"].sum())
    hourly = int(sum_sales / sum_h) if sum_h > 0 else 0
    # Flex / Fresh / 他（列名は DB のまま: Afrex, Afresh, frex h, fresh h）
    flex_sales = int(tmp["Afrex"].sum()) if "Afrex" in tmp.columns else 0
    fresh_sales = int(tmp["Afresh"].sum()) if "Afresh" in tmp.columns else 0

    flex_h = float(pd.to_numeric(tmp.get("frex h", 0), errors="coerce").fillna(0).sum()) if "frex h" in tmp.columns else 0.0
    fresh_h = float(pd.to_numeric(tmp.get("fresh h", 0), errors="coerce").fillna(0).sum()) if "fresh h" in tmp.columns else 0.0

    other_sales = max(0, sum_sales - flex_sales - fresh_sales)
    other_h = max(0.0, sum_h - flex_h - fresh_h)

    flex_hourly = int(flex_sales / flex_h) if flex_h > 0 else 0
    fresh_hourly = int(fresh_sales / fresh_h) if fresh_h > 0 else 0
    other_hourly = int(other_sales / other_h) if other_h > 0 else 0
   
    # -----------------------------
    # 季節判定（冬:12,1,2,3 / 夏:4-11）
    # -----------------------------
    m = int(month_str.split("-")[1])
    season = "冬" if m in (12, 1, 2, 3) else "夏"  # 4〜11は夏
   
    # -----------------------------
    # 目標（季節ごと）
    # -----------------------------
    if season == "冬":
        daily_target = 20000
        hourly_tiers = (3000, 3500, 4000)  # 合格 / 良い / 上振れ
    else:
        daily_target = 15000
        hourly_tiers = (2000, 2500, 3000)

    # -----------------------------
    # 平均日給（5h+）の現状
    # -----------------------------
    tmp_5h = tmp[tmp["合計h_num"] >= 5.0].copy()
    days_5h = int(len(tmp_5h))
    avg_5h_sales = int(tmp_5h["合計売上_num"].mean()) if days_5h > 0 else 0
    daily_ok = "✅" if avg_5h_sales >= daily_target else "❌"

    # -----------------------------
    # 時給の3段階評価
    # -----------------------------
    def grade_hourly(v: int, tiers: tuple[int, int, int]) -> str:
        ok, good, bubble = tiers
        if v >= bubble:
            return "上振れ（バブル）✅"
        elif v >= good:
            return "良い✅"
        elif v >= ok:
            return "合格✅"
        else:
            return "未達❌"

    hourly_grade = grade_hourly(hourly, hourly_tiers)

    # 対象月の年月（future判定のため先に作る）
    y, mo = map(int, month_str.split("-"))
    today = date.today()

    is_current_month = (today.year == y) and (today.month == mo)
    is_future_month  = (y, mo) > (today.year, today.month)

    lines = []
    lines.append(f"【{month_str} 月次レポート】")

    # 未来月は「目標だけ」表示して終了
    if is_future_month:
        lines.append("")
        lines.append("（未来月のため、実績系は当月開始後に表示）")
        lines.append("")
        lines.append("【目標】")
        lines.append("月目標: 400,000円")
        if season == "冬":
            lines.append("季節: 冬（12〜3月）")
            lines.append("・平均日給（5h+）目標: 20,000円")
            lines.append("・時給目標: 合格 3,000 / 良い 3,500 / 上振れ 4,000")
        else:
            lines.append("季節: 夏（4〜11月）")
            lines.append("・平均日給（5h+）目標: 15,000円")
            lines.append("・時給目標: 合格 2,000 / 良い 2,500 / 上振れ 3,000")

        return "\n".join(lines)

    # ここから下は「今月/過去月」のフルレポ
    lines.append("")
    lines.append("【月合計（売上/時間/時給）】")
    lines.append(f"全体: 売上 {sum_sales:,} 円 / 時間 {sum_h:g} h / 時給 {hourly:,} 円")
    lines.append(f"Flex : 売上 {flex_sales:,} 円 / 時間 {flex_h:g} h / 時給 {flex_hourly:,} 円")
    lines.append(f"Fresh: 売上 {fresh_sales:,} 円 / 時間 {fresh_h:g} h / 時給 {fresh_hourly:,} 円")
    lines.append(f"他   : 売上 {other_sales:,} 円 / 時間 {other_h:g} h / 時給 {other_hourly:,} 円")

    # -----------------------------
    # 1日あたり平均稼働時間（稼働日平均 / 暦日平均）
    # -----------------------------
    work_days = int((tmp["合計h_num"] > 0).sum())              # 稼働した日（時間>0）
    avg_workday_h = (sum_h / work_days) if work_days > 0 else 0.0

    last_day = calendar.monthrange(y, mo)[1]                   # その月の日数
    avg_calendar_h = (sum_h / last_day) if last_day > 0 else 0.0

    lines.append("")
    lines.append("【稼働時間（当月）】")
    lines.append(f"稼働日数: {work_days} 日 / 稼働日平均: {avg_workday_h:.2f} h/日")
    lines.append(f"暦日平均（休み込み）: {avg_calendar_h:.2f} h/日（{last_day}日で割り算）")

    if fresh_h > 0 and fresh_h < 5.0:
        lines.append("")
        lines.append("※注意：Fresh時間がまだ少ないため、Fresh時給は参考値です（時間入力が増えると安定します）")

    # -----------------------------
    # 月40万：目標/残り日数/プラン（残り7日以下で予定表を出す）
    # -----------------------------
    MONTH_TARGET = 400000  # 月40万（ここだけ触ればOK）

    today = date.today()

    remain_sales = max(0, MONTH_TARGET - sum_sales)
    ok_mark = "✅" if sum_sales >= MONTH_TARGET else "❌"

    if is_current_month:
        # 対象月の月末日（今月のときだけ必要）
        last_day = calendar.monthrange(y, mo)[1]
        month_end = date(y, mo, last_day)

        # 明日から月末まで（今日を除外）
        remain_days = max(0, (month_end - today).days)
        per_day_need = (remain_sales + remain_days - 1) // remain_days if remain_days > 0 else None

        # 5h+換算の基準日給（実績avgがあればそれ、なければ季節固定）
        plan_daily = avg_5h_sales if avg_5h_sales > 0 else daily_target
        plan_daily = max(1, int(plan_daily))
        need_5h_days = (remain_sales + plan_daily - 1) // plan_daily if remain_sales > 0 else 0
        need_5h_days = min(need_5h_days, remain_days)

        # ---- 表示（今月だけ）----
        lines.append("")
        lines.append("【月間目標進捗】")
        lines.append(f"月40万: {ok_mark}（{sum_sales:,}円 / あと{remain_sales:,}円）")

        if remain_days > 0:
            lines.append(f"月末まで残り: {remain_days}日（明日から） / 1日あたり必要: {per_day_need:,}円")
        else:
            lines.append("月末まで残り: 0日（明日から） / 1日あたり必要: —")

        lines.append(f"5h+換算で必要: {need_5h_days}日（平均日給 {plan_daily:,}円ベース）")

        # 月末プラン（最大7日表示）
        show_days = min(7, remain_days)
        if show_days > 0:
            lines.append("")
            lines.append("【月末プラン（予定表）】")
            lines.append(f"方針: 残り{remain_days}日のうち {need_5h_days}日を「5h+確保」(前倒し)")

            for i in range(1, show_days + 1):
                d = today + timedelta(days=i)
                mark = "5h+確保" if i <= need_5h_days else "軽め/休み"
                note = f"（目安 {plan_daily:,}円）" if i <= need_5h_days else ""
                wd = "月火水木金土日"[d.weekday()]
                lines.append(f"{d.isoformat()}({wd}) : {mark}{note}")

        # ↓ lines.append で表示
    else:
        # 今月じゃないなら表示しない（＝残り日数/予定表セクションを丸ごとスキップ）
        pass
 
    # 日次の時給（0hは除外）
    tmp["hourly"] = tmp.apply(
        lambda r: (r["合計売上_num"] / r["合計h_num"]) if r["合計h_num"] > 0 else None,
        axis=1
    )
    day = tmp.dropna(subset=["hourly"]).copy()
    day["hourly_int"] = day["hourly"].astype(int)

    top5 = day.sort_values("hourly", ascending=False).head(5)
    worst5 = day.sort_values("hourly", ascending=True).head(5)

    def fmt_day_row(r):
        dstr = r["日付"].strftime("%Y/%m/%d")
        sales = int(r["合計売上_num"])
        h = float(r["合計h_num"])
        hr = int(r["hourly"])
        hh = f"{h:g}"
        return f"{dstr}: {hr:,} 円（{sales:,}/{hh}h）"

    def fmt_breakdown(r):
        dstr = r["日付"].strftime("%Y/%m/%d")
        sales = int(r["合計売上_num"])
        h = float(r["合計h_num"])
        hr = int(r["hourly"]) if r["hourly"] is not None else 0

        parts = []
        for c in client_cols:
            v = int(r.get(c, 0))
            if v != 0:
                parts.append((c, v))
        parts.sort(key=lambda x: x[1], reverse=True)

        inner = " / ".join([f"{k} {v:,}" for k, v in parts]) if parts else "（内訳なし）"
        return (
            f"{dstr}  売上:{sales:,}  時間:{h:g}h  時給:{hr:,}円\n"
            f"  内訳: {inner}"
        )

    lines.append("")
    lines.append("【全体時給 TOP5（当月・日次）】")
    if top5.empty:
        lines.append("データなし（時間が0の行しかない）")
    else:
        for i, (_, r) in enumerate(top5.iterrows(), start=1):
            lines.append(f"{i}. {fmt_day_row(r)}")

    lines.append("")
    lines.append("【全体時給 WORST5（当月・日次）】")
    if worst5.empty:
        lines.append("データなし（時間が0の行しかない）")
    else:
        for i, (_, r) in enumerate(worst5.iterrows(), start=1):
            lines.append(f"{i}. {fmt_day_row(r)}")

    lines.append("")
    lines.append("【TOP5内訳（当月・日次）】")
    if top5.empty:
        lines.append("データなし")
    else:
        for i, (_, r) in enumerate(top5.sort_values("hourly", ascending=False).iterrows(), start=1):
            lines.append(f"[TOP{i}]")
            lines.append(fmt_breakdown(r))

    lines.append("")
    lines.append("【WORST5内訳（当月・日次）】")
    if worst5.empty:
        lines.append("データなし")
    else:
        for i, (_, r) in enumerate(worst5.sort_values("hourly", ascending=True).iterrows(), start=1):
            lines.append(f"[WORST{i}]")
            lines.append(fmt_breakdown(r))

    # -----------------------------
    # 季節目標チェック（末尾に追加）
    # -----------------------------
    lines.append("")
    lines.append(f"季節: {season}")
    lines.append(f"{season}：平均日給{daily_target:,}（5h+）: {daily_ok}（{avg_5h_sales:,}円 / 5h+日数 {days_5h}日）")

    ok, good, bubble = hourly_tiers
    lines.append(f"{season}：時給（合格{ok:,}/良い{good:,}/上振れ{bubble:,}）: {hourly_grade}（{hourly:,}円/h）")

    return "\n".join(lines)
def calc_month_pace(df: pd.DataFrame, month_str: str, month_target: int = 400000) -> dict:
    """
    月40万の“暦日按分ペース”判定用
    - ideal_cum: 今日時点の理想累計（暦日按分）
    - actual: 実績累計（月合計売上）
    - diff: 実績 - 理想
    - show: 当月だけ表示
    """
    tmp = df.copy()
    tmp["日付"] = pd.to_datetime(tmp["日付"], errors="coerce", format="mixed")
    tmp = tmp.dropna(subset=["日付"])
    tmp["月"] = tmp["日付"].dt.to_period("M").astype(str)
    tmp = tmp[tmp["月"] == month_str].copy()

    if tmp.empty:
        return {"show": False}

    tmp["合計売上_num"] = pd.to_numeric(tmp["合計売上"], errors="coerce").fillna(0)
    actual = int(tmp["合計売上_num"].sum())

    y, mo = map(int, month_str.split("-"))
    today = date.today()
    is_current_month = (today.year == y) and (today.month == mo)
    if not is_current_month:
        return {"show": False}

    last_day = calendar.monthrange(y, mo)[1]
    day_idx = max(1, min(today.day, last_day))

    ideal_cum = int(month_target * (day_idx / last_day))
    diff = actual - ideal_cum
    ok = actual >= ideal_cum

    return {
        "show": True,
        "ok": ok,
        "ideal_cum": ideal_cum,
        "actual": actual,
        "diff": diff,
        "day_idx": day_idx,
        "last_day": last_day,
        "month_target": month_target,
    }

def build_year_report_full(df: pd.DataFrame, year: int) -> str:
    tmp = df.copy()
    tmp["日付"] = pd.to_datetime(tmp["日付"], errors="coerce", format="mixed")
    tmp = tmp.dropna(subset=["日付"])
    tmp = tmp[tmp["日付"].dt.year == year].copy()

    if tmp.empty:
        return f"\n{year}年 データなし\n"

    # 数値化
    tmp["合計売上_num"] = pd.to_numeric(tmp["合計売上"], errors="coerce").fillna(0)
    tmp["合計h_num"] = pd.to_numeric(tmp["合計h"], errors="coerce").fillna(0)

    client_cols = [c for c in CLIENT_COLS if c in tmp.columns]
    for c in client_cols:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce").fillna(0)

    # 年合計
    sum_sales = int(tmp["合計売上_num"].sum())
    sum_h = float(tmp["合計h_num"].sum())
    hourly = int(sum_sales / sum_h) if sum_h > 0 else 0

    # Flex / Fresh / 他
    flex_sales = int(tmp["Afrex"].sum()) if "Afrex" in tmp.columns else 0
    fresh_sales = int(tmp["Afresh"].sum()) if "Afresh" in tmp.columns else 0

    flex_h = float(pd.to_numeric(tmp.get("frex h", 0), errors="coerce").fillna(0).sum()) if "frex h" in tmp.columns else 0.0
    fresh_h = float(pd.to_numeric(tmp.get("fresh h", 0), errors="coerce").fillna(0).sum()) if "fresh h" in tmp.columns else 0.0

    other_sales = max(0, sum_sales - flex_sales - fresh_sales)
    other_h = max(0.0, sum_h - flex_h - fresh_h)

    flex_hourly = int(flex_sales / flex_h) if flex_h > 0 else 0
    fresh_hourly = int(fresh_sales / fresh_h) if fresh_h > 0 else 0
    other_hourly = int(other_sales / other_h) if other_h > 0 else 0

    # 稼働時間（平均）
    work_days = int((tmp["合計h_num"] > 0).sum())
    avg_workday_h = (sum_h / work_days) if work_days > 0 else 0.0

    days_in_year = 366 if calendar.isleap(year) else 365
    avg_calendar_h = (sum_h / days_in_year) if days_in_year > 0 else 0.0

    # 日次の時給（0hは除外）
    tmp["hourly"] = tmp.apply(
        lambda r: (r["合計売上_num"] / r["合計h_num"]) if r["合計h_num"] > 0 else None,
        axis=1
    )
    day = tmp.dropna(subset=["hourly"]).copy()
    day["hourly_int"] = day["hourly"].astype(int)

    top5 = day.sort_values("hourly", ascending=False).head(5)
    worst5 = day.sort_values("hourly", ascending=True).head(5)

    def fmt_day_row(r):
        dstr = r["日付"].strftime("%Y/%m/%d")
        sales = int(r["合計売上_num"])
        h = float(r["合計h_num"])
        hr = int(r["hourly"])
        hh = f"{h:g}"
        return f"{dstr}: {hr:,} 円（{sales:,}/{hh}h）"

    def fmt_breakdown(r):
        dstr = r["日付"].strftime("%Y/%m/%d")
        sales = int(r["合計売上_num"])
        h = float(r["合計h_num"])
        hr = int(r["hourly"]) if r["hourly"] is not None else 0

        parts = []
        for c in client_cols:
            v = int(r.get(c, 0))
            if v != 0:
                parts.append((c, v))
        parts.sort(key=lambda x: x[1], reverse=True)

        inner = " / ".join([f"{k} {v:,}" for k, v in parts]) if parts else "（内訳なし）"
        return (
            f"{dstr}  売上:{sales:,}  時間:{h:g}h  時給:{hr:,}円\n"
            f"  内訳: {inner}"
        )

    lines = []
    lines.append(f"【{year} 年次レポート】")
    lines.append("")
    lines.append("【年合計（売上/時間/時給）】")
    lines.append(f"全体: 売上 {sum_sales:,} 円 / 時間 {sum_h:g} h / 時給 {hourly:,} 円")
    lines.append(f"Flex : 売上 {flex_sales:,} 円 / 時間 {flex_h:g} h / 時給 {flex_hourly:,} 円")
    lines.append(f"Fresh: 売上 {fresh_sales:,} 円 / 時間 {fresh_h:g} h / 時給 {fresh_hourly:,} 円")
    lines.append(f"他   : 売上 {other_sales:,} 円 / 時間 {other_h:g} h / 時給 {other_hourly:,} 円")

    # -----------------------------
    # 月別サマリ（売上/時間/時給 + 稼働日数/稼働日平均h）
    # -----------------------------
    mtmp = tmp.copy()
    mtmp["月"] = mtmp["日付"].dt.to_period("M").astype(str)

    # 稼働日フラグ（時間>0）
    mtmp["is_workday"] = (mtmp["合計h_num"] > 0).astype(int)

    g = mtmp.groupby("月", as_index=False).agg(
        sales=("合計売上_num", "sum"),
        hours=("合計h_num", "sum"),
        work_days=("is_workday", "sum"),
    )
    g["sales"] = g["sales"].astype(int)
    g["hours"] = g["hours"].astype(float)
    g["work_days"] = g["work_days"].astype(int)
    g["hourly"] = g.apply(lambda r: int(r["sales"] / r["hours"]) if r["hours"] > 0 else 0, axis=1)
    g["avg_workday_h"] = g.apply(lambda r: (r["hours"] / r["work_days"]) if r["work_days"] > 0 else 0.0, axis=1)

    lines.append("")
    lines.append("【月別サマリ（売上/時間/時給/稼働日数/稼働日平均h）】")
    for _, r in g.sort_values("月").iterrows():
        lines.append(
            f"{r['月']}: "
            f"売上 {int(r['sales']):,} 円 / "
            f"時間 {float(r['hours']):g} h / "
            f"時給 {int(r['hourly']):,} 円 / "
            f"稼働 {int(r['work_days'])} 日 / "
            f"稼働日平均 {float(r['avg_workday_h']):.2f} h"
        )

    lines.append("")
    lines.append("【稼働時間（年間）】")
    lines.append(f"稼働日数: {work_days} 日 / 稼働日平均: {avg_workday_h:.2f} h/日")
    lines.append(f"暦日平均（休み込み）: {avg_calendar_h:.2f} h/日（{days_in_year}日で割り算）")

    lines.append("")
    lines.append("【全体時給 TOP5（年間・日次）】")
    if top5.empty:
        lines.append("データなし（時間が0の行しかない）")
    else:
        for i, (_, r) in enumerate(top5.iterrows(), start=1):
            lines.append(f"{i}. {fmt_day_row(r)}")

    lines.append("")
    lines.append("【全体時給 WORST5（年間・日次）】")
    if worst5.empty:
        lines.append("データなし（時間が0の行しかない）")
    else:
        for i, (_, r) in enumerate(worst5.iterrows(), start=1):
            lines.append(f"{i}. {fmt_day_row(r)}")

    lines.append("")
    lines.append("【TOP5内訳（年間・日次）】")
    if top5.empty:
        lines.append("データなし")
    else:
        for i, (_, r) in enumerate(top5.sort_values("hourly", ascending=False).iterrows(), start=1):
            lines.append(f"[TOP{i}]")
            lines.append(fmt_breakdown(r))

    lines.append("")
    lines.append("【WORST5内訳（年間・日次）】")
    if worst5.empty:
        lines.append("データなし")
    else:
        for i, (_, r) in enumerate(worst5.sort_values("hourly", ascending=True).iterrows(), start=1):
            lines.append(f"[WORST{i}]")
            lines.append(fmt_breakdown(r))

    return "\n".join(lines)


st.subheader("レポ生成（月次レポ）")

if "df_2025" not in st.session_state:
    _csv_path = os.path.join(os.path.dirname(__file__), "2025_all.csv")
    if os.path.exists(_csv_path):
        import io as _io
        with open(_csv_path, "rb") as _f:
            _files = [_io.BytesIO(_f.read())]
            _files[0].name = "2025_all.csv"
        _auto = parse_2025_csv(_files)
        st.session_state["df_2025"] = _auto if not _auto.empty else pd.DataFrame()
    else:
        st.session_state["df_2025"] = pd.DataFrame()
df_2025_loaded = st.session_state.get("df_2025", pd.DataFrame())

if not df_2025_loaded.empty:
    df_merged = pd.concat([df, df_2025_loaded], ignore_index=True)
    df_merged["_sort"] = pd.to_datetime(df_merged["日付"], errors="coerce")
    df_merged = df_merged.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
else:
    df_merged = df

months = []
if not df_merged.empty:
    dtmp = df_merged.copy()
    dtmp["日付"] = pd.to_datetime(dtmp["日付"], errors="coerce", format="mixed")
    months = sorted(dtmp.dropna(subset=["日付"])["日付"].dt.to_period("M").astype(str).unique().tolist(), reverse=True)
sample = df_merged["日付"].head(10).tolist()

years = []
if not df_merged.empty:
    ytmp = df_merged.copy()
    ytmp["日付"] = pd.to_datetime(ytmp["日付"], errors="coerce", format="mixed")
    years = sorted(ytmp.dropna(subset=["日付"])["日付"].dt.year.unique().tolist(), reverse=True)

cL, cR = st.columns(2)

with cL:
    month_str = st.selectbox("対象月（YYYY-MM）", months) if months else None
    gen_m = st.button("月次レポ生成")

with cR:
    default_year = date.today().year
    sel_year = st.selectbox(
        "対象年（YYYY）",
        years,
        index=(years.index(default_year) if default_year in years else (len(years) - 1))
    ) if years else default_year
    gen_y = st.button("年次レポ生成")

if gen_m and month_str:
    rep = build_month_report_full(df_merged, month_str)
    st.session_state["report_text"] = rep
    st.session_state["pace_info"] = calc_month_pace(df, month_str, month_target=400000)
    st.session_state["report_kind"] = "month"

if gen_y:
    rep = build_year_report_full(df_merged, int(sel_year))
    st.session_state["report_text"] = rep
    st.session_state["pace_info"] = None  # 年次ではペース判定は出さない
    st.session_state["report_kind"] = "year"

report_text = st.session_state.get("report_text", "")
pace_info = st.session_state.get("pace_info", None)
report_kind = st.session_state.get("report_kind", "month")

if report_text:
    # 月間目標進捗（ペース判定：当月のみ）
    if report_kind == "month" and isinstance(pace_info, dict) and pace_info.get("show"):
        st.subheader("月間目標進捗")
        mark = "⭕️" if pace_info["ok"] else "❌"
        diff = pace_info["diff"]
        sign = "+" if diff >= 0 else ""
        msg = (
            f"ペース判定: {mark}  "
            f"（理想累計 {pace_info['ideal_cum']:,}円 / 実績 {pace_info['actual']:,}円 / 差分 {sign}{diff:,}円）"
        )
        if pace_info["ok"]:
            st.success(msg)  # 緑
        else:
            st.error(msg)    # 赤

    st.markdown("""
    <style>
    div[data-testid="stCodeBlock"] pre {
      font-size: 16px !important;
      line-height: 1.4 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.code(report_text, language="text")

st.subheader("バックアップ / 復元（CSV → DB）")
st.caption("⚠ インポートは上書き保存（同日なら更新）になります。実行前に全データCSVを手元に保存推奨。")

# uploader の表示ファイルも消すための世代
if "csv_up_ver" not in st.session_state:
    st.session_state["csv_up_ver"] = 0

up_file = st.file_uploader(
    "CSVを選択（monthly_all_... または monthly_YYYY-MM_...）",
    type=["csv"],
    key=f"csv_upload_{st.session_state['csv_up_ver']}",
)

# ここで import_df を保持してボタン押下時に参照できるようにする（rerun対策）
if "import_df" not in st.session_state:
    st.session_state["import_df"] = None
if "import_months" not in st.session_state:
    st.session_state["import_months"] = []
if "import_csv_rows" not in st.session_state:
    st.session_state["import_csv_rows"] = 0
if "import_minmax" not in st.session_state:
    st.session_state["import_minmax"] = ("", "")

if up_file is not None:
    try:
        import_df = pd.read_csv(up_file, dtype=str, encoding="utf-8-sig")
    except Exception:
        import_df = pd.read_csv(up_file, dtype=str, encoding="utf-8")

    import_df = import_df.fillna("")

    if "日付" not in import_df.columns:
        st.error("CSVに『日付』列がありません。正しいCSVを選んでください。")
        st.session_state["import_df"] = None
    else:
        # 列を揃える
        for c in COLUMNS:
            if c not in import_df.columns:
                import_df[c] = ""
        import_df = import_df[COLUMNS]

        # 情報表示（対象月/件数/日付範囲）
        dts = pd.to_datetime(import_df["日付"], errors="coerce")
        months = sorted(dts.dropna().dt.strftime("%Y-%m").unique().tolist())
        min_d = dts.min()
        max_d = dts.max()
        min_s = str(min_d.date()) if pd.notna(min_d) else "-"
        max_s = str(max_d.date()) if pd.notna(max_d) else "-"

        st.session_state["import_df"] = import_df
        st.session_state["import_months"] = months
        st.session_state["import_csv_rows"] = int(len(import_df))
        st.session_state["import_minmax"] = (min_s, max_s)

        st.info(f"CSV: 月={months if months else '-'} / 件数={len(import_df)} 行 / 日付範囲={min_s}〜{max_s}")

        st.write("プレビュー（先頭10行）")
        st.dataframe(import_df.head(10), width="stretch", hide_index=True)

        st.markdown("### インポート方式")
        strict_month = st.checkbox(
            "✅（月次CSV向け）この月のDBを先に全削除してから復元（CSVに無い日付は消える）",
            value=False,
            key="strict_month_restore",
        )
        st.caption("※ monthly_YYYY-MM.csv を入れるときだけ推奨。monthly_all では使わない。")

        confirm_imp = st.checkbox(
            "インポートしてOK（上書きが発生する場合があります）",
            key="confirm_import",
        )

        if st.button("CSVをDBへインポート（高速/execute_values）", type="primary", key="btn_import"):
            if not confirm_imp:
                st.warning("チェックを入れてから押してね")
            else:
                def _do_import() -> int:
                    init_db()

                    df_imp = st.session_state.get("import_df")
                    if df_imp is None or df_imp.empty:
                        raise RuntimeError("インポート対象のCSVがありません（もう一度ファイルを選び直してね）")

                    # strict_month の安全チェック
                    if strict_month:
                        months2 = st.session_state.get("import_months", [])
                        if len(months2) != 1:
                            raise RuntimeError(f"月だけ完全一致は『1ヶ月分のCSV』専用です。検出月={months2}")
                        month_prefix = months2[0]
                        ok_del = delete_by_month_prefix(month_prefix)
                        if not ok_del:
                            raise RuntimeError("月削除に失敗したためインポート中断")

                    cols = COLUMNS
                    colnames = ", ".join([f'"{c}"' for c in cols])
                    update_set = ", ".join([f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "日付"])

                    sql = f'''
                        INSERT INTO "{TABLE}" ({colnames})
                        VALUES %s
                        ON CONFLICT("日付") DO UPDATE SET
                        {update_set};
                    '''

                    values_list = [
                        tuple("" if r.get(c) is None else str(r.get(c, "")) for c in cols)
                        for _, r in df_imp.iterrows()
                    ]

                    pcon = _pg_connect()
                    try:
                        with pcon.cursor() as cur:
                            execute_values(cur, sql, values_list, page_size=500)
                        pcon.commit()
                        return len(values_list)
                    finally:
                        pcon.close()

                n = run_db("CSVインポート（高速/execute_values）", _do_import, default=0)
                if n > 0:
                    st.success(f"インポート完了: {n} 行")

                    # UIリセット（ファイル表示も消す）
                    for k in ["confirm_import", "strict_month_restore", "btn_import", "import_df", "import_months", "import_csv_rows", "import_minmax"]:
                        st.session_state.pop(k, None)
                    st.session_state["csv_up_ver"] += 1

                    st.rerun()
else:
    st.caption("CSVを選ぶと、プレビューとインポートボタンが表示されます。")

# -----------------------------
# レポ生成（簡易：月次集計）
# -----------------------------
# ============================================================
