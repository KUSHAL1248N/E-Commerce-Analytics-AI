# No-card cloud deployment guide

This guide deploys the existing Streamlit dashboard while preserving its original local setup:

- **Local development:** Ollama + Qwen 2.5 3B (selected automatically when `AI_PROVIDER` is absent or set to `ollama`).
- **Hosted app:** Cloudflare Workers AI + `@cf/qwen/qwen2.5-coder-32b-instruct` (selected with Streamlit Secrets).
- **Database:** TiDB Cloud Starter, using its MySQL-compatible endpoint and TLS.
- **Web app:** Streamlit Community Cloud.

The deployed application still generates MySQL-compatible SQL, validates it with SQLGlot, and runs it through a database account that has only `SELECT` permission on `ecommerce_analytics`.

## Free-tier limits and cost controls

- TiDB Cloud Starter offers free quotas for the first five MySQL-compatible Starter instances in an organization: 5 GiB row storage, 5 GiB columnar storage, and 50 million request units per month. When the quota is reached, new connections are denied until quota reset or a quota change. Do not add a payment method or increase the spending limit for this project.
- Cloudflare Workers AI on the Free Workers plan includes 10,000 Neurons per day. When the limit is reached, further inference requests fail until the daily reset. Do not upgrade to Workers Paid or activate paid AI Gateway credits.
- Streamlit Community Cloud free apps can hibernate after 12 hours without traffic. Viewers can wake the app again. Resource quotas apply.
- These are provider free-tier allowances, not an uptime guarantee. Providers can change free-tier conditions. Review each provider's current billing page before creating resources.

## 1. Create the TiDB Cloud Starter database

1. Create a TiDB Cloud account and choose a **MySQL-compatible TiDB Cloud Starter** instance. Do not select Essential, Dedicated, or a paid plan.
2. Choose an AWS region close to your audience if available.
3. Create the instance and set its root password. Save the password securely; it is only for initial database setup.
4. Open the instance and choose **Connect → Public**. Copy the host, port, username, and password. TiDB Cloud Starter public endpoints use port `4000` and require TLS.
5. Connect with MySQL Workbench (or another MySQL client). Use the provided host, port `4000`, username and password. In MySQL Workbench, configure SSL mode **Require**. Do not expose the root password in GitHub or Streamlit Secrets.
6. The Starter public endpoint allows all IPs by default. Because Streamlit Community Cloud does not provide a fixed app egress IP for this setup, do not add a guessed allowlist. Use TLS, a strong least-privilege application account, and only synthetic demo data. If the TiDB firewall has been changed from its default, the app's outbound connectivity must be tested.

## 2. Create the schema, sample data, and views

Connect as the TiDB root/administrator user and execute these files **one at a time, in this order**:

1. `database/01_create_database.sql`
2. `database/02_create_tables.sql`
3. `database/03_insert_data.sql`
4. `database/04_insert_orders.sql`
5. `database/05_insert_order_items.sql`
6. `database/06_insert_payments.sql`
7. `database/07_insert_reviews.sql`
8. `analysis/06_create_views.sql`

The database is named `ecommerce_analytics`. The input files use MySQL syntax; TiDB Cloud Starter is MySQL-compatible. Check that the nine tables and four views exist before proceeding.

## 3. Create the read-only application user

1. Generate a long alphanumeric password on your computer, for example with Python:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Open `database/08_create_ai_reader.sql.example` and replace `REPLACE_WITH_LONG_RANDOM_PASSWORD` with that password. Keep it alphanumeric so it does not need SQL quoting/escaping.
3. Execute the resulting SQL while connected as the TiDB administrator:

   ```sql
   CREATE USER IF NOT EXISTS 'ai_reader'@'%' IDENTIFIED BY 'YOUR_GENERATED_PASSWORD';
   GRANT SELECT ON ecommerce_analytics.* TO 'ai_reader'@'%';
   SHOW GRANTS FOR 'ai_reader'@'%';
   ```

4. Confirm the only database-level permission for `ai_reader` is `SELECT` on `ecommerce_analytics`.
5. Use `ai_reader` for both dashboard reads and AI-generated query execution. Do not put the administrator/root credentials in Streamlit Secrets.

## 4. Create the Cloudflare Workers AI token

