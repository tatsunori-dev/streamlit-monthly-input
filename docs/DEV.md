# DEV（ローカル起動手順）

## 前提
- Python3 が入っていること
- このリポジトリを clone 済み

## 起動（3行）
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt && streamlit run app.py

## 停止
- ターミナルで `Ctrl + C`

## 反映されない時
- `Ctrl + C` で止めて、もう一度 `streamlit run app.py`

---

## Git差分チェック（置換漏れがないか確認）
    cd ~/Desktop/python_practice
    git diff

## 決定版をGitHubへ反映（add→commit→push）
    cd ~/Desktop/python_practice
    git add docs/DEPLOY_RAILWAY.md docs/DEV.md README.md
    git commit -m "update docs"
    git push

---

## メモ（任意）
- `.venv/` は Git 管理しない（`.gitignore` に入っていればOK）
- `pip freeze > requirements.txt` は依存関係を追加した時だけやればOK

## 障害/復旧チェック（最小）
- まず「📦 全データCSV」をDL（バックアップ確保）
- Railway Variables: SUPABASE_DB_URL / APP_USERNAME / APP_PASSWORD を確認
- Supabase: テーブル records が存在するか確認（なければアプリ起動で自動作成）
- Railway Logs で [DB-ERROR] を検索して、失敗した処理ラベルを確認
