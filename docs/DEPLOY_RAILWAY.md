# Railway Deploy 手順（streamlit-monthly-input）【決定版】

このドキュメントは **GitHub → Railway で Streamlit アプリを動かす手順の決定版**。  
現状は **保存なし運用（ポートフォリオ＆動作確認優先）**。

---

## 0. 前提
- GitHub repo: https://github.com/tatsunori-dev/streamlit-monthly-input
- リポジトリ直下に `app.py` と `requirements.txt` がある
- Railway に GitHub 連携済み
- （README に Deploy URL を貼れる状態）

---

## 1. Railway で New Project（GitHub repo から）
1. Railway Dashboard → `+ New`
2. `GitHub Repo` を選ぶ
3. `tatsunori-dev/streamlit-monthly-input` を選択
4. 自動で Build/Deploy が走るので待つ（Deployments が `Deployment successful` になる）

---

## 2. Start command（起動コマンド）
Railway → 対象プロジェクト → 対象 Service → `Settings` → `Deploy`

### 2-1. Custom Start Command（ここが最重要）
`Custom Start Command` に下を入れる：

    streamlit run app.py --server.port $PORT --server.address 0.0.0.0

### 2-2. Pre-deploy / Build Command（基本は空でOK）
- `Pre-deploy Command`：空でOK
- `Custom Build Command`：空でOK（Python/Streamlitは通常不要）

---

## 3. Networking（URL発行 / 固定URL）
Railway → 対象プロジェクト → 対象 Service → `Settings` → `Networking`

- `Domains` に出ているURLがアプリURL（基本は固定）
- 例：`https://streamlit-monthly-input-production.up.railway.app/`

### README へ貼る
README.md の `## Deploy URL（Railway）` に上のURLを貼る。

---

## 4. 動作確認（Mac / iPhone）
### 4-1. Mac
- アプリURLを開く
- **ダミー数字**で入力 → 表示更新 → 月次レポ生成 まで確認

### 4-2. iPhone（外での確認用）
- Safari でアプリURLを開く
- **ダミー数字**で入力 → 表示更新 → 月次レポ生成 まで確認

※現状は「保存なし運用」なので、Railway側で実数字は入れない（ダミーでOK）

---

## 5. 落とし穴（SQLiteが消える問題）と方針
このアプリは SQLite（`data.db`）を使っている。

### 5-1. 何が起きる？
クラウド環境では、デプロイ/再起動/再配置のタイミングで  
**SQLiteファイル（data.db）が消える/巻き戻る可能性**がある。

### 5-2. 今の最適解（保存しない運用）
- **保存はしない**（入力 → 表示確認のみ）
- 実数字は今まで通り Numbers 等で管理
- 「どこでも入力して残す」は、外部DBに寄せてからにする

### 5-3. 保存が必要になったら（将来の選択肢）
- ① 外部Postgres（例：Supabase等）に寄せる
- ② Railway 内で Postgres を追加（便利だがコスト増えやすい）

---

## 6. 節約運用（Remove / Redeploy）
### 6-1. 重要な認識
- **ブラウザを閉じただけでは止まらない**
- Service が動いている間は、基本的にクレジット消費が進む

### 6-2. 止める（Remove）
Railway → 対象プロジェクト → 対象 Service

- `Remove` を実行（停止相当）
  ※ RailwayのUIでは“Stop/Sleep”ではなく“Remove”が停止相当になる場合がある（プラン/画面構成で表示が違う）

### 6-3. 再開する（Redeploy）
Railway → 対象プロジェクト → `Deployments`

- 「最新の successful（成功）」を開く
- `Redeploy` を押して起動
- 起動後、アプリURLにアクセスして動作確認（ダミーでOK）

※ `Redeploy` が見当たらない場合：
  - 最新のデプロイを選んで「Deploy / Restart」系のボタンを押す

### 6-4. 外でのテスト運用（iPhone想定）
- 家でいったん `Remove`（停止）しておく
- 外でテストしたいタイミングで：
  1) Railway で `Redeploy`（起動）
  2) アプリURLで入力確認（ダミー）
  3) 終わったら `Remove`（停止）
