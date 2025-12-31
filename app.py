import streamlit as st
import json
import openai
from datetime import datetime, timedelta
import os
import re
import shutil
import google.generativeai as genai

# ================= CONFIG =================
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
else:
    st.error("ไม่พบ API Key ใน Secrets")
    st.stop()

if "GOOGLE_API_KEY" in st.secrets:
    google_api_key = st.secrets["GOOGLE_API_KEY"]
else:
    st.error("ไม่พบ API Key ใน Secrets")
    st.stop()

genai.configure(api_key=google_api_key)

client = openai.OpenAI(api_key=api_key)

DB_FILE = 'db.json'
DIALOG_FILE = 'dialog.json'
PROMPT_FILE = 'prompt.json'
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

previous_story = []
prompt_data = load_json(PROMPT_FILE)

def ask_gemini_story(prompt, context):
    validator_instruction = prompt_data.get("story_prompt", "").format(
        context=context,  # เอาตัวแปร context ใส่แทนที่ {context}
        previous_story=previous_story  # เอาตัวแปร previous_story ใส่แทนที่ {previous_story}
    )
    # if model f error model_name='gemini-1.5-flash-latest'

    try:
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=validator_instruction
        )

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"[Gemini Crosscheck Error]: {e}")
        return f"error {e.message}"


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
    stamina_pct = p['stats'].get('stamina_percent', 100) / 100.0
    st.progress(min(stamina_pct, 1.0), text=f"⚡ Stamina: {p['stats']['stamina']}")

    # 3. BASIC STATS (Grid Layout)
    c1, c2 = st.columns(2)
    c1.metric("STR", p['stats'].get('strength', 0))
    c2.metric("SPD", p['stats'].get('speed', 0))

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

    with st.expander("🛠️ Debug: Raw Database (JSON)", expanded=False):

        # ปุ่มกด Refresh เผื่อค่าไม่ไม่อัปเดต
        if st.button("🔄 Refresh Data"):
            st.rerun()

        # แสดง JSON ทั้งก้อน (Interactive: กดลูกศรพับ/กางดูได้เลย)
        st.json(db)

    st.divider()

    st.subheader("📂 File Manager")
    tab_db, tab_dialog, tab_prompt = st.tabs(["DB", "Dialog", "Prompt"])
    with tab_db:
        st.write("จัดการข้อมูลผู้เล่น (db.json)")

        # Download
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                st.download_button(
                    label="⬇️ Download DB",
                    data=f,
                    file_name="db.json",
                    mime="application/json"
                )

        # Upload
        uploaded_db = st.file_uploader("Upload DB", type=["json"], key="up_db")
        if uploaded_db:
            try:
                # แปลงไฟล์ที่อัปโหลดเป็น Dict แล้วเซฟทับ
                new_data = json.load(uploaded_db)
                save_json(DB_FILE, new_data)
                st.success("✅ อัปเดต DB สำเร็จ! (Reloading...)")
                st.rerun()  # รีเฟรชหน้าจอทันที
            except Exception as e:
                st.error(f"ไฟล์ JSON เสียหาย: {e}")

    # ================= 2. Dialog Manager =================
    with tab_dialog:
        st.write("จัดการประวัติแชท (dialog.json)")

        # Download
        if os.path.exists(DIALOG_FILE):
            with open(DIALOG_FILE, "rb") as f:
                st.download_button(
                    label="⬇️ Download Dialog",
                    data=f,
                    file_name="dialog.json",
                    mime="application/json"
                )

        # Upload
        uploaded_dialog = st.file_uploader("Upload Dialog", type=["json"], key="up_dialog")
        if uploaded_dialog:
            try:
                new_data = json.load(uploaded_dialog)
                save_json(DIALOG_FILE, new_data)
                # โหลดเข้า session state ด้วยถ้าจำเป็น
                # st.session_state.chat_history = new_data
                st.success("✅ อัปเดต Dialog สำเร็จ!")
                st.rerun()
            except Exception as e:
                st.error(f"ไฟล์เสียหาย: {e}")

    # ================= 3. Prompt Manager (New!) =================
    with tab_prompt:
        st.write("แก้ Prompt ทันที (prompt.json)")

        # Download
        if os.path.exists(PROMPT_FILE):
            with open(PROMPT_FILE, "rb") as f:
                st.download_button(
                    label="⬇️ Download Prompts",
                    data=f,
                    file_name="prompt.json",
                    mime="application/json"
                )

        # Upload
        uploaded_prompt = st.file_uploader("Upload Prompts", type=["json"], key="up_prompt")
        if uploaded_prompt:
            try:
                new_data = json.load(uploaded_prompt)
                # เช็คหน่อยว่ามี Key ครบไหม
                if "system_prompt" in new_data:
                    save_json(PROMPT_FILE, new_data)
                    st.success("✅ เปลี่ยน Prompt เรียบร้อย!")
                    st.rerun()
                else:
                    st.error("JSON ต้องมี key 'system_prompt'")
            except Exception as e:
                st.error(f"ไฟล์เสียหาย: {e}")

    st.divider()
    # 6. SYSTEM CONTROLS
    if st.button("🗑️ Reset Story", type="primary", use_container_width=True):

        try:
            # ก็อปปี้ไฟล์ db_backup.json มาทับ db.json
            shutil.copy('db_backup.json', 'db.json')
            print("[System]: Database restored from backup.")
        except FileNotFoundError:
            st.error("ไม่พบไฟล์ db_backup.json! กรุณาสร้างไฟล์ backup ไว้ก่อนครับ")

        st.session_state.chat_history = []
        save_json(DIALOG_FILE, [])
        st.rerun()

