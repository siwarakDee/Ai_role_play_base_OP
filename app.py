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


def ask_gemini_crosscheck(gpt_response, full_system_prompt):
    validator_instruction = f"""
    You are the "Editor-in-Chief" for a One Piece RPG.
    Your goal is to **CROSS-CHECK Logic** AND **REWRITE Narrative** to be more exciting.

    [YOUR MISSION]
    1. **Analyze:** Read the GPT Draft Response below.
    2. **Security Check (Logic Gate):**
       - **Teleport Hack:** Did they move instantly across oceans? (e.g. East Blue -> New World). -> IF YES: REWRITE to "Lost at sea" or "Storm blocked".
       - **God Mode:** Did Lvl 1 beat a Boss? -> IF YES: REWRITE to "Instantly Defeated".
       - **Item Hack:** Used item not in inventory? -> IF YES: REWRITE to "Item not found".
    3. **Narrative Polish (MANDATORY):**
       - **DO NOT just copy the draft.** Even if the logic is correct, you MUST IMPROVE it.
       - **REWRITE** the `[Event]` and `[NPC]` sections to be "One Piece Style" (Dramatic, Funny, Emotional, Action-packed).
       - Add Sound Effects (e.g., *Doom!!*, *Fwoosh!*) and character tone.
    4. 3. **JSON Synchronization (CRITICAL):**
       - **Do NOT blindly copy the Draft JSON.**
       - If you changed the outcome (e.g. Success -> Fail), you **MUST** modify the JSON values (HP, Inventory, Location) to match YOUR new story.
       - *Example:* If you wrote that the player "got hit by a cannonball", the JSON `player.stats.hp` MUST decrease.
       - *Example:* If you wrote that "The treasure was fake", the JSON `player.inventory` MUST NOT have the treasure.

    [STRICT OUTPUT FORMAT]
    1. **[Event]:** (Rewrite this to be exciting, ~3-5 lines)
    2. **[NPC]:** (Add lively dialogue/action. If none, keep empty)
    3. **[Result]:** (Clear summary of consequences, fix if logic was wrong)
    4. **Choices:** (Keep 3 choices)

    5. **JSON Block:** strictly at the end. Recheck json value is 
       Format: 
       ```json 
       {{ 
         "time_passed": {{ "days": 0, "hours": 0, "minutes": 0 }},
         "log_entry": "Summary log",
         "player": {{...}}, 
         "world": {{...}},
         "characters": {{...}},
         "locations": {{...}},
         "unique_items": {{...}}
       }} 
       ```

    =========================================
    [REFERENCE RULES & CONTEXT]
    {full_system_prompt} 
    =========================================
    """

    # ส่งเนื้อหาให้ตรวจ
    content_to_review = f"""
    --- DRAFT RESPONSE TO IMPROVE (FROM GPT) ---
    {gpt_response}
    """

    try:
        # ใช้ Flash เพื่อความเร็ว
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=validator_instruction
        )

        response = model.generate_content(content_to_review)
        return response.text

    except Exception as e:
        print(f"[Gemini Crosscheck Error]: {e}")
        return gpt_response  # ถ้า Gemini ล่ม ให้ใช้ของ GPT ไปก่อน


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
# for message in st.session_state.chat_history:
#     with st.chat_message(message["role"]):
#         st.markdown(message["content"])
#         if "debug_json" in message:
#             with st.expander("🔍 System Log"):
#                 st.code(message["debug_json"], language="json")
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

    system_prompt = f"""
    Role: Eiichiro Oda (Ultimate Game Master of One Piece RPG).
    Tone: Exciting, Emotional, Dramatic (Shonen Manga Style). 
    Language: Thai (Rich descriptions, Character Dialogues).
    
    [STRICT NARRATIVE & DIALOGUE RULES]
    1. **Dialogue is MUST:** ห้ามเล่าสรุปเหตุการณ์เฉยๆ แต่ต้อง **"เขียนบทพูด"** ออกมาให้สมจริง
    2. **Character Personality:** NPC ต้องมีนิสัยเฉพาะตัว (Nami, Villagers, Marines) ตอบโต้ตามสถานการณ์
    3. **Reactive World:** ถ้าผู้เล่นทำชั่ว บรรยากาศต้องกดดัน ถ้าทำดี ต้องได้รับการสรรเสริญ
    
    [STRICT RULES - LOGIC & PROGRESSION]
    1. **NO Player Puppeteering:** NEVER write dialogue or internal thoughts for the Player (Mosu). Describe only external events and results.
    2. **Logic Gate (Anti-God Mode):**
       - **Impossible Requests = FAILURE:** If a player asks to do something impossible (e.g., "Go to Laugh Tale" from East Blue, "Kill Kaido" at Lvl 1), the result MUST be **FAILURE**. 
       - **Punishment:** Describe the failure realistically (e.g., "You sailed out but got lost in a storm and returned to shore," or "The Sea King attacked you immediately").
    3. **Inventory Check:** BEFORE allowing item usage, verify if the item exists in Inventory.
    4. **Geography & Navigation (CRITICAL):**
       - **Connection Only:** Player can ONLY travel to locations connected in the `loc_data`.
       - **Grand Line Physics:** You CANNOT go straight to 'Laugh Tale' (Raftel) or 'New World' from 'East Blue'. You must follow the route: East Blue -> Reverse Mountain -> Paradise -> New World.
       - **Laugh Tale Lock:** Attempting to go to Laugh Tale without 4 Road Poneglyphs results in getting lost in the mist/storms forever.
       - **EXCEPTION:** 'Bartholomew Kuma' crew member allows Fast Travel (ignores connection).
    5. **Battle System:** Analyze Stats. Do NOT let low-level players beat Bosses.
    6. **New Discoveries:** If new unique items/locations/chars appear, return them in JSON.
    
    [RELATIONSHIP SYSTEM (Friendship)]
    1. **Scale:** -1000 to +1000.
    2. **Effect:** Affects NPC dialogue and willingness to help.
    3. **Dynamic Update:** ALWAYS return updated `friendship` in JSON if changed.
    
    [STRICT OUTPUT FORMAT]
        You must follow this layout exactly:
    1. **[Event]:** (Short description of what happened, 3-5 lines max. Focus on Action/Result)
    2. **[NPC]:** (NPC Name says or NPC actions "..." - Only if NPC is present)
    3. **[Result]:** (Summary: Success/Failure, HP loss, Location change status, etc)
        
    4. **Choices:**
        1. [Choice A]
        2. [Choice B]
        3. [Choice C]        
    
    5. **JSON Block:** strictly at the end.
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
    Characters:  {json.dumps(db['characters'], ensure_ascii=False)}
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
            gpt_draft_content = response.choices[0].message.content

            final_content = ask_gemini_crosscheck(
                gpt_response=gpt_draft_content,
                full_system_prompt=system_prompt
            )

            # Extract JSON
            json_match = re.search(r"```json(.*?)```", final_content, re.DOTALL)

            story_text = final_content
            json_str = ""

            if json_match:
                story_text = final_content.replace(json_match.group(0), "").strip()
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
                        if 'current_location' in p_up:
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
                        if 'exp' in p_up: db['player']['exp'].update(p_up['exp'])
                        if 'level' in p_up: db['player']['level'].update(p_up['level'])
                        if 'abilities' in p_up: db['player']['traits']['abilities'].update(p_up['abilities'])
                        if 'devil_fruit' in p_up: db['player']['devil_fruit'].update(p_up['devil_fruit'])
                        if 'crew' in p_up: db['player']['crew'].update(p_up['crew'])
                        if 'haki' in p_up: db['player']['haki'].update(p_up['haki'])

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
                        if 'abilities' in p_up:
                            if 'traits' not in db['player']: db['player']['traits'] = {}
                            db['player']['traits']['abilities'] = p_up['abilities']

                        # Level & Exp (Int)
                        if 'exp' in p_up: db['player']['exp'] = p_up['exp']
                        if 'level' in p_up: db['player']['level'] = p_up['level']

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
                "content": story_text,  # เนื้อเรื่องที่ผ่านการตัด JSON ออกแล้ว
                "debug_json": json_str,  # JSON string เพียวๆ

                # >>> เพิ่ม 2 บรรทัดนี้ครับ <<<
                "gpt_raw": gpt_draft_content,
                "gemini_raw": final_content
            })


            save_json(DIALOG_FILE, st.session_state.chat_history)  # <--- บันทึกถาวรตรงนี้

            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")