# streamlit-monthly-input

軽貨物ドライバー向け：売上と稼働時間を入力して、月次レポを自動表示する Streamlit アプリ。  
※現在は「保存なし運用」（ポートフォリオ＆動作確認優先）

## できること
- 画面から入力 → その場で集計結果（売上/時間/時給など）を表示
- 月次レポ生成（エラーなく動作確認OK）

## ローカル起動（3行）
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt && streamlit run app.py
```

## Deploy URL（Railway）
- https://streamlit-monthly-input-production.up.railway.app/

## 運用メモ（重要）
- SQLite（data.db）を使っているため、クラウド環境では永続化が崩れる可能性あり
- 節約運用：使わない時は Railway 側で Remove（停止）してクレジット消費を抑える