# --- MAIN CHAT ---
st.header("🌊 One Piece AI RPG: Persistent World")

# Render History
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # แสดง System Log เฉพาะฝั่ง Assistant (AI)
        if message["role"] == "assistant":
            with st.expander("🔍 System Log (Debug & Cross-check)"):
                # สร้าง Tab 3 อันเพื่อแยกข้อมูลให้ดูง่าย
                tab_json, tab_compare = st.tabs(["💾 JSON Data", "🆚 GPT vs Gemini"])

                # Tab 1: ข้อมูล JSON ที่เอาไปอัปเดต DB
                with tab_json:
                    # ใช้ .get กัน Error กรณีข้อความเก่าไม่มี key นี้
                    st.code(message.get("debug_json", "{}"), language="json")

                # Tab 2: เปรียบเทียบ Raw Response
                with tab_compare:
                    c1, c2 = st.columns(2)

                    with c1:
                        st.markdown("### 🤖 GPT-4o (Draft)")
                        st.caption("ร่างแรกก่อนตรวจ")
                        # ใช้ text_area หรือ code เพื่อให้ scroll ได้ถ้าข้อความยาว
                        st.code(message.get("gpt_raw", "No Data"), language="markdown")

                    with c2:
                        st.markdown("### 👨‍🏫 Gemini (Final)")
                        st.caption("ผ่านการ Cross-check แล้ว")
                        st.code(message.get("gemini_raw", "No Data"), language="markdown")

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

    context = f"""
    Previous story:{previous_story}
    
    [CONTEXT DATA]
        Player: {json.dumps(p, ensure_ascii=False)}
        World Status: {json.dumps(db['world'], ensure_ascii=False)}
        Current Location Info: {json.dumps(loc_data, ensure_ascii=False)}
        Settings: {json.dumps(db['settings'], ensure_ascii=False)}
        Characters:  {json.dumps(db['characters'], ensure_ascii=False)}
    """
    with st.spinner("Calculating..."):
        gemini_story = ask_gemini_story(
            prompt= prompt,
            context= context
         )
    if len(previous_story) == 3:
        previous_story.clear()
    previous_story.append(gemini_story)

    story = f"Story: {gemini_story}"
    outout_format = f"""
    [STRICT OUTPUT FORMAT]
        You must follow this layout exactly:
        1. **Final story after verify imd improve.
        2. **[Result]:** (Summary: Success/Failure, HP loss, Location change status, etc)   
        3. **Choices:**
            1. [Choice A]
            2. [Choice B]
            3. [Choice C]        
        4. **JSON Block:** strictly at the end.
           - **PURE JSON ONLY:** Do NOT include comments (e.g., // or /* */) inside the JSON block.
           - **NO TRAILING COMMAS:** Ensure the last item in a list/object does not have a comma.
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
    """
    context_data = f"""
    [CONTEXT DATA]
    Player: {json.dumps(p, ensure_ascii=False)}
    World Status: {json.dumps(db['world'], ensure_ascii=False)}
    Current Location Info: {json.dumps(loc_data, ensure_ascii=False)}
    Settings: {json.dumps(db['settings'], ensure_ascii=False)}
    Characters:  {json.dumps(db['characters'], ensure_ascii=False)}
    """
    raw_template = prompt_data.get("system_prompt", "")

    system_prompt = raw_template + "\n" + story + "\n" + outout_format + "\n" + context_data

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
            gpt_content = response.choices[0].message.content

            # Extract JSON
            json_match = re.search(r"```json(.*?)```", gpt_content, re.DOTALL)

            story_text = gpt_content
            json_str = ""

            if json_match:
                story_text = gpt_content.replace(json_match.group(0), "").strip()
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

                        # Inventory (List)
                        if 'inventory' in p_up: db['player']['inventory'] = p_up['inventory']

                        # Location (String)
                        if 'current_location' in p_up:
                            db['player']['current_location'] = p_up['current_location']

                        # Crew (List)
                        if 'crew' in p_up: db['player']['crew'] = p_up['crew']

                        # Abilities (List)
                        if 'traits' in p_up and 'abilities' in p_up['traits']:
                            if 'traits' not in db['player']: db['player']['traits'] = {}
                            db['player']['traits']['abilities'] = p_up['traits']['abilities']

                        # Stats (Dict)
                        if 'stats' in p_up: db['player']['stats'].update(p_up['stats'])

                        # Reputation (Dict)
                        if 'reputation' in p_up:
                            if 'reputation' not in db['player']: db['player']['reputation'] = {}
                            db['player']['reputation'].update(p_up['reputation'])

                        # Vehicle (Dict)
                        if 'vehicle' in p_up:
                            if 'vehicle' not in db['player']: db['player']['vehicle'] = {}
                            if 'status' in p_up['vehicle']:
                                if 'status' not in db['player']['vehicle']: db['player']['vehicle']['status'] = {}
                                db['player']['vehicle']['status'].update(p_up['vehicle']['status'])

                        # Devil Fruit (Dict)
                        if 'devil_fruit' in p_up:
                            if 'devil_fruit' not in db['player']: db['player']['devil_fruit'] = {}
                            db['player']['devil_fruit'].update(p_up['devil_fruit'])

                        # Haki (Dict)
                        if 'haki' in p_up:
                            if 'haki' not in db['player']: db['player']['haki'] = {}
                            db['player']['haki'].update(p_up['haki'])

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

            # st.session_state.chat_history.append(ai_msg)
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": story_text,
                "debug_json": json_str,
                "gpt_raw": gpt_content,
                "gemini_raw": gemini_story
            })


            save_json(DIALOG_FILE, st.session_state.chat_history)  # <--- บันทึกถาวรตรงนี้

            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")