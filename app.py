import os
import sys
import streamlit as st

def _secret(path: str, default: str = "") -> str:
    """secrets.toml が無い環境でも落ちないように読む"""
    try:
        cur = st.secrets
        for k in path.split("."):
            cur = cur[k]
        return str(cur)
    except Exception:
        return default

def require_login():
    # ローカル開発はログイン不要（MacでだけOFFにしたいならこのフラグを使う）
    if os.getenv("DEV_NO_AUTH") == "1":
        return

    u = os.getenv("APP_USERNAME") or _secret("auth.username", "")
    p = os.getenv("APP_PASSWORD") or _secret("auth.password", "")

    # ローカルで環境変数もsecretsも無いなら、ログインをスキップ（開発用）
    if not u and not p:
        return

    if not u or not p:
        st.error("認証設定がありません（APP_USERNAME/APP_PASSWORD または secrets.toml を設定）")
        st.stop()

    if "authed" not in st.session_state:
        st.session_state["authed"] = False

    # ログイン済み：サイドバーにログアウトだけ出す
    if st.session_state["authed"]:
        with st.sidebar:
            st.success(f"ログイン中: {st.session_state.get('auth_user','')}")
            if st.button("ログアウト", key="btn_logout"):
                st.session_state["authed"] = False
                st.session_state.pop("auth_user", None)
                st.rerun()
        return

    st.title("ログイン")

    with st.form("login_form", clear_on_submit=False):
        user = st.text_input("ユーザー名", key="login_user")
        pw = st.text_input("パスワード", type="password", key="login_pw")
        submitted = st.form_submit_button("ログイン")

    if submitted:
        if user == u and pw == p:
            st.session_state["authed"] = True
            st.session_state["auth_user"] = user
            st.rerun()
        else:
            st.error("ユーザー名かパスワードが違う")

    st.stop()

# -----------------------------
# Streamlit（必ず最上部付近）
# -----------------------------
st.set_page_config(page_title="月次入力", layout="wide")

require_login()

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
        st.session_state["clients_map"] = {c: 0 for c in CLIENT_COLS}

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

import psycopg2

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

    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLUMNS]

    if not df.empty:
        df["_sort"] = pd.to_datetime(df["日付"], errors="coerce")
        df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    return df

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

def upsert_row(row: dict) -> int:
    init_db()

    cols = COLUMNS
    values = ["" if row.get(c) is None else str(row.get(c, "")) for c in cols]

    colnames = ", ".join([f'"{c}"' for c in cols])
    placeholders = ", ".join(["%s"] * len(cols))
    update_set = ", ".join([f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "日付"])

    sql = f'''
        INSERT INTO "{TABLE}" ({colnames})
        VALUES ({placeholders})
        ON CONFLICT("日付") DO UPDATE SET
        {update_set};
    '''

    pcon = _pg_connect()
    try:
        with pcon.cursor() as cur:
            cur.execute(sql, values)
        pcon.commit()
        return 1
    finally:
        pcon.close()

def delete_by_dates(date_keys: set[str]):
    if not date_keys:
        return

    init_db()
    keys = [str(k) for k in date_keys]

    placeholders = ", ".join(["%s"] * len(keys))
    sql = f'DELETE FROM "{TABLE}" WHERE "日付" IN ({placeholders});'

    pcon = _pg_connect()
    try:
        with pcon.cursor() as cur:
            cur.execute(sql, keys)
        pcon.commit()
    finally:
        pcon.close()

    # Postgres: IN (%s, %s, ...)
    placeholders = ", ".join(["%s"] * len(keys))
    sql = f'DELETE FROM "{TABLE}" WHERE "日付" IN ({placeholders});'

    pcon = _pg_connect()
    try:
        with pcon.cursor() as cur:
            cur.execute(sql, keys)
        pcon.commit()
    finally:
        pcon.close()

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

def on_change_date():
    key = st.session_state["date_pick"].isoformat()
    row = load_row(key)
    if row:
        load_inputs_from_row(row)
    else:
        clear_inputs()

# 初期化
if "clients_map" not in st.session_state:
    st.session_state["clients_map"] = {c: "" for c in CLIENT_COLS}
if "memo" not in st.session_state:
    st.session_state["memo"] = ""
if "total_h_s" not in st.session_state:
    st.session_state["total_h_s"] = ""
if "frex_h_s" not in st.session_state:
    st.session_state["frex_h_s"] = ""
if "fresh_h_s" not in st.session_state:
    st.session_state["fresh_h_s"] = ""

# -----------------------------
# UI
# -----------------------------
st.markdown("## 月次入力（Postgres / Supabase）")
df = load_df()
# -----------------------------
# 初回だけ：日付(d)の行を読み込んで session_state を先に埋める（ウィジェット生成前）
# -----------------------------
if "d" not in st.session_state:
    st.session_state["d"] = date.today()

