import streamlit as st
import json
import openai
from datetime import datetime, timedelta
import os

# ================= CONFIG =================
# แนะนำให้เก็บ API KEY ใน Streamlit Secrets เวลาขึ้น Cloud
# แต่ถ้ารันในเครื่อง ใส่ตรงนี้ได้ (แต่อย่าเผลอหลุดให้ใครเห็น)
api_key = st.secrets["OPENAI_API_KEY"] if "OPENAI_API_KEY" in st.secrets else "sk-xxxxxxxxxxxxxxxxxxx"
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


def get_time(db):
    return datetime.strptime(db['world']['current_time'], TIME_FMT)


def add_time(db, days=0, hours=0, minutes=0):
    curr = get_time(db)
    new_time = curr + timedelta(days=days, hours=hours, minutes=minutes)
    db['world']['current_time'] = new_time.strftime(TIME_FMT)
    return new_time


# ================= UI SETUP =================
st.set_page_config(page_title="One Piece RPG", page_icon="🏴‍☠️")
st.title("🏴‍☠️ One Piece AI RPG")

# Initialize Session State (ความจำของเว็บ)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Load DB
db = load_db()
if not db:
    st.error("ไม่พบไฟล์ db.json กรุณาอัปโหลดไฟล์")
    st.stop()

# --- SIDEBAR HUD ---
p = db['player']
st.sidebar.header(f"🧑‍✈️ Captain {p['name']}")
st.sidebar.write(f"📍 **Loc:** {p['current_location']}")
st.sidebar.write(f"📅 **Time:** {db['world']['current_time']}")
st.sidebar.write(f"🎒 **Inv:** {p['inventory']}")
st.sidebar.write(f"❤️ **HP:** {p['stats']['hp']}")
st.sidebar.divider()
if db['log']:
    st.sidebar.info(f"📜 **Last Log:** {db['log'][-1]}")

# --- CHAT INTERFACE ---
# แสดงประวัติการคุยเก่า
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# รับ Input จากผู้เล่น
if prompt := st.chat_input("สั่งการกัปตัน... (เช่น ไปเกาะถัดไป, กินเนื้อ)"):
    # 1. แสดงข้อความผู้เล่น
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    # 2. เตรียม System Prompt (เหมือนเดิมเป๊ะ)
    curr_loc_name = p['current_location']
    loc_data = db['locations'].get(curr_loc_name, {})

    system_prompt = f"""
    Role: Game Master One Piece RPG (Strict Logic).
    [STRICT JSON RULES]
    1. Do NOT change keys.
    2. Array: Send COMPLETE list.
    3. Log: Only significant events (Max 120 chars).

    [MECHANICS]
    - Time: Check settings.action_costs.
    - Location: Player at '{curr_loc_name}'.
    - Logic: Validate Inventory/Stats first.

    [FORMAT]
    Narrative first (Thai), then JSON:
    ```json
    {{
        "narrative_summary": "...",
        "time_passed": {{ "days": 0, "hours": 0, "minutes": 0 }},
        "new_log_entry": "...",
        "updates": {{ ... }}
    }}
    ```

    [CONTEXT]
    Player: {json.dumps(p, ensure_ascii=False)}
    World: {json.dumps(db['world'], ensure_ascii=False)}
    Location: {json.dumps(loc_data, ensure_ascii=False)}
    Settings: {json.dumps(db['settings'], ensure_ascii=False)}
    """

    messages_payload = [{"role": "system", "content": system_prompt}]
    # ส่งประวัติย้อนหลัง 6 ข้อความ
    for msg in st.session_state.chat_history[-6:]:
        messages_payload.append(msg)

    # 3. เรียก AI
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages_payload,
                temperature=0.5,
            )
            content = response.choices[0].message.content

            # 4. Process JSON & Display Story
            import re

            json_match = re.search(r"```json(.*?)```", content, re.DOTALL)

            if json_match:
                story_text = content.replace(json_match.group(0), "").strip()
                message_placeholder.markdown(story_text)

                # Update Logic
                data = json.loads(json_match.group(1).strip())

                # Update Time
                t = data.get('time_passed', {})
                add_time(db, t.get('days', 0), t.get('hours', 0), t.get('minutes', 0))

                # Update Log
                if data.get('new_log_entry'):
                    db['log'].append(data['new_log_entry'][:120])

                # Update Data
                updates = data.get('updates', {})

                if 'player' in updates:
                    p_up = updates['player']
                    if 'inventory' in p_up: db['player']['inventory'] = p_up['inventory']
                    if 'current_location' in p_up: db['player']['current_location'] = p_up['current_location']
                    if 'stats' in p_up: db['player']['stats'].update(p_up['stats'])

                # (ใส่ Logic update อื่นๆ ตรงนี้เพิ่มได้เหมือน main.py เดิม)

                save_db(db)
                st.rerun()  # รีเฟรชหน้าเว็บเพื่ออัปเดต HUD Sidebar

            else:
                message_placeholder.markdown(content)

            st.session_state.chat_history.append(
                {"role": "assistant", "content": story_text if json_match else content})

        except Exception as e:
            st.error(f"Error: {e}")