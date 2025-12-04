# semgrep-ci-to-sms
This script automates enabling **Semgrep Managed Scans (SMS)** across all projects in a deployment, except those that already have SMS enabled and those without any scans (not onboarded projects).

It performs the following steps:

---

## Step 1 — Identify Deployment Automatically  
If you do **not** provide a deployment slug, the script calls:

```
GET https://semgrep.dev/api/v1/deployments
```

It selects the **first deployment** returned and uses its `slug`.

You can also explicitly pass a deployment slug via `--deployment-slug`.

---

## Step 2 — List All Projects  
The script retrieves all projects via:

```
GET https://semgrep.dev/api/v1/deployments/{deployment_slug}/projects
```

Then, for each project, it fetches detailed configuration using:

```
GET https://semgrep.dev/api/v1/deployments/{deployment_slug}/projects/{project_name}
```

Projects that **already have SMS enabled** (both diff & full scans) are skipped:

```json
"managed_scan_config": {
  "diff_scan": { "enabled": true },
  "full_scan": { "enabled": true }
}
```

---

## Step 3 — Enable SMS for Remaining Projects

SMS is enabled via:

```
PATCH https://semgrep.dev/api/v1/deployments/{deployment_slug}/projects/{project_name}/managed-scan
```

With JSON payload:

```json
{
  "diff_scan": { "enabled": true },
  "full_scan": { "enabled": true }
}
```

---

# 🚀 Usage

## 1. Install dependencies
The script requires **Python 3** and the `requests` library.

```bash
pip install requests
```

---

## 2. Run in dry-run mode (recommended)

```bash
python enable_sms.py --dry-run --api-token "$SEMGREP_API_TOKEN"
```

This prints what would be changed without modifying anything.

---

## 3. Run for real

```bash
python enable_sms.py --api-token "$SEMGREP_API_TOKEN"
```

---

## 4. Optional: Specify deployment slug

```bash
python enable_sms.py --deployment-slug my-team --api-token "$SEMGREP_API_TOKEN"
```

---

# Authentication

The API token can be provided in two ways:

### Option A — CLI argument
```
--api-token <TOKEN>
```

### Option B — Environment variable
```bash
export SEMGREP_API_TOKEN="your_token_here"
```

---

# 📌 Script Features

- Auto-detects first deployment if none provided  
- Skips projects already using SMS  
- Enables SMS with correct PATCH + JSON body  
- Supports dry-run mode  
- URL-encodes project names safely  
- Prints clear status output  

# 📄 License

Internal / Customer Support Utility — no formal license.

