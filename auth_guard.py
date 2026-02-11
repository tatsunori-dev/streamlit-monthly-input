# auth_guard.py
import os
import streamlit as st

from auth_core import should_skip_auth, load_credentials, validate


def auth_guard():
    """
    - ローカルのみ認証スキップ（DEV用）
    - Railway本番は必ず認証
    - Enterでログイン可能（st.form）
    """

    # 1) スキップ条件（ローカルのみ）
    if should_skip_auth(os.environ):
        return

    # 2) secrets 読み込み（環境によって例外になる可能性があるためガード）
    secrets_dict = None
    try:
        secrets_dict = dict(st.secrets)
    except Exception:
        secrets_dict = None

    # 3) 認証情報取得（env優先 / secrets補助）
    u, p = load_credentials(os.environ, secrets_dict)

    # 4) ローカルで env も secrets も無いならスキップ（開発用）
    #    ※不要ならこの if ブロックを削除すると「常に認証必須」になる
    if (not u and not p) and (not os.environ.get("RAILWAY_ENVIRONMENT")):
        return

    # 5) Railway / 本番で認証情報が無いのはエラー
    if not u or not p:
        st.error("認証設定がありません（APP_USERNAME/APP_PASSWORD または secrets.toml を設定）")
        st.stop()

    # 6) セッション初期化
    if "authed" not in st.session_state:
        st.session_state["authed"] = False

    # 7) ログイン済み表示
    if st.session_state["authed"]:
        with st.sidebar:
            st.success(f"ログイン中: {st.session_state.get('auth_user', '')}")
            if st.button("ログアウト", key="btn_logout"):
                st.session_state["authed"] = False
                st.session_state.pop("auth_user", None)
                st.rerun()
        return

    # 8) ログインフォーム（Enter送信OK）
    st.subheader("ログイン")
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
        # フォーム未送信時は以降のUIを止める（未認証で下に進ませない）
        st.stop()
