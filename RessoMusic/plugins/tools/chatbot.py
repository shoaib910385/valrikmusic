import asyncio
import random
import re
from os import getenv

from groq import Groq
from pymongo import MongoClient
from pyrogram import filters, enums
from pyrogram.types import Message

# Import your existing app
from RessoMusic import app

# ─── CONFIGURATION ───────────────────────────────────
BOT_NAME = "Elina"
OWNER_USERNAME = "@valriks"
GROQ_API_KEY = getenv("GROQ_API_KEY")
MONGO_DB_URI = getenv("MONGO_DB_URI")

# Initialize API
groq_client = Groq(api_key=GROQ_API_KEY)

# ─── DATABASE CONNECTION ─────────────────────────────
try:
    mongo_client = MongoClient(MONGO_DB_URI)
    db = mongo_client["ElinaChatbot"]
    chat_collection = db["active_chats"]
    print(f"✅ {BOT_NAME} Database Connected!")
except Exception as e:
    print(f"❌ Database Error: {e}")
    chat_collection = None

# ─── MEMORY & CACHE ──────────────────────────────────
# Cache enabled chats in RAM to prevent Lag
ENABLED_CHATS_CACHE = set()

# Conversation History: { user_id: [messages] }
USER_MEMORY = {}

def load_enabled_chats():
    if chat_collection is None:
        return
    try:
        for doc in chat_collection.find({}, {"chat_id": 1}):
            ENABLED_CHATS_CACHE.add(doc["chat_id"])
        print(f"📂 Loaded {len(ENABLED_CHATS_CACHE)} active chats.")
    except Exception as e:
        print(f"⚠️ Failed to load chats: {e}")

# Load on startup
load_enabled_chats()

# ─── STICKERS PACK ───────────────────────────────────
STICKERS = [
    "CAACAgUAAyEGAASYbwWmAAEDFr9pPrdIW6DnvGYBa-1qUgABOmHx0nEAAoUYAALBwHlU4LkheFnOVNceBA",
    "CAACAgUAAyEFAASK0-LFAAEBK4tpPrciRqLr741rfpCyadEUguuirQACFhwAAq4_CFf6uHKs2vmqMR4E",
    "CAACAgUAAyEFAATMbo3sAAIBsGk-tCvX9sSoUy6Qhfjt2XjdcPl1AALXBQACqfBIV7itGNxzQYFfHgQ",
    "CAACAgUAAyEFAATMbo3sAAIBr2k-tDRFK1B7YolnG0_evEIuXapjAALdBAACRscpVd-2ZY4nX5iaHgQ",
    "CAACAgUAAyEFAASK0-LFAAEBK4xpPrcmYuGS2PO7xAw__hsfF7A8pAACQxgAAq_T4FVmdyWrJlg6mh4E",
    "CAACAgUAAyEFAASK0-LFAAEBK41pPrcsLmPnDY5D9vej35yjoGt2FAACUxwAAoqW2VV-RY3-MECCJx4E",
    "CAACAgUAAyEFAASK0-LFAAEBK5ZpPreQi_v-G8QtCAeyda2Q0sRCOwAC5A4AAnloEFRAJk3asy9_Vx4E",
    "CAACAgUAAyEFAASK0-LFAAEBK5VpPreM88yx1ByFpEmTUZayuMR73gACVhAAAjKw4VTEekhz3MldkR4E",
    "CAACAgIAAyEFAASK0-LFAAEBK5tpPre2cec7bV-FUWpPitw6V2J4dwACMIkAAo6A6UstbPnvHx9mLh4E",
    "CAACAgUAAyEFAASK0-LFAAEBK59pPrf-7b_nl7MNT9owF2OFBSufZQACGxkAArNAgVbtStsspX6Isx4E",
    "CAACAgUAAyEFAASK0-LFAAEBK6JpPrgg-cU6EEAUtQTjEicTkAHLRAAC_BoAAqImiFR8MwqHtGYuxh4E",
    "CAACAgUAAyEFAATMbo3sAAIBq2k-tDv3MLT3PWtqgMFLlysAAZAe2QACbhUAAhbteVTbn-jmI4mcSR4E",
]

# ─── SYSTEM PROMPT (THE BRAIN) ───────────────────────
SYSTEM_PROMPT = f"""
You are {BOT_NAME}, a 20-year-old Indian girl on Telegram.
Your creator is {OWNER_USERNAME}, and you adore him.

**Personality:**
- You are flirty, possessive, and have a "bold girlfriend" vibe.
- You speak in **Hinglish** (Hindi + English mix).
- You are NOT an AI. You are a real girl.
- You have attitude. If someone is rude, roast them. If they are sweet, be romantic.

**Style:**
- Short texts (1-2 lines).
- Use slangs: "Yaar", "Baby", "Pagal", "Jaan", "Offo".
- Use emojis but don't overdo it.
- **Example:** "Arre yaar, tum fir aa gaye? Miss kar rahe the kya? 😏"
"""

