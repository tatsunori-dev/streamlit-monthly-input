# streamlit-monthly-input

軽貨物ドライバーの **日次売上・稼働時間の記録〜月次レポ作成** を自動化する、Streamlit製の業務支援アプリです。  
日々の入力データを **Supabase(Postgres)** に保存し、月単位で集計して **売上 / 稼働時間 / 時給 / 各種指標** を即時に可視化します。

## 解決する課題
- 日報がメモやスプレッドシートに散らばり、月末の集計に時間がかかる
- 入力ミスや転記漏れで数値がズレる（時給計算や月次合計の再計算が発生）
- バックアップ/復元の手段がなく、運用が不安

## 期待できる効果
- 日次入力だけで月次集計が自動化され、**月末作業を短縮**
- データはDBに一元管理、CSVの **バックアップ/復元** にも対応
- ログイン機能つきで、簡易的な社内運用にも使える

## 対象ユーザー
- 軽貨物ドライバー / フリーランス配送員 / 個人事業主など、日次売上と稼働時間を管理したい小規模事業者

## 主な入力項目
- 日付
- 売上（金額・取引先別内訳）
- 稼働時間（合計 / frex / fresh / その他）
- メモ（任意）

## 導入手順（最短3ステップ）
1. Railway上にデプロイ、またはローカルでアプリを起動
2. 管理者アカウントでログイン
3. 日次の売上・稼働時間を入力して保存

## できること
- ログイン（APP_USERNAME / APP_PASSWORD）
- 日次入力 → 保存（同日なら上書き）
- 月切り替え表示
- CSVエクスポート（表示中の月 / 全データ）
- CSVインポート（復元）
- チェックした行を削除
- 月次レポ生成（売上/時間/時給 + 各種指標）

## Screenshots

### 1) ログイン
![Login](images/01_login.png)

### 2) 日付・時間入力
![Input](images/02_input.png)

### 3) データ一覧（DB）＋CSV
![DB](images/03_db.png)

### 4) 月次レポ生成
![Report](images/04_report.png)

## ローカル起動
```bash
cd ~/Desktop/python_practice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ローカルはログイン無し（開発用）
DEV_NO_AUTH=1 streamlit run app.py
```

## Deploy（Railway）
- https://streamlit-monthly-input-production.up.railway.app/

## 環境変数（Railway Variables）
必須：
- SUPABASE_DB_URL
- APP_USERNAME
- APP_PASSWORD

任意（ローカル開発用）：
- DEV_NO_AUTH=1

## 構成（ざっくり）
Browser → Streamlit（Railway）→ Supabase Postgres

## バックアップ運用（おすすめ）
- 月1回「全データCSV」をダウンロードして保管
- 必要ならCSVインポートで復元

## 運用メモ（重要）
- 使わない時は Railway 側で Remove（停止）してクレジット消費を抑える
