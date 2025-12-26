import streamlit as st
import json
import openai
from datetime import datetime, timedelta
import os
import re

# ================= CONFIG =================
# ดึง Key จาก Secrets ที่เราตั้งค่าไว้
api_key = st.secrets["OPENAI_API_KEY"]
client = openai.OpenAI(api_key=api_key)

DB_FILE = 'db.json'
TIME_FMT = "%Y-%m-%d %H:%M:%S"

# ================= FUNCTIONS =================
def load_db():
    if not os.path.exists(DB_FILE): return None
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_time(db, days=0, hours=0, minutes=0):
    curr = datetime.strptime(db['world']['current_time'], TIME_FMT)
    new_time = curr + timedelta(days=days, hours=hours, minutes=minutes)
    db['world']['current_time'] = new_time.strftime(TIME_FMT)

# ================= UI SETUP =================
st.set_page_config(page_title="One Piece RPG", page_icon="🏴‍☠️", layout="wide")

# Initialize Chat History
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Load DB
db = load_db()
if not db:
    st.error("ไม่พบไฟล์ db.json กรุณาตรวจสอบ")
    st.stop()

# --- SIDEBAR HUD (แสดงสถานะ) ---
p = db['player']
with st.sidebar:
    st.title(f"🏴‍☠️ {p['name']}")
    st.write(f"📍 **Loc:** {p['current_location']}")
    st.write(f"📅 **Time:** {db['world']['current_time']}")
    
    # HP Bar (สมมติ Max HP 500)
    hp_percent = min(p['stats']['hp'] / 500, 1.0)
    st.progress(hp_percent, text=f"❤️ HP: {p['stats']['hp']}")
    
    st.divider()
    st.subheader("🎒 Inventory")
    for item in p['inventory']:
        st.caption(f"- {item}")
        
    st.divider()
    if db['log']:
        st.info(f"📜 **Last Log:** {db['log'][-1]}")

# --- MAIN CHAT INTERFACE ---
st.header("🌊 One Piece AI RPG: New World")

# 1. แสดงประวัติการคุยเก่า (Render History)
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # ถ้ามี JSON log ซ่อนอยู่ ให้แสดงด้วย (ถ้าเราเก็บไว้)
        if "debug_json" in message:
            with st.expander("🔍 ดูการคำนวณของ AI (JSON)"):
                st.code(message["debug_json"], language="json")

# 2. รับ Input
if prompt := st.chat_input("สั่งการกัปตัน... (เช่น ไปเกาะถัดไป, กินเนื้อ)"):
    
    # แสดงข้อความผู้เล่นทันที
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    # เตรียม Prompt
    curr_loc_name = p['current_location']
    loc_data = db['locations'].get(curr_loc_name, {})
    
    system_prompt = f"""
    Role: GM One Piece RPG (Strict Logic).
    [Rules]
    1. JSON Structure must not change keys.
    2. Arrays: Send COMPLETE list for updates.
    3. Log: Only significant events (Max 120 chars).
    
    [Format]
    Narrative (Thai) then JSON Block:
    ```json
    {{
        "narrative_summary": "...",
        "time_passed": {{ "days": 0, "hours": 0, "minutes": 0 }},
        "new_log_entry": "...",
        "updates": {{ ... }}
    }}
    ```
    
    [Context]
    Player: {json.dumps(p, ensure_ascii=False)}
    World: {json.dumps(db['world'], ensure_ascii=False)}
    Location: {json.dumps(loc_data, ensure_ascii=False)}
    Settings: {json.dumps(db['settings'], ensure_ascii=False)}
    """

    messages_payload = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.chat_history[-6:]:
        if msg["role"] != "system": # กันพลาด
             messages_payload.append({"role": msg["role"], "content": msg["content"]})

    # เรียก AI
    with st.chat_message("assistant"):
        with st.spinner("Oda Sensei กำลังแต่งเรื่อง..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_payload,
                    temperature=0.5,
                )
                content = response.choices[0].message.content
                
                # แยก JSON
                json_match = re.search(r"```json(.*?)```", content, re.DOTALL)
                
                if json_match:
                    # ส่วนเนื้อเรื่อง
                    story_text = content.replace(json_match.group(0), "").strip()
                    st.markdown(story_text)
                    
                    # ส่วน JSON (Debug)
                    json_str = json_match.group(1).strip()
                    with st.expander("🔍 ดูเบื้องหลัง (Game Engine Log)"):
                        st.code(json_str, language="json")
                    
                    # --- [FIXED] บันทึกข้อความลง History ก่อน Rerun ---
                    st.session_state.chat_history.append({
                        "role": "assistant", 
                        "content": story_text,
                        "debug_json": json_str # เก็บ JSON ไว้ดูย้อนหลังได้
                    })
                    
                    # Process Update DB
                    data = json.loads(json_str)
                    
                    # Time
                    t = data.get('time_passed', {})
                    add_time(db, t.get('days',0), t.get('hours',0), t.get('minutes',0))
                    
                    # Log
                    if data.get('new_log_entry'):
                        db['log'].append(data['new_log_entry'][:120])
                    
                    # Updates
                    updates = data.get('updates', {})
                    if 'player' in updates:
                        p_up = updates['player']
                        if 'inventory' in p_up: db['player']['inventory'] = p_up['inventory']
                        if 'current_location' in p_up: db['player']['current_location'] = p_up['current_location']
                        if 'stats' in p_up: db['player']['stats'].update(p_up['stats'])
                        if 'reputation' in p_up: db['player']['reputation'].update(p_up['reputation'])

                    if 'world' in updates and 'timeline' in updates['world']:
                        db['world']['timeline'] = updates['world']['timeline']

                    if 'characters' in updates:
                         for name, char_data in updates['characters'].items():
                            if name not in db['characters']: db['characters'][name] = char_data
                            else:
                                if 'status' in char_data: db['characters'][name]['status'] = char_data['status']
                                if 'stats' in char_data: db['characters'][name]['stats'].update(char_data['stats'])

                    save_db(db)
                    
                    # Rerun เพื่ออัปเดต Sidebar
                    st.rerun()
                    
                else:
                    st.markdown(content)
                    st.session_state.chat_history.append({"role": "assistant", "content": content})

            except Exception as e:
                st.error(f"Error: {e}")