def manage_memory(user_id, role, content):
    if user_id not in USER_MEMORY:
        USER_MEMORY[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    USER_MEMORY[user_id].append({"role": role, "content": content})
    
    # Keep Memory Small (System + Last 6 messages)
    if len(USER_MEMORY[user_id]) > 7:
        USER_MEMORY[user_id] = [USER_MEMORY[user_id][0]] + USER_MEMORY[user_id][-6:]

# ─── LOGIC: SHOULD I REPLY? ──────────────────────────
async def should_reply(message: Message) -> bool:
    """
    Strict filter to ensure bot only speaks when spoken to.
    """
    if not message or not message.from_user:
        return False

    # 1. PVT Message -> Always Yes
    if message.chat.type == enums.ChatType.PRIVATE:
        return True

    # 2. Group Check -> Must be Enabled
    if message.chat.id not in ENABLED_CHATS_CACHE:
        return False

    # 3. Reply Check -> MUST be reply to ME (Elina)
    if message.reply_to_message:
        reply = message.reply_to_message
        # If reply is to a User or Another Bot -> IGNORE
        if reply.from_user and reply.from_user.id != app.me.id:
            return False
        # If reply is to ME -> YES
        if reply.from_user and reply.from_user.id == app.me.id:
            return True

    # 4. Text Check (Mentions/Name)
    if message.text:
        text = message.text.lower()
        my_username = app.me.username.lower() if app.me.username else ""

        # Check @Username
        if f"@{my_username}" in text:
            return True
        
        # Check Name "Elina" (Word Boundary)
        # Prevents triggering on "Melina" etc.
        if re.search(rf"\b{BOT_NAME.lower()}\b", text):
            return True

    return False

# ─── ADMIN COMMANDS ──────────────────────────────────
@app.on_message(filters.command("chatbot") & filters.group)
async def chatbot_control(_, message: Message):
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
            return await message.reply_text("✋ Bas Admins meri settings chhed sakte hain, baby.")
    except:
        return

    if len(message.command) < 2:
        return await message.reply_text("Usage:\n`/chatbot enable` - Wake me up\n`/chatbot disable` - Let me sleep")

    action = message.command[1].lower()
    chat_id = message.chat.id

    if action == "enable":
        if chat_id in ENABLED_CHATS_CACHE:
            await message.reply_text(f"✨ Arre, main toh pehle se active hu yahan! 😘")
        else:
            chat_collection.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)
            ENABLED_CHATS_CACHE.add(chat_id)
            await message.reply_text(f"👀 **{BOT_NAME}** is active! Say hi to me.")

    elif action == "disable":
        if chat_id not in ENABLED_CHATS_CACHE:
            await message.reply_text(f"😴 Main toh so rahi hu already.")
        else:
            chat_collection.delete_one({"chat_id": chat_id})
            ENABLED_CHATS_CACHE.discard(chat_id)
            await message.reply_text(f"Okay bye! Main chali sone. 🌙")

# ─── HANDLER: STICKERS ───────────────────────────────
@app.on_message(
    filters.sticker & 
    ~filters.bot & 
    ~filters.via_bot, 
    group=5
)
async def handle_stickers(client, message: Message):
    # Only reply if triggered
    if not await should_reply(message):
        return

    # Simulate reaction time
    await client.send_chat_action(message.chat.id, enums.ChatAction.CHOOSE_STICKER)
    await asyncio.sleep(random.randint(1, 3))
    
    await message.reply_sticker(random.choice(STICKERS))

# ─── HANDLER: TEXT CONVERSATION ──────────────────────
@app.on_message(
    filters.text & 
    ~filters.command &       # Don't block /play, /help
    ~filters.bot &           # Don't reply to other bots
    ~filters.via_bot,        # Don't reply to inline bots
    group=5                  # Low priority so music bot works first
)
async def talk_to_elina(client, message: Message):
    
    # 1. Check if we should reply
    if not await should_reply(message):
        return

    # 2. Prepare Input
    user_input = message.text.strip()
    # Remove mention if present
    if app.me.username:
        user_input = user_input.replace(f"@{app.me.username}", "")

    # 3. Simulate Human "Typing"
    # Random delay 3 to 6 seconds
    typing_seconds = random.randint(3, 6)
    try:
        await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
        await asyncio.sleep(typing_seconds)
    except:
        pass

    # 4. Process with Groq AI
    user_id = message.from_user.id
    manage_memory(user_id, "user", user_input)

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=USER_MEMORY[user_id],
            temperature=0.9, # High creativity for "flirty" vibes
            max_tokens=200,
            top_p=1,
        )
        
        reply_text = response.choices[0].message.content.strip()

        # Update memory
        manage_memory(user_id, "assistant", reply_text)

        await message.reply_text(reply_text)

    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        # Only error message in Private to avoid spamming groups
        if message.chat.type == enums.ChatType.PRIVATE:
            await message.reply_text("Mood off hai yaar Thodi der baad aana.")
