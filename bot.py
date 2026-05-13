import os
import asyncio
import logging
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes
)

# ========== CONFIGURATION ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8681173639:AAH8oHPK0UvEjZavAEa2THc3dNMeVCVAiPo')
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://uiddbckrjparmtbdegzx.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVpZGRiY2tyanBhcm10YmRlZ3p4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2NjM1NTgsImV4cCI6MjA5NDIzOTU1OH0.C12kI-0ZZlJ9k264TFd4GSlZMr5Oz2ebll8gCGdD4kA')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== SUPABASE API HELPER ==========
async def supabase_get(endpoint: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        return response.json()

async def supabase_insert(endpoint: str, data: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json=data
        )
        return response.status_code

# ========== DATABASE FUNCTIONS ==========
async def get_or_create_user(user_id: int, username: str, first_name: str):
    users = await supabase_get(f"users?id=eq.{user_id}&select=*")
    
    if not users:
        await supabase_insert("users", {
            "id": user_id,
            "username": username or "",
            "first_name": first_name or "",
            "is_premium": False,
            "total_questions_answered": 0,
            "total_correct": 0
        })
        return {"id": user_id, "is_premium": False}
    
    return users[0]

async def get_topics(is_premium: bool = False):
    if is_premium:
        topics = await supabase_get("topics?select=id,name,is_premium&order=display_order.asc")
    else:
        topics = await supabase_get("topics?select=id,name,is_premium&is_premium=eq.false&order=display_order.asc&limit=20")
    return topics

async def get_questions_by_topic(topic_id: int, limit: int = 10):
    questions = await supabase_get(
        f"questions?select=id,question_text,option_a,option_b,option_c,correct_answer,explanation&topic_id=eq.{topic_id}&order=random()&limit={limit}"
    )
    return questions

async def update_user_stats(user_id: int, is_correct: bool):
    users = await supabase_get(f"users?id=eq.{user_id}&select=total_questions_answered,total_correct")
    
    if users:
        current = users[0]
        new_answered = current.get('total_questions_answered', 0) + 1
        new_correct = current.get('total_correct', 0) + (1 if is_correct else 0)
        
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "total_questions_answered": new_answered,
                    "total_correct": new_correct,
                    "updated_at": datetime.now().isoformat()
                }
            )

