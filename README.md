# Legal Eagle - AI Legal Research Assistant

## 🚀 Quick Deploy to Streamlit Cloud

### Step 1: GitHub Setup
1. Create a new GitHub repository
2. Upload all files EXCEPT `.streamlit/secrets.toml`
3. Make repository public (required for free Streamlit hosting)

### Step 2: Streamlit Cloud Deployment
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select your repository
5. Set main file path: `app.py`
6. Click "Advanced settings"

### Step 3: Add Secrets (CRITICAL)
In Advanced settings, add your secrets:
```toml
GROK_API_KEY = "3e7ZetCJdBOrUwhdr1SgQTY0Mex8OVPDu0miMIrsBpRWVDoc1jNhWZAZkOvNctEULuYxGWguLsk4vMUu"