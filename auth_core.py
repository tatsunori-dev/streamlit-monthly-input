# auth_core.py
import os

def is_railway_env(env: dict[str, str] | None = None) -> bool:
    env = env or os.environ
    return any([
        env.get("RAILWAY_ENVIRONMENT"),
        env.get("RAILWAY_PROJECT_ID"),
        env.get("RAILWAY_SERVICE_ID"),
    ])

def should_skip_auth(env: dict[str, str] | None = None) -> bool:
    env = env or os.environ
    # Railwayでは絶対スキップしない
    if is_railway_env(env):
        return False
    # ローカルでDEV_NO_AUTH=1だけスキップ
    return env.get("DEV_NO_AUTH") == "1"

def load_credentials(env: dict[str, str] | None = None, secrets: dict | None = None) -> tuple[str, str]:
    env = env or os.environ
    u = env.get("APP_USERNAME") or ""
    p = env.get("APP_PASSWORD") or ""

    # secrets は st.secrets を dict として渡す想定（テスト用）
    if (not u or not p) and secrets:
        cur = secrets
        for k in "auth.username".split("."):
            cur = cur.get(k, {})
        u = u or (cur if isinstance(cur, str) else "")

        cur = secrets
        for k in "auth.password".split("."):
            cur = cur.get(k, {})
        p = p or (cur if isinstance(cur, str) else "")

    return u, p

def validate(username: str, password: str, expected_u: str, expected_p: str) -> bool:
    return (username == expected_u) and (password == expected_p)
