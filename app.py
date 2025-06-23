import streamlit as st
import pandas as pd
from datetime import date, timedelta
import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# --------- SCOPES ---------
SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly"
]

# --------- SETUP ---------
CREDENTIALS_DIR = "credentials"
os.makedirs(CREDENTIALS_DIR, exist_ok=True)

if "creds_saved" not in st.session_state:
    st.session_state["creds_saved"] = False

# --------- AUTH ---------
def authenticate_and_store(account_label):
    flow = Flow.from_client_secrets_file(
        "client_secrets.json",
        scopes=SCOPES,
        redirect_uri="https://gjnm3mowwuh38xitnawc3g.streamlit.app/"
    )

    auth_url, _ = flow.authorization_url(prompt='consent')
    st.markdown(f"[🔐 Click here to authenticate your YouTube account]({auth_url})")

    code = st.text_input("📋 Paste the authorization code here:")

    if code and not st.session_state["creds_saved"]:
        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials
            file_path = f"{CREDENTIALS_DIR}/{account_label}.pkl"

            with open(file_path, "wb") as f:
                pickle.dump(credentials, f)

            st.session_state["creds_saved"] = True
            st.success(f"✅ Credentials saved: {file_path}")
            st.experimental_rerun()
        except Exception as e:
            st.error("❌ Authentication failed.")
            st.exception(e)

def load_credentials(account_label):
    with open(f"{CREDENTIALS_DIR}/{account_label}.pkl", "rb") as f:
        return pickle.load(f)

def list_saved_accounts():
    return [f.replace(".pkl", "") for f in os.listdir(CREDENTIALS_DIR) if f.endswith(".pkl")]

# --------- API CALLS ---------
def get_channel_name(youtube_data):
    res = youtube_data.channels().list(mine=True, part="snippet").execute()
    return res['items'][0]['snippet']['title']

def get_video_metrics(youtube_analytics, start_date, end_date):
    request = youtube_analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
        dimensions="video",
        sort="-views",
        maxResults=50
    )
    result = request.execute()
    cols = [col['name'] for col in result['columnHeaders']]
    return pd.DataFrame(result['rows'], columns=cols)

def get_video_titles(youtube_data, video_ids):
    all_titles = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        response = youtube_data.videos().list(part="snippet,statistics", id=",".join(chunk)).execute()
        for item in response["items"]:
            video_id = item["id"]
            title = item["snippet"]["title"]
            stats = item["statistics"]
            all_titles[video_id] = {
                "Title": title,
                "Likes": int(stats.get("likeCount", 0)),
                "Comments": int(stats.get("commentCount", 0)),
                "Shares": 0
            }
    return all_titles

# --------- UI ---------
st.set_page_config("📊 YouTube Video Dashboard", layout="wide")
st.title("📊 YouTube Video-Wise Analytics")

# Show contents of credentials
st.sidebar.markdown("📁 **Files in credentials folder:**")
st.sidebar.json(os.listdir(CREDENTIALS_DIR))

# Date range
start_date = (date.today() - timedelta(days=30)).isoformat()
end_date = date.today().isoformat()

# Account selector
st.sidebar.subheader("🎯 YouTube Accounts")
accounts = list_saved_accounts()

if accounts:
    st.sidebar.write("📁 Saved accounts:", accounts)
    selected_account = st.sidebar.selectbox("Select Account", accounts)
else:
    selected_account = None

if st.sidebar.button("➕ Add New Account"):
    authenticate_and_store(f"account_{len(accounts)+1}")
    st.stop()

# Show analytics
if selected_account:
    credentials = load_credentials(selected_account)
    yt_analytics = build("youtubeAnalytics", "v2", credentials=credentials)
    yt_data = build("youtube", "v3", credentials=credentials)

    try:
        video_df = get_video_metrics(yt_analytics, start_date, end_date)
        video_ids = video_df['video'].tolist()
        meta = get_video_titles(yt_data, video_ids)

        video_df['Title'] = video_df['video'].apply(lambda vid: meta.get(vid, {}).get("Title", ""))
        video_df['Likes'] = video_df['video'].apply(lambda vid: meta.get(vid, {}).get("Likes", 0))
        video_df['Comments'] = video_df['video'].apply(lambda vid: meta.get(vid, {}).get("Comments", 0))
        video_df['Shares'] = 0
        video_df['EngagementRate(%)'] = ((video_df['views'] + video_df['Likes'] + video_df['Comments']) / video_df['views']) * 100

        video_df = video_df.rename(columns={
            'views': 'Views',
            'estimatedMinutesWatched': 'Watch Time (min)',
            'averageViewDuration': 'Avg View Duration (sec)',
            'subscribersGained': 'Subscribers Gained',
            'subscribersLost': 'Subscribers Lost'
        })

        ordered_cols = ['Title', 'Views', 'Watch Time (min)', 'Avg View Duration (sec)',
                        'Subscribers Gained', 'Subscribers Lost', 'Likes', 'Comments', 'Shares', 'EngagementRate(%)']

        st.success(f"✅ Showing data for: **{selected_account}**")
        st.dataframe(video_df[ordered_cols])
        st.download_button("📥 Download CSV", video_df.to_csv(index=False), "video_analytics.csv")

    except Exception as e:
        st.error("❌ Failed to fetch analytics.")
        st.exception(e)
