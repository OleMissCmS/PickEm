# CBS Pick 'Em – Paste Analyzer (Streamlit)

Single-file Streamlit app that computes **Points Remaining** and **Total Points Possible** from copy-pasted CBS Weekly Standings **text** (no HTML, no login). It treats "`- (N)`" as a used confidence (no points available there).

## Files
- `app.py` — the Streamlit app
- `requirements.txt` — Python dependencies (`streamlit`, `pandas`)

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy via GitHub → Streamlit Community Cloud
1. Create a new GitHub repo and add `app.py` and `requirements.txt`.
2. Go to https://share.streamlit.io → “Deploy an app” → pick your repo/branch.
3. Set the app file to `app.py` and click **Deploy**.
4. Open the deployed URL. Paste the standings text and click **Analyze**.