# ========== BOT HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    db_user = await get_or_create_user(user.id, user.username or "", user.first_name or "")
    context.user_data['is_premium'] = db_user.get('is_premium', False)
    
    topics = await get_topics(context.user_data['is_premium'])
    
    # Build keyboard in 2 columns for better layout
    keyboard = []
    row = []
    for i, topic in enumerate(topics):
        lock = "🔓 " if context.user_data['is_premium'] or not topic.get('is_premium', False) else "🔒 "
        row.append(InlineKeyboardButton(f"{lock}{topic['name']}", callback_data=f"topic_{topic['id']}"))
        if len(row) == 2 or i == len(topics) - 1:
            keyboard.append(row)
            row = []
    
    if not context.user_data['is_premium']:
        keyboard.append([InlineKeyboardButton("⭐ UNLOCK PREMIUM - 25 GHS", callback_data="unlock_premium")])
    
    keyboard.append([InlineKeyboardButton("ℹ️ Help & Info", callback_data="help")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🚗 *DVTheory Driving Test Bot*\n\n"
        f"Hello {user.first_name}! 👋\n\n"
        f"📚 Select a topic below to start practicing:\n"
        f"💰 Premium: {'✅ ACTIVE' if context.user_data['is_premium'] else '❌ NOT ACTIVE'}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "unlock_premium":
        await show_premium_options(update, context)
    elif data == "back_to_topics":
        await show_topics_menu(update, context)
    elif data == "help":
        await show_help(update, context)
    elif data.startswith("topic_"):
        topic_id = int(data.split("_")[1])
        await start_quiz(update, context, topic_id)
    elif data.startswith("answer_"):
        parts = data.split("_")
        q_idx = int(parts[1])
        a_idx = int(parts[2])
        await check_answer(update, context, q_idx, a_idx)
    elif data == "next_question":
        await next_question(update, context)

async def show_topics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to topics menu"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    db_user = await get_or_create_user(user_id, "", "")
    context.user_data['is_premium'] = db_user.get('is_premium', False)
    
    topics = await get_topics(context.user_data['is_premium'])
    
    keyboard = []
    row = []
    for i, topic in enumerate(topics):
        lock = "🔓 " if context.user_data['is_premium'] or not topic.get('is_premium', False) else "🔒 "
        row.append(InlineKeyboardButton(f"{lock}{topic['name']}", callback_data=f"topic_{topic['id']}"))
        if len(row) == 2 or i == len(topics) - 1:
            keyboard.append(row)
            row = []
    
    if not context.user_data['is_premium']:
        keyboard.append([InlineKeyboardButton("⭐ UNLOCK PREMIUM - 25 GHS", callback_data="unlock_premium")])
    
    keyboard.append([InlineKeyboardButton("ℹ️ Help & Info", callback_data="help")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🏠 *Main Menu*\n\nSelect a topic to start practicing:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    query = update.callback_query
    
    help_text = (
        f"📖 *How to Use DVTheory Bot*\n\n"
        f"1️⃣ Select a topic from the menu\n"
        f"2️⃣ Answer 10 random questions\n"
        f"3️⃣ Get instant feedback\n"
        f"4️⃣ Track your progress\n\n"
        f"💰 *Premium Access:* 25 GHS one-time\n"
        f"• 70+ topics\n"
        f"• 910+ questions\n"
        f"• Detailed explanations\n\n"
        f"📧 *Support:* @nanaosae\n\n"
        f"Type /start to return to menu"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_topics")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_premium_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    text = (
        "🔓 *UNLOCK PREMIUM ACCESS* 🔓\n\n"
        "Get lifetime access to ALL topics and 910+ questions!\n\n"
        "✨ *Premium Benefits:*\n"
        "• All 70+ topics unlocked\n"
        "• 910+ exam-style questions\n"
        "• Detailed explanations\n\n"
        "💰 *Price: 25 GHS (One-time payment)*\n\n"
        "📧 Contact @nanaosae to upgrade!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Topics", callback_data="back_to_topics")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    query = update.callback_query
    
    topics = await get_topics(True)
    topic = next((t for t in topics if t['id'] == topic_id), None)
    
    if not topic:
        await query.edit_message_text("Topic not found.")
        return
    
    if topic.get('is_premium', False) and not context.user_data.get('is_premium'):
        await query.edit_message_text(
            f"🔒 *{topic['name']}* is a premium topic!\n\n"
            f"Unlock all topics for only 25 GHS!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐ Unlock Premium", callback_data="unlock_premium"),
                InlineKeyboardButton("🔙 Back", callback_data="back_to_topics")
            ]]),
            parse_mode='Markdown'
        )
        return
    
    questions = await get_questions_by_topic(topic_id)
    
    if not questions:
        await query.edit_message_text("No questions available for this topic yet.")
        return
    
    context.user_data['current_topic_id'] = topic_id
    context.user_data['current_topic_name'] = topic['name']
    context.user_data['questions'] = questions
    context.user_data['current_index'] = 0
    context.user_data['score'] = 0
    
    await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    questions = context.user_data.get('questions', [])
    idx = context.user_data.get('current_index', 0)
    score = context.user_data.get('score', 0)
    topic = context.user_data.get('current_topic_name', 'Quiz')
    
    if idx >= len(questions):
        await show_results(update, context)
        return
    
    q = questions[idx]
    
    keyboard = []
    options = [q['option_a'], q['option_b'], q['option_c']]
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{chr(65+i)}. {opt[:60]}", callback_data=f"answer_{idx}_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"📚 *Topic:* {topic}\n"
        f"📊 *Progress:* {idx + 1}/{len(questions)}\n"
        f"⭐ *Score:* {score}\n\n"
        f"❓ *Question {idx + 1}:*\n{q['question_text']}"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, q_idx: int, a_idx: int):
    query = update.callback_query
    questions = context.user_data.get('questions', [])
    user_id = update.effective_user.id
    
    if q_idx >= len(questions):
        return
    
    q = questions[q_idx]
    options = [q['option_a'], q['option_b'], q['option_c']]
    selected = options[a_idx]
    is_correct = (selected == q['correct_answer'])
    
    await update_user_stats(user_id, is_correct)
    
    if is_correct:
        context.user_data['score'] = context.user_data.get('score', 0) + 1
        feedback = f"✅ *CORRECT!* 🎉\n\n{q['correct_answer']}"
    else:
        feedback = f"❌ *WRONG!*\n\n💡 Correct answer: {q['correct_answer']}"
    
    if q.get('explanation'):
        feedback += f"\n\n📖 *Explanation:* {q['explanation']}"
    
    keyboard = [[InlineKeyboardButton("➡️ Next Question", callback_data="next_question")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(feedback, reply_markup=reply_markup, parse_mode='Markdown')

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_index'] = context.user_data.get('current_index', 0) + 1
    await send_question(update, context)

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    questions = context.user_data.get('questions', [])
    score = context.user_data.get('score', 0)
    total = len(questions)
    percentage = (score / total) * 100 if total > 0 else 0
    
    if percentage >= 80:
        rating = "🏆 *EXCELLENT!* You're ready for the test!"
    elif percentage >= 60:
        rating = "👍 *GOOD!* Keep practicing!"
    else:
        rating = "📚 *NEEDS PRACTICE!* Review and try again!"
    
    text = (
        f"📊 *Quiz Complete!*\n\n"
        f"⭐ *Score:* {score}/{total} ({percentage:.0f}%)\n\n"
        f"{rating}\n\n"
        f"What would you like to do next?"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Practice Again", callback_data=f"topic_{context.user_data['current_topic_id']}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_topics")]
    ]
    
    if not context.user_data.get('is_premium'):
        keyboard.append([InlineKeyboardButton("⭐ UNLOCK ALL TOPICS - 25 GHS", callback_data="unlock_premium")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ========== MAIN ==========
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("DVTheory Bot is running...")
    
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
