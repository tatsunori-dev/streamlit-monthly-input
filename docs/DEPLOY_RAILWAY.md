# Railway Deploy 手順（streamlit-monthly-input）

## 0. 前提
- GitHub repo: https://github.com/tatsunori-dev/streamlit-monthly-input
- `requirements.txt` がある
- `app.py` がある
- Railway に GitHub 連携済み

---

## 1. Railway で New Project（GitHub repo から）
1. Railway Dashboard → `+ New`
2. `GitHub Repo` を選ぶ
3. `tatsunori-dev/streamlit-monthly-input` を選択
4. 自動で Build/Deploy が走るのを待つ（Deployments が `Deployment successful` になる）

---

## 2. Start command（起動コマンド）
Service → `Settings` → `Deploy` → `Custom Start Command` にこれを入れる：

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0

## 確認コマンド（すぐ見つける）
ターミナルでこれ：

```bash
cd ~/Desktop/python_practice
grep -n '```' docs/DEPLOY_RAILWAY.md