1. Create/sign into a Cloudflare account and remain on the **Workers Free** plan.
2. Open **Workers & Pages → AI → Use REST API** (the dashboard labels may change).
3. Create a Workers AI API token with the minimum required Workers AI permission (Read / Workers AI model inference access). Do not create a Global API Key.
4. Copy the Cloudflare Account ID from the dashboard and save the token securely.
5. Do not enable Workers Paid, paid AI Gateway credits, or any pay-as-you-go upgrade.
6. The configured model is `@cf/qwen/qwen2.5-coder-32b-instruct`. Cloudflare's Free Workers AI quota is 10,000 Neurons/day. Requests fail after the free quota is exhausted; this project does not implement paid fallback.

## 5. Create a separate GitHub repository for the AI-enabled version

The ZIP was deliberately packaged without its old `.git` directory so it cannot accidentally overwrite the existing non-AI GitHub repository.

1. Extract this project into a new folder, for example `Ecommerce-Analytics-AI`.
2. On GitHub, create a new **empty** repository named `E-Commerce-Analytics-AI`. Do not initialize it with a README or license because those files are already in this project.
3. Open CMD in the extracted project folder and run:

   ```bash
   git init
   git branch -M main
   git add .
   git status
   ```

4. Before committing, verify `.env`, `.streamlit/secrets.toml`, passwords, and tokens are **not** staged. `.gitignore` already excludes them.
5. Commit and push:

   ```bash
   git commit -m "Prepare e-commerce analytics for cloud deployment"
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/E-Commerce-Analytics-AI.git
   git push -u origin main
   ```

## 6. Deploy the Streamlit app

1. Open [Streamlit Community Cloud](https://share.streamlit.io/) and sign in with GitHub.
2. Choose **Create app → I have an app**.
3. Select repository `YOUR_GITHUB_USERNAME/E-Commerce-Analytics-AI`, branch `main`, and main file path `python_app/dashboard.py`.
4. In Advanced settings, select Python **3.12** if the option is shown.
5. Deploy. The project includes a root-level `requirements.txt`; Streamlit installs the Python packages from it.
6. Wait until the app starts. If it fails, open the app's Manage app / Logs page and inspect the first Python dependency or configuration error before changing code.

## 7. Add Streamlit Secrets

In Streamlit Community Cloud, open the app's **Settings → Secrets**. Paste the contents below after replacing the placeholders. Use the *TiDB application's `ai_reader` password*, not the root/admin password.

```toml
AI_PROVIDER = "cloudflare"
CLOUDFLARE_ACCOUNT_ID = "YOUR_CLOUDFLARE_ACCOUNT_ID"
CLOUDFLARE_API_TOKEN = "YOUR_CLOUDFLARE_WORKERS_AI_TOKEN"
CLOUDFLARE_MODEL = "@cf/qwen/qwen2.5-coder-32b-instruct"
CLOUDFLARE_MAX_TOKENS = "512"

MYSQL_HOST = "YOUR_TIDB_PUBLIC_HOST"
MYSQL_PORT = "4000"
MYSQL_USER = "ai_reader"
MYSQL_PASSWORD = "YOUR_AI_READER_PASSWORD"
MYSQL_DATABASE = "ecommerce_analytics"
MYSQL_SSL = "true"

AI_MYSQL_USER = "ai_reader"
AI_MYSQL_PASSWORD = "YOUR_AI_READER_PASSWORD"
```

Save Secrets and reboot/redeploy the app. Secrets are read server-side by Python. The Cloudflare token is never placed in browser code or committed to GitHub.

## 8. Test the live application

Run these tests in the deployed Streamlit app:

1. Confirm the dashboard loads overview KPIs, filters, and charts from TiDB.
2. Ask: `How many total orders are there?`
3. Ask: `Which product generated the highest revenue from delivered orders?`
4. Ask an unsupported prediction question, such as `Predict next month's sales`. The app should return the configured `UNSUPPORTED:` message and must not execute SQL.
5. Confirm the generated SQL is displayed, passes SQLGlot validation, and results come from TiDB.

If the dashboard can't connect to TiDB, first verify the host, port, user, password, database name, public endpoint, and TLS setting. If AI generation fails, check the Cloudflare Account ID, token permission, model ID, and remaining daily Neurons. Do not paste credentials into a support message or screenshot.

## Local development is preserved

Your local `.env` should continue using:

```env
AI_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

Do not change your local Ollama model to Cloudflare. The hosted app selects Cloudflare through Streamlit Secrets; local development defaults to Ollama.
