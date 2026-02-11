# auth_guard.py
import os
import streamlit as st
from auth_core import should_skip_auth, load_credentials, validate

def auth_guard():
    # スキップ条件（ローカルのみ）
    if should_skip_auth(os.environ):
        return

secrets_dict = None
try:
    # Streamlit には st.secrets 自体は常にあるが、環境によっては参照時に例外になることがある
    secrets_dict = dict(st.secrets)
except Exception:
    secrets_dict = None

u, p = load_credentials(os.environ, secrets_dict)

    # ローカルで env も secrets も無いならスキップ（開発用）
    # ※これ要らないなら消してOK（より厳格になる）
    if (not u and not p) and (not os.environ.get("RAILWAY_ENVIRONMENT")):
        return

    if not u or not p:
        st.error("認証設定がありません（APP_USERNAME/APP_PASSWORD または secrets.toml を設定）")
        st.stop()

    if "authed" not in st.session_state:
        st.session_state["authed"] = False

    # ログイン済み
    if st.session_state["authed"]:
        with st.sidebar:
            st.success(f"ログイン中: {st.session_state.get('auth_user','')}")
            if st.button("ログアウト", key="btn_logout"):
                st.session_state["authed"] = False
                st.session_state.pop("auth_user", None)
                st.rerun()
        return

    st.subheader("ログイン")

    # ✅ Enterで送信できるのは st.form_submit_button のおかげ（ここが大事）
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("ユーザー名", key="login_username")
        password = st.text_input("パスワード", type="password", key="login_password")
        submitted = st.form_submit_button("ログイン")

    if submitted:
        if validate(username, password, u, p):
            st.session_state["authed"] = True
            st.session_state["auth_user"] = username
            st.rerun()
        else:
            st.error("ユーザー名/パスワードが違います")
            st.stop()
    else:
        st.stop()
