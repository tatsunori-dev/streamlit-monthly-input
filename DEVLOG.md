
## 2026-02-13
### 今日の作業おさらい
- プロジェクト全体の現状共有を完了（ファイル構成 / DB / 認証 / 月次レポの実装箇所を特定）
- DB方針を確定：全カラムTEXT・空文字ベース・基本手入力で運用（数値型移行は急がない）
- auth確認：本番はログイン必須、認証情報は環境変数（Railway Variables）で管理
- ローカル接続は .streamlit/secrets.toml の SUPABASE_DB_URL を使用（ENVではない）
- 月次レポの仕様追加を確定：
  - 新タイトル「月間目標進捗」を追加
  - 月40万の“日割りペース判定”を追加（理想累計 vs 実績累計で ⭕️/❌、色は st.success/st.error）
  - このペース判定は当月のみ表示（翌月になったら非表示でOK）
- 年次レポ追加の仕様を確定：
  - 月次の内容を年間版に（年合計 / 稼働時間（年間） / 全体時給TOP5 & ワースト5 / 各内訳）
  - Flex/Fresh/他 の詳細も年間に含める
  - 年次は目標系（季節/5h+/時給3段階評価）は当面入れない（とりあえずNO）
- Railway：Redeploy完了、Usage記録
  - Credits Available $5.00 / Current Usage $0.04 / Estimated Month’s Cost $0.00
  - Project streamlit-monthly-input Current Cost $0.0373（主にMemory）

### 明日の作業共有
- 月次レポに「月間目標進捗」ブロックを追加（タイトル付与＋ペース判定 ⭕️/❌ を st.success/st.error で表示）
- 年次レポの生成関数を追加（年フィルタで月次相当の集計＋TOP/WORST＋内訳、Flex/Fresh/他も年間で出す）
- UIに年次レポのボタン/切替を追加（まずは月次と同じ表示形式でOK）

