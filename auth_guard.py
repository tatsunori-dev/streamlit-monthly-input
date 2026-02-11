# auth_guard.py
import os
import streamlit as st


def auth_guard() -> bool:
    """
    認証ガード（テスト仕様準拠）
    - DEV_NO_AUTH=1 のときは認証バイパス（authed=True で通す）
    - session_state["authed"] が True なら通す
    - 未認証ならログインUI表示
      - Login ボタン押下 & 正しいID/PW -> authed=True で通す
      - それ以外 -> st.stop()
    """
    # タイトルは常に呼ばれる（test_auth_guard_calls_title 対応）
    st.title("月次入力（Postgres / Supabase）")

    # 1) ローカル開発用：認証スキップ
    if os.getenv("DEV_NO_AUTH") == "1":
        st.session_state["authed"] = True
        return True

    # 2) 既に認証済み
    if st.session_state.get("authed") is True:
        return True

    # 3) 未認証：ログインUI
    app_user = os.getenv("APP_USERNAME", "")
    app_pass = os.getenv("APP_PASSWORD", "")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", key="login_password", type="password")

    if st.button("Login"):
        if username == app_user and password == app_pass and app_user != "" and app_pass != "":
            st.session_state["authed"] = True
            return True
        else:
            st.error("ログインに失敗しました")
            st.stop()

    # Login ボタンが押されてない場合も、未認証なので止める（テストがここを期待）
    st.stop()
