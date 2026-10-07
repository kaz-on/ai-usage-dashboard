# AI Usage Dashboard

OpenAI APIの組織別利用量・コストを可視化する、LAN内向けの非公式の軽量ダッシュボードです。Costs APIとCompletions Usage APIを使用し、単一のFastAPIコンテナに画面、定期同期、SQLiteをまとめています。

このアプリケーションは OpenAI Codex を利用して作成されています。

## 利用前の注意

**本アプリにはユーザー認証・アクセス制御・HTTPSがありません。** 接続できる人は、利用額・プロジェクト名・APIキー名の閲覧、CSV出力、手動同期を実行できます。信頼できる環境で使用し、インターネットへ直接公開しないでください。

初期設定では`127.0.0.1`で待ち受け、起動したホストからのみアクセスできます。LAN内で共有する場合は、後述の待ち受けIPとファイアウォールの設定を変更してください。

## 主な機能

- プロジェクト別の積み上げコストと総額（日・週・月を期間に応じて自動集約）
- プロジェクト別の積み上げリクエスト推移
- Cached/Uncached InputとOutput tokensの独立チャート
- 期間合計に対するプロジェクト別コスト割合
- Project名、Model、API Key名による絞り込み
- モデル別トークン量、プロジェクト別コスト
- CompletionsとCostsのCSV出力
- 1時間ごとの自動同期と手動同期
- SQLiteによる永続化
- APIキー不要のデモモード

Costs APIはモデル単位のコストを返さないため、モデル別コストの推計表示は行いません。仕様はOpenAIの公式ドキュメントに合わせています。

利用量の表示対象はCompletions Usageです。画像・音声など、その他のUsageエンドポイントの集計は実装していません。CostsはCosts APIが返すデータを表示します。

- [Costs API](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs)
- [Completions Usage API](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions)
- [List projects API](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/methods/list)
- [List project API keys](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/api_keys/methods/list)

## デモモードで起動

```bash
cp .env.example .env
docker compose up -d --build
```

起動したホストのブラウザで `http://127.0.0.1:8080` を開きます。`.env.example`は`MOCK_MODE=true`なので、実際のAPIキーがなくてもデモデータが自動生成されます。

状態確認：

```bash
docker compose ps
docker compose logs -f dashboard
```

停止：

```bash
docker compose down
```

`docker compose down -v`はSQLiteを保存したボリュームも削除するため、データを残したい場合は`-v`を付けないでください。

## 実際のOpenAIデータを使用

Organization Admin API Keyを用意し、`.env`を次のように変更します。
`OPENAI_ADMIN_KEY` は Usage API Scope と Organization Administration の Read 権限が必要です。

```dotenv
OPENAI_ADMIN_KEY=sk-admin-...
MOCK_MODE=false
```

反映します。

```bash
docker compose up -d --build
```

キーはブラウザへ送信されず、ダッシュボードコンテナからOpenAI APIを呼ぶためだけに使用されます。`.env`はGitの管理対象外です。

デモモードと実データモードは同じSQLiteを使用します。モードを切り替えても同期範囲外のデータや過去の同期履歴が残るため、実データで運用を始めるときはデモ用とは別の空のデータボリュームを用意してください。

初回は`INITIAL_HISTORY_DAYS`の日数を取得します。データ取得後は、`SYNC_INTERVAL_MINUTES`ごとに直近`SYNC_LOOKBACK_DAYS`日を再取得します。

## LAN内の特定IPで待ち受ける

サーバーのLAN側IPが`192.168.10.20`の場合、`.env`を変更します。

```dotenv
DASHBOARD_BIND_ADDRESS=192.168.10.20
DASHBOARD_PORT=8080
```

LAN内の別の端末からは`http://192.168.10.20:8080`を開きます。

待ち受けIPの指定は接続元の制限ではありません。OSのファイアウォールでも必要な接続元だけにTCP 8080を許可してください。共有するネットワークでは、認証とHTTPSを提供するリバースプロキシ等による保護も検討してください。

