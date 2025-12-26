import streamlit as st
import json
import openai
from datetime import datetime, timedelta
import os
import re

# ================= CONFIG =================
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    st.error("ไม่พบ API Key ใน Secrets")
    st.stop()

client = openai.OpenAI(api_key=api_key)

DB_FILE = 'db.json'
DIALOG_FILE = 'dialog.json' # ไฟล์ใหม่สำหรับเก็บแชท
TIME_FMT = "%Y-%m-%d %H:%M:%S"

# ================= FUNCTIONS =================
def load_json(filepath, default_value):
    if not os.path.exists(filepath): return default_value
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return default_value

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_time(db, days=0, hours=0, minutes=0):
    curr = datetime.strptime(db['world']['current_time'], TIME_FMT)
    new_time = curr + timedelta(days=days, hours=hours, minutes=minutes)
    db['world']['current_time'] = new_time.strftime(TIME_FMT)

# ================= UI SETUP =================
st.set_page_config(page_title="One Piece RPG", page_icon="🏴‍☠️", layout="wide")

# 1. โหลดประวัติแชทจากไฟล์ (ถ้ามี)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = load_json(DIALOG_FILE, [])

# 2. โหลด Database เกม
db = load_json(DB_FILE, None)
if not db:
    st.error(f"ไม่พบไฟล์ {DB_FILE}")
    st.stop()

# --- SIDEBAR HUD ---
p = db['player']
with st.sidebar:
    st.title(f"🏴‍☠️ {p['name']}")
    st.write(f"📍 **Loc:** {p['current_location']}")
    st.write(f"📅 **Time:** {db['world']['current_time']}")
    
    # HP Bar
    max_hp = 500
    hp_val = p['stats']['hp']
    st.progress(min(hp_val/max_hp, 1.0), text=f"❤️ HP: {hp_val}")
    
    st.divider()
    st.subheader("🎒 Inventory")
    for item in p['inventory']:
        st.caption(f"- {item}")
        
    st.divider()
    # ปุ่มกดเพื่อเคลียร์แบบ Manual
    if st.button("🗑️ เคลียร์เนื้อเรื่อง (Reset Story)", type="primary"):
        st.session_state.chat_history = []
        save_json(DIALOG_FILE, []) # ลบไฟล์
        st.rerun()

# --- MAIN CHAT ---
st.header("🌊 One Piece AI RPG: Persistent World")

# Render History
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "debug_json" in message:
            with st.expander("🔍 System Log"):
                st.code(message["debug_json"], language="json")

# Handle Input
if prompt := st.chat_input("สั่งการกัปตัน..."):
    
    # === CHECK CLEAR COMMAND ===
    if prompt.strip() in ["เคลียร์เนื้อเรื่อง", "ล้างเนื้อเรื่อง", "reset story", "clear"]:
        st.session_state.chat_history = []
        save_json(DIALOG_FILE, [])
        st.success("ล้างประวัติเรียบร้อยแล้ว!")
        st.rerun()
    
    # 1. User Message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # บันทึก User ลง RAM และ ลงไฟล์ทันที
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    save_json(DIALOG_FILE, st.session_state.chat_history)

    # Prepare Data
    curr_loc_name = p['current_location']
    loc_data = db['locations'].get(curr_loc_name, {})
    
    system_prompt = f"""
    Role: GM One Piece RPG.
    Rules:
    1. Strict JSON Structure.
    2. Check Inventory/Stats before action.
    3. Narrative (Thai) first, then JSON Block.
    
    [Context]
    Player: {json.dumps(p, ensure_ascii=False)}
    World: {json.dumps(db['world'], ensure_ascii=False)}
    Location: {json.dumps(loc_data, ensure_ascii=False)}
    Settings: {json.dumps(db['settings'], ensure_ascii=False)}
    """

    messages_payload = [{"role": "system", "content": system_prompt}]
    # ส่งประวัติ 6 ข้อความล่าสุดให้ AI อ่าน (ไม่ส่งทั้งหมดเพื่อประหยัด Token)
    for msg in st.session_state.chat_history[-6:]:
        if msg["role"] != "system":
             messages_payload.append({"role": msg["role"], "content": msg["content"]})

    with st.spinner("Calculating..."):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages_payload,
                temperature=0.5,
            )
            content = response.choices[0].message.content
            
            # Extract JSON
            json_match = re.search(r"```json(.*?)```", content, re.DOTALL)
            
            story_text = content
            json_str = ""

            if json_match:
                story_text = content.replace(json_match.group(0), "").strip()
                json_str = json_match.group(1).strip()
                
                # Logic Update
                data = json.loads(json_str)
                t = data.get('time_passed', {})
                add_time(db, t.get('days',0), t.get('hours',0), t.get('minutes',0))
                
                if data.get('new_log_entry'):
                    db['log'].append(data['new_log_entry'][:120])
                
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
                    for name, cdata in updates['characters'].items():
                        if name not in db['characters']: db['characters'][name] = cdata
                        else:
                            if 'status' in cdata: db['characters'][name]['status'] = cdata['status']
                            if 'stats' in cdata: db['characters'][name]['stats'].update(cdata['stats'])

                save_json(DB_FILE, db)
            
            # 2. Assistant Message (Save to File)
            ai_msg = {"role": "assistant", "content": story_text}
            if json_str: ai_msg["debug_json"] = json_str
            
            st.session_state.chat_history.append(ai_msg)
            save_json(DIALOG_FILE, st.session_state.chat_history) # <--- บันทึกถาวรตรงนี้

            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")