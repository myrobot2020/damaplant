# ui/plant.py - Simple Streamlit UI for pipeline control

import streamlit as st
import json
import time
from datetime import datetime
from google.cloud import pubsub_v1
from supabase import create_client
import os

# ============================================
# CONFIGURATION
# ============================================

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
TOPIC_INGEST = f"projects/{PROJECT_ID}/topics/sutta-ingested"

pubsub_publisher = pubsub_v1.PublisherClient()
supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY")
)

# ============================================
# UI
# ============================================

st.set_page_config(page_title="Plant Control", layout="wide")

st.title("🌱 DAMA Pipeline Control")

# URL Input Section
st.markdown("### 🎥 Ingest New Sutta")
col1, col2 = st.columns([3, 1])

with col1:
    url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")

with col2:
    slug = st.text_input("Slug (optional)", placeholder="auto-generated")

if st.button("🚀 Start Pipeline", type="primary"):
    if url:
        # Publish to Pub/Sub
        message = json.dumps({
            "url": url,
            "slug": slug if slug else None,
            "requested_at": datetime.now().isoformat()
        })
        pubsub_publisher.publish(TOPIC_INGEST, message.encode())
        st.success(f"✅ Published to {TOPIC_INGEST}")
        st.info(f"📤 Message: {message[:200]}...")
    else:
        st.error("Please enter a URL")

# Event Monitor Section
st.markdown("---")
st.markdown("### 📡 Live Pipeline Events")

# Auto-refresh every 2 seconds
placeholder = st.empty()

def fetch_events():
    try:
        events = supabase.table("pipeline_events") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(20) \
            .execute()
        return events.data
    except:
        return []

# Display events
event_container = st.container()

with event_container:
    events = fetch_events()
    if events:
        for e in events:
            col1, col2, col3, col4 = st.columns([2, 1, 2, 3])
            with col1:
                st.caption(e["created_at"][11:19] if e["created_at"] else "")
            with col2:
                st.code(e["stage"], language="")
            with col3:
                st.text(e["verb"])
            with col4:
                st.caption(str(e["payload"])[:50])
    else:
        st.info("Waiting for events...")

# Auto-refresh button
if st.button("🔄 Refresh"):
    st.rerun()

st.markdown("---")
st.caption(f"📡 Listening to topic: {TOPIC_INGEST}")