## 設定値

| 環境変数 | デフォルト | 説明 |
| --- | --- | --- |
| `OPENAI_ADMIN_KEY` | 空 | Usage API Scope と Organization Administration の Read 権限を持つ Organization Admin API Key |
| `DASHBOARD_SUBTITLE` | 空 | 画面タイトルの横に表示する集計対象名（例: Organization名） |
| `MOCK_MODE` | `false` | デモデータを生成する |
| `DASHBOARD_BIND_ADDRESS` | `127.0.0.1` | Dockerが公開するホスト側IP。LAN利用時はホストのLAN側IPを指定 |
| `DASHBOARD_PORT` | `8080` | ホスト側ポート |
| `TZ` | `Asia/Tokyo` | スケジューラーのタイムゾーン |
| `SYNC_INTERVAL_MINUTES` | `60` | 自動同期間隔 |
| `INITIAL_HISTORY_DAYS` | `90` | 初回取得日数 |
| `SYNC_LOOKBACK_DAYS` | `3` | 定期同期で再取得する日数 |

## データ保存とバックアップ

GitHubへのpushで保存されるのはGit管理対象のソースコードだけです。`.env`、SQLite、Composeのデータボリュームは含まれないため、別途バックアップしてください。

SQLiteには利用額・利用量に加え、プロジェクト名、APIキー名・ID、所有者名、マスクされたキー値などの組織情報が保存されます。DB、CSV、ログ、実データのスクリーンショットをpublicリポジトリへ追加しないでください。`.env`もアクセスを制限した場所に保存してください。

SQLiteはComposeの`dashboard-data`ボリュームに保存されます。簡易バックアップは次のように取得できます。

```bash
docker compose exec dashboard python -c \
  "import sqlite3; src=sqlite3.connect('/data/dashboard.db'); dst=sqlite3.connect('/data/backup.db'); src.backup(dst); dst.close(); src.close()"
docker compose cp dashboard:/data/backup.db ./dashboard-backup.db
```

復元時はコンテナを停止してからSQLiteファイルを差し替えてください。

## 集計上の制約

- 日付の絞り込みと日次集計はUTC基準です。`TZ`はスケジューラーのタイムゾーン設定です。
- Modelフィルターは利用量に適用され、Costsの集計には適用されません。
- 単一プロセスでの運用を想定しています。Uvicornの複数workerによる運用は想定していません。

## ローカル開発

Python 3.12以上とNode.jsを使用します。Node.jsはフロントエンドの型チェック専用で、
アプリケーションの実行やJavaScriptのビルドには使用しません。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
npm ci
MOCK_MODE=true DATABASE_PATH=./data/dashboard.db \
  .venv/bin/uvicorn app.main:app --reload
```

テストと静的チェック：

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
npm run typecheck
node --check app/static/dashboard.js
```

テストではモックHTTPレスポンスと決定的なデモデータを使用し、OpenAI APIへ通信しません。

GitHub Actionsでも、`main`へのpushとpull request時に同じテスト・静的チェックを実行します。CIにOpenAI APIキーは不要です。

`app/static/dashboard.js`は`// @ts-check`とJSDocで型チェックします。APIレスポンスと
Chart.js連携に使用する型は`app/static/dashboard-types.d.ts`に集約しています。
`npm run typecheck`は`noEmit`で実行されるため配信用ファイルを生成せず、Dockerfileにも
Node.jsの追加はありません。

## フロントエンドライブラリ

時系列チャートには[Chart.js 4.5.1](https://www.chartjs.org/)を使用しています。LAN内で外部通信なしに表示できるよう、配布ファイルを`app/static`に同梱しています。Chart.jsはMIT Licenseで提供され、ライセンス本文は`app/static/CHARTJS-LICENSE.md`に収録しています。

## ライセンス

本プロジェクトは[MIT License](LICENSE)で提供します。同梱のChart.jsには[Chart.jsのMIT License](app/static/CHARTJS-LICENSE.md)が適用されます。
