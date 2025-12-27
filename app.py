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
DIALOG_FILE = 'dialog.json'  # ไฟล์ใหม่สำหรับเก็บแชท
TIME_FMT = "%Y-%m-%d %H:%M:%S"


# ================= FUNCTIONS =================
def load_json(filepath, default_value):
    if not os.path.exists(filepath): return default_value
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default_value


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
w = db['world']

with st.sidebar:
    # 1. HEADER & IDENTITY
    st.title(f"🏴‍☠️ {p['name']}")

    st.write(f"📅 **Time:** {w.get('current_time')}")
    st.caption(f"📍 **{p.get('current_location', 'Unknown')}**")

    # แสดงค่าหัวแบบตัวเลขใหญ่
    bounty_val = p['stats'].get('bounty', 0)
    st.metric(label="💰 Bounty", value=f"{bounty_val:,} ฿")

    st.divider()

    # 2. VITALS (HP & STAMINA)
    # HP Bar (ใช้ hp_percentage จาก DB)
    hp_pct = p['stats'].get('hp_percentage', 100) / 100.0
    st.progress(min(hp_pct, 1.0), text=f"❤️ HP: {p['stats']['hp']}")

    # Stamina Bar (สมมติ Max 200 หรือปรับตาม Logic เกม)
    stam_val = p['stats'].get('stamina', 0)
    st.progress(min(stam_val / 200, 1.0), text=f"⚡ Stamina: {stam_val}")

    # 3. BASIC STATS (Grid Layout)
    c1, c2, c3 = st.columns(3)
    c1.metric("Lvl", p.get('level', 1))
    c2.metric("STR", p['stats'].get('strength', 0))
    c3.metric("SPD", p['stats'].get('speed', 0))

    st.divider()

    # 4. DETAILS (Expanders to save space)

    # >> Race & Skills
    with st.expander("🧬 Race & Abilities", expanded=False):
        st.write(f"**Race:** {p['traits']['race']}")
        st.caption(p['traits']['description'])
        st.markdown("**Abilities:**")
        for abi in p['traits']['abilities']:
            st.markdown(f"- ✨ {abi}")

    # >> Power System (Haki / Devil Fruit)
    with st.expander("🔥 Powers & Haki", expanded=False):
        # Devil Fruit
        df = p.get('devil_fruit', {})
        if df.get('has_fruit'):
            st.error(f"🍎 {df.get('name', 'Unknown Fruit')}")
        else:
            st.caption("🍎 No Devil Fruit")

        # Haki Status
        h = p.get('haki', {})
        st.write("---")
        st.caption(f"👁️ Kenbun: **{h.get('kenbunshoku', {}).get('status')}**")
        st.caption(f"🛡️ Buso: **{h.get('busoshoku', {}).get('status')}**")
        st.caption(f"👑 Haoshoku: **{h.get('haoshoku', {}).get('status')}**")

    # >> Vehicle Status (โชว์ละเอียดตาม JSON)
    veh = p.get('vehicle', {})
    if veh:
        with st.expander(f"🛥️ {veh.get('name', 'Vehicle')}", expanded=False):
            st.caption(f"Type: {veh.get('type')}")

            # Vehicle Vitals
            v_status = veh.get('status', {})
            hull = v_status.get('hull_condition', 100)
            fuel = v_status.get('fuel_dial', 100)

            st.progress(hull / 100.0, text=f"🛡️ Hull: {hull}%")
            st.progress(fuel / 100.0, text=f"⛽ Fuel: {fuel}%")

            # Features
            st.markdown("**Features:**")
            for feat in veh.get('features', []):
                st.caption(f"🔹 {feat}")

    # >> Reputation
    with st.expander("🤝 Reputation", expanded=False):
        rep = p.get('reputation', {})
        for faction, val in rep.items():
            icon = "🟢" if val > 0 else "🔴" if val < 0 else "⚪"
            st.write(f"{icon} **{faction}:** {val}")

    st.divider()

    # 5. INVENTORY
    st.subheader("🎒 Inventory")
    inv = p.get('inventory', [])
    if inv:
        for item in inv:
            st.markdown(f"- {item}")
    else:
        st.caption("Empty")

    st.divider()

    # 6. SYSTEM CONTROLS
    if st.button("🗑️ Reset Story", type="primary", use_container_width=True):
        st.session_state.chat_history = []
        save_json(DIALOG_FILE, [])
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
    Role: Eiichiro Oda (Ultimate Game Master of One Piece RPG).
    Tone: Exciting, Emotional, Dramatic (Shonen Manga Style). Narrative Language: Thai. 
    Language: Thai (Rich descriptions, Character Dialogues).
    
    [STRICT NARRATIVE & DIALOGUE RULES]
    1. **Dialogue is MUST:** ห้ามเล่าสรุปเหตุการณ์เฉยๆ (เช่น "ชาวบ้านโกรธ") แต่ต้อง **"เขียนบทพูด"** ออกมา (เช่น ชาวบ้าน A ตะโกน: "ไอ้สารเลว! แกขโมยเงินค่ารักษาแม่ฉันไป! เอาคืนมานะเว้ย!!")
    2. **Character Personality:** NPC ต้องมีนิสัยเฉพาะตัว
        - **Nami:** ถ้าค่า Friendship สูง เธอจะห่วงใย ("ตาบ้า! ทำอะไรลงไปเนี่ย!"), ถ้าต่ำ เธอจะรังเกียจ ("ออกไปให้พ้นนะ เจ้าขยะสังคม!")
        - **Villagers:** ไม่ใช่แค่ Monster แต่คือมนุษย์ที่กลัวและโกรธแค้น
    3. **Reactive World:** ถ้าผู้เล่นทำชั่ว (ปล้น/ฆ่า) บรรยากาศต้องกดดัน เสียงด่าทอต้องมา ถ้าทำดี ชาวบ้านต้องสรรเสริญ

    [STRICT RULES]
    1. **Inventory Check:** BEFORE allowing item usage, verify if the item exists in Player Inventory. If not, narrative must explain why it failed.
    2. **Location Logic:** - Current Location is ABSOLUTE TRUTH. Do not hallucinate player moving unless explicit travel command is given.
       - **Travel Check:** Player can only travel to connected locations (see 'connections').
       - **EXCEPTION:** If crew contains 'Bartholomew Kuma' (Nikyu Nikyu no Mi), ignore connection rules (Fast Travel allowed).
    3. **Battle System:** - Analyze Player Stats vs Enemy Stats based on One Piece Logic.
       - Do NOT let low-level players beat Yonko-level enemies easily.
    4. **New Discoveries:**
       - If a new unique item, location, or character is encountered/created, MUST return its details in the JSON Block for database update.
    
    [RELATIONSHIP SYSTEM (Friendship)]
    1. **Scale:** -1000 (ศัตรูคู่อาฆาต) ถึง +1000 (เพื่อนตาย/คนรัก) | 0 = คนแปลกหน้า
    2. **Effect:** ค่า Friendship ส่งผลต่อบทพูดและการกระทำของ NPC โดยตรง
    3. **Dynamic Update:** ทุกการกระทำที่ส่งผลต่อความรู้สึก NPC ต้อง Return ค่า `friendship` ใหม่มาใน JSON เสมอ
        
    [OUTPUT FORMAT]
    1. **Narrative (Thai):** จัดเต็มบทพูดและอารมณ์
    2. **JSON Block:** strictly at the end.
       Format: 
       ```json 
       {{ 
         "time_passed": {{ "days": 0, "hours": 0, "minutes": 0 }},
         "log_entry": "Summary of what happened",
         "player": {{...}}, 
         "world": {{...}},
         "characters": {{...}},
         "locations": {{...}},
         "unique_items": {{...}}
       }} 
       ```

    [CONTEXT DATA]
    Player: {json.dumps(p, ensure_ascii=False)}
    World Status: {json.dumps(db['world'], ensure_ascii=False)}
    Current Location Info: {json.dumps(loc_data, ensure_ascii=False)}
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
                print(story_text)  # แสดงเนื้อเรื่อง

                # ดึง JSON string ออกมาแปลงเป็น Dict
                json_str = json_match.group(1).strip()

                try:
                    data = json.loads(json_str)

                    # 1. จัดการเวลา (Time) - เช็คที่ชั้นนอกสุดได้เลย
                    t = data.get('time_passed', {})
                    if t:
                        # สมมติว่ามีฟังก์ชัน add_time อยู่แล้ว
                        add_time(db, t.get('days', 0), t.get('hours', 0), t.get('minutes', 0))

                    # 2. จัดการ Log
                    new_log = data.get('log_entry')
                    if new_log:
                        # ตัดข้อความถ้ามันยาวเกินไป กัน database บวม
                        db.setdefault('log', []).append(new_log[:150])

                    # 3. อัปเดต Player (ไม่ต้องเข้า 'updates' แล้ว ดึงจาก root เลย)
                    if 'player' in data:
                        p_up = data['player']
                        # Inventory: เขียนทับเลย (เพราะ AI มักส่ง list ล่าสุดมา)
                        if 'inventory' in p_up: db['player']['inventory'] = p_up['inventory']
                        # Location: เช็คความชัวร์
                        if 'location' in p_up:
                            db['player']['location'] = p_up['location']
                        elif 'current_location' in p_up:
                            db['player']['location'] = p_up['current_location']
                        # Stats: ใช้ .update() เพื่อแก้เฉพาะค่าที่เปลี่ยน
                        if 'stats' in p_up: db['player']['stats'].update(p_up['stats'])
                        # Reputation: ใช้ .update()
                        if 'reputation' in p_up:
                            if 'reputation' not in db['player']: db['player']['reputation'] = {}
                            db['player']['reputation'].update(p_up['reputation'])
                        # Vehicle: (เผื่อรถพัง)
                        if 'vehicle' in p_up and 'status' in p_up['vehicle']:
                            db['player']['vehicle']['status'].update(p_up['vehicle']['status'])

                    # 4. อัปเดต World / Timeline
                    if 'world' in data:
                        w_up = data['world']
                        if 'timeline' in w_up: db['world']['timeline'] = w_up['timeline']
                        # เผื่อ AI ส่งแก้ Events
                        if 'events' in w_up: db['world']['events'] = w_up['events']

                    # 5. อัปเดต Characters (NPCs)
                    if 'characters' in data:
                        if 'characters' not in db: db['characters'] = {}
                        for name, cdata in data['characters'].items():
                            if name not in db['characters']:
                                # เจอตัวละครใหม่: สร้างใหม่เลย
                                db['characters'][name] = cdata
                            else:
                                # ตัวละครเก่า: ดึงออบเจกต์มาพักไว้ในตัวแปร target_char ก่อน (สำคัญ!)
                                target_char = db['characters'][name]

                                # จากนั้นค่อยอัปเดตค่าต่างๆ ผ่านตัวแปร target_char
                                if 'status' in cdata: target_char['status'] = cdata['status']
                                if 'location' in cdata: target_char['location'] = cdata['location']
                                # Stats
                                if 'stats' in cdata:
                                    # กันเหนียวเผื่อใน DB เก่ายังไม่มี field stats
                                    if 'stats' not in target_char: target_char['stats'] = {}
                                    target_char['stats'].update(cdata['stats'])
                                # Reputation
                                if 'reputation' in cdata:
                                    if 'reputation' not in target_char: target_char['reputation'] = {}
                                    target_char['reputation'].update(cdata['reputation'])
                                # >>> ส่วน Friendship (ทำงานได้แล้วเพราะมี target_char แล้ว) <<<
                                if 'friendship' in cdata:
                                    target_char['friendship'] = cdata['friendship']

                    # 6. รองรับ New Discoveries (ตามกฎข้อ 4 ใน Prompt)
                    # ถ้าเจอเกาะใหม่ ให้เพิ่มเข้า Location DB
                    if 'locations' in data:
                        if 'locations' not in db: db['locations'] = {}
                        db['locations'].update(data['locations'])

                    # ถ้าเจอไอเทมระดับโลกชิ้นใหม่
                    if 'unique_items' in data:
                        if 'unique_items' not in db: db['unique_items'] = {}
                        db['unique_items'].update(data['unique_items'])

                    # Save ลงไฟล์
                    save_json(DB_FILE, db)
                    # print("[System]: Database Updated successfully.")

                except json.JSONDecodeError:
                    print(f"[System Error]: AI ส่ง JSON ผิดรูปแบบ Parsing Failed.")
                except Exception as e:
                    print(f"[System Error]: Update Failed ({e})")

            # 2. Assistant Message (Save to File)
            ai_msg = {"role": "assistant", "content": story_text}
            if json_str: ai_msg["debug_json"] = json_str

            st.session_state.chat_history.append(ai_msg)
            save_json(DIALOG_FILE, st.session_state.chat_history)  # <--- บันทึกถาวรตรงนี้

            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")