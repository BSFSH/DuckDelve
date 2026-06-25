# Deploying DuckDelve to PythonAnywhere

Pushes to `main` auto-deploy via `.github/workflows/deploy.yml`: GitHub Actions
SSHes into PythonAnywhere, runs `git pull` + `pip install -r requirements.txt`,
then reloads the web app through the PythonAnywhere API.

This is a paid-plan feature (SSH access). Do the one-time setup below, then every
`git push` goes live on its own.

## 1. One-time PythonAnywhere setup

Open a **Bash console** on PythonAnywhere and turn the existing code into a git
clone (replace `USERNAME` with your PythonAnywhere username):

```bash
# If ~/DuckDelve already exists (it holds flask.log etc.), convert it in place:
cd ~/DuckDelve
git init
git remote add origin https://github.com/BSFSH/DuckDelve.git
git fetch origin
git reset --hard origin/main          # makes the dir match the repo exactly

# (Alternative: back up and clone fresh)
# mv ~/DuckDelve ~/DuckDelve_backup && git clone https://github.com/BSFSH/DuckDelve.git ~/DuckDelve
```

Create the virtualenv and install deps:

```bash
mkvirtualenv --python=/usr/bin/python3.10 duckdelve
pip install -r ~/DuckDelve/requirements.txt
```

On the **Web tab**, point the app at the clone:
- Source code: `/home/USERNAME/DuckDelve`
- Working directory: `/home/USERNAME/DuckDelve`
- Virtualenv: `/home/USERNAME/.virtualenvs/duckdelve`
- Edit the WSGI file (`/var/www/USERNAME_pythonanywhere_com_wsgi.py`) so it ends with:

```python
import sys
path = "/home/USERNAME/DuckDelve"
if path not in sys.path:
    sys.path.insert(0, path)
import os
os.environ.setdefault("FLASK_SECRET_KEY", "put-a-long-random-value-here")
from app import app as application
```

Click **Reload** once to confirm the site works from the clone.

> If the GitHub repo is **private**, the PythonAnywhere clone needs auth: add a
> read-only **deploy key** (an SSH key whose public half is added to the repo's
> Deploy Keys) and use the `git@github.com:...` remote, or use a personal access
> token in the HTTPS URL.

## 2. GitHub repository secrets

In the GitHub repo: **Settings -> Secrets and variables -> Actions -> New repository secret**.
Add each of these:

| Secret            | Value (example)                                  |
|-------------------|--------------------------------------------------|
| `PA_USERNAME`     | your PythonAnywhere username                      |
| `PA_PASSWORD`     | your PythonAnywhere **login password** (for SSH) |
| `PA_PROJECT_DIR`  | `/home/USERNAME/DuckDelve`                        |
| `PA_VENV_DIR`     | `/home/USERNAME/.virtualenvs/duckdelve`           |
| `PA_DOMAIN`       | `USERNAME.pythonanywhere.com`                     |
| `PA_API_TOKEN`    | Account -> API token -> create/copy              |

Notes:
- The SSH host (`ssh.pythonanywhere.com`) is hard-coded in the workflow.
- The API token is separate from your password; generate it on the **Account**
  page under "API token."
- Hardening (optional): instead of `PA_PASSWORD`, add an SSH **public key** to
  your PythonAnywhere Account and switch the workflow to key auth (store the
  private key as a secret). Avoids putting your account password in CI.

## 3. Go live

1. Commit and push everything to `main`.
2. Watch **Actions** in GitHub: the "Deploy to PythonAnywhere" run should pull,
   install, and reload (final step prints `Reload returned HTTP 200`).
3. Visit `https://USERNAME.pythonanywhere.com` to confirm.

From then on, every push to `main` deploys automatically. You can also re-run it
manually from the Actions tab.
```
