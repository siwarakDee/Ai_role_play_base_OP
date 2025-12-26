import streamlit as st
import json
import openai
from datetime import datetime, timedelta
import os
import re

# ================= CONFIG =================
# ดึง Key จาก Secrets
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    st.error("ไม่พบ API Key ใน Secrets กรุณาตั้งค่าก่อน")
    st.stop()

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

# --- SIDEBAR HUD (แสดงสถานะซ้ายมือ) ---
p = db['player']
with st.sidebar:
    st.title(f"🏴‍☠️ {p['name']}")
    st.write(f"📍 **Loc:** {p['current_location']}")
    st.write(f"📅 **Time:** {db['world']['current_time']}")
    
    # HP Bar
    max_hp = 500 # สมมติ Max HP
    current_hp = p['stats']['hp']
    hp_percent = min(current_hp / max_hp, 1.0)
    st.progress(hp_percent, text=f"❤️ HP: {current_hp}")
    
    st.divider()
    st.subheader("🎒 Inventory")
    for item in p['inventory']:
        st.caption(f"- {item}")
        
    st.divider()
    if db['log']:
        st.info(f"📜 **Last Log:** {db['log'][-1]}")
        
    # ปุ่ม Reset (เผื่อค้าง)
    if st.button("รีเซ็ตประวัติแชท"):
        st.session_state.chat_history = []
        st.rerun()

# --- MAIN CHAT INTERFACE ---
st.header("🌊 One Piece AI RPG: New World")

# 1. แสดงประวัติการคุยเก่า (Render History)
# ส่วนนี้จะทำงานทุกครั้งที่ Rerun ทำให้ข้อความไม่หาย
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "debug_json" in message:
            with st.expander("🔍 ดูเบื้องหลัง (Game Engine)"):
                st.code(message["debug_json"], language="json")

# 2. รับ Input
if prompt := st.chat_input("สั่งการกัปตัน... (เช่น ไปเกาะถัดไป, กินเนื้อ)"):
    
    # 2.1 แสดงข้อความผู้เล่นทันที (เพื่อความลื่นไหล)
    with st.chat_message("user"):
        st.markdown(prompt)
    # บันทึกข้อความผู้เล่นลง Memory ทันที
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    # เตรียม Data สำหรับส่ง AI
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

    # เตรียม History ส่งให้ AI (ตัดเอาแค่ 6 ข้อความล่าสุด)
    messages_payload = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.chat_history[-6:]:
        if msg["role"] != "system":
             messages_payload.append({"role": msg["role"], "content": msg["content"]})

    # 3. เรียก AI (แสดง Spinner หมุนๆ ระหว่างรอ)
    with st.spinner("Oda Sensei กำลังคำนวณ..."):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages_payload,
                temperature=0.5,
            )
            content = response.choices[0].message.content
            
            # 4. แยก JSON กับ เนื้อเรื่อง
            json_match = re.search(r"```json(.*?)```", content, re.DOTALL)
            
            story_text = content
            json_str = ""

            if json_match:
                story_text = content.replace(json_match.group(0), "").strip()
                json_str = json_match.group(1).strip()
                
                # --- UPDATE DATABASE (คำนวณหลังบ้านเงียบๆ) ---
                data = json.loads(json_str)
                
                # Update Time
                t = data.get('time_passed', {})
                add_time(db, t.get('days',0), t.get('hours',0), t.get('minutes',0))
                
                # Update Log
                if data.get('new_log_entry'):
                    db['log'].append(data['new_log_entry'][:120])
                
                # Update Game Data
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

                # บันทึกลงไฟล์
                save_db(db)
            
            # 5. บันทึกคำตอบ AI ลง Memory (สำคัญมาก! ต้องทำก่อน Rerun)
            ai_msg_obj = {"role": "assistant", "content": story_text}
            if json_str:
                ai_msg_obj["debug_json"] = json_str # แอบเก็บ JSON ไว้ดู
            
            st.session_state.chat_history.append(ai_msg_obj)

            # 6. สั่งรีเฟรชหน้าจอ (Rerun)
            # พอรีเฟรช มันจะวิ่งไปบรรทัดบนสุดใหม่ แล้ววาด History ทั้งหมดออกมาเอง
            st.rerun()

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")