if "_boot" not in st.session_state:
    st.session_state["_boot"] = True

    key0 = st.session_state["d"].isoformat()
    data0 = load_row(key0)

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
        st.session_state["clients_map"] = {c: (to_int(data0.get(c, "")) or 0) for c in CLIENT_COLS}

    st.session_state["client_sel"] = "U"
    st.session_state["client_amount"] = int(st.session_state["clients_map"].get("U", 0) or 0)
    # 未保存検知：起動時に読み込んだ直後の状態を保存
    st.session_state["loaded_sig"] = _sig(_current_payload())

def on_date_change():
    key = st.session_state["d"].isoformat()
    data = load_row(key)

    if not data:
        st.session_state["total_h_s"] = ""
        st.session_state["frex_h_s"] = ""
        st.session_state["fresh_h_s"] = ""
        st.session_state["memo"] = ""
        st.session_state["clients_map"] = {c: 0 for c in CLIENT_COLS}
    else:
        st.session_state["total_h_s"] = data.get("合計h", "") or ""
        st.session_state["frex_h_s"]  = data.get("frex h", "") or ""
        st.session_state["fresh_h_s"] = data.get("fresh h", "") or ""
        st.session_state["memo"]      = data.get("メモ", "") or ""
        st.session_state["clients_map"] = {
    c: (to_int(data.get(c, "")) or 0)
    for c in CLIENT_COLS
}

    st.session_state["client_sel"] = "U"
    st.session_state["client_amount"] = int(st.session_state["clients_map"].get("U", 0) or 0)
    # 未保存検知：この日付で読み込んだ直後の状態を保存
    st.session_state["loaded_sig"] = _sig(_current_payload())

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

    upsert_row(row)
    # 保存後：この状態を「保存済み」として記録（警告解除）
    st.session_state["loaded_sig"] = _sig(_current_payload())
    st.success(f"保存しました: {key}")

    st.session_state.pop("editor", None)
    st.rerun()

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

    csv_all = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📦 全データをCSVでダウンロード（バックアップ）",
        data=csv_all,
        file_name="monthly_all.csv",
        mime="text/csv",
        key="dl_all",
    )

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

        if st.button("チェックした行を削除", key="btn_del"):
            if not confirm:
                st.warning("チェックを入れてから押してね")
            else:
                del_keys = set(picked["日付"].astype(str).tolist())
                delete_by_dates(del_keys)
                st.success(f"削除しました: {', '.join(sorted(del_keys))}")
                st.rerun()

# -----------------------------
# レポ生成（簡易：月次集計）
# -----------------------------
st.subheader("レポ生成（月次レポ）")

def build_month_report_simple(df: pd.DataFrame, month_str: str) -> str:
    tmp = df.copy()
    tmp["日付"] = pd.to_datetime(tmp["日付"], errors="coerce")
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
    tmp["日付"] = pd.to_datetime(tmp["日付"], errors="coerce")
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
    lines.append("【全体時給 TOP5】")
    if top5.empty:
        lines.append("データなし（時間が0の行しかない）")
    else:
        for _, r in top5.iterrows():
            lines.append(fmt_day_row(r))

    lines.append("")
    lines.append("【全体時給 ワースト5】")
    if worst5.empty:
        lines.append("データなし（時間が0の行しかない）")
    else:
        for _, r in worst5.iterrows():
            lines.append(fmt_day_row(r))
   
    lines.append("")
    lines.append("【TOP5内訳】")
    if top5.empty:
        lines.append("データなし")
    else:
        for _, r in top5.sort_values("hourly", ascending=False).iterrows():
            lines.append(fmt_breakdown(r))

    lines.append("")
    lines.append("【ワースト5内訳】")
    if worst5.empty:
        lines.append("データなし")
    else:
        for _, r in worst5.sort_values("hourly", ascending=True).iterrows():
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

months = []
if not df.empty:
    dtmp = df.copy()
    dtmp["日付"] = pd.to_datetime(dtmp["日付"], errors="coerce")
    months = sorted(dtmp.dropna(subset=["日付"])["日付"].dt.to_period("M").astype(str).unique().tolist())

month_str = st.selectbox("対象月（YYYY-MM）", months) if months else None
gen = st.button("月次レポ生成")

if gen and month_str:
    rep = build_month_report_full(df, month_str)
    st.session_state["report_text"] = rep

report_text = st.session_state.get("report_text", "")
if report_text:
    st.markdown("""
    <style>
    /* レポ（st.code）の文字を少し大きく */
    div[data-testid="stCodeBlock"] pre {
      font-size: 16px !important;
      line-height: 1.4 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.code(report_text, language="text")
