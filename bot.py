import os
import asyncio
import logging
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== CONFIGURATION ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== SUPABASE API ==========
async def supabase_get(endpoint):
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        return r.json()

# ========== BOT HANDLERS ==========
async def start(update, context):
    user = update.effective_user
    context.user_data['is_premium'] = False
    
    topics = await supabase_get("topics?select=id,name,is_premium&is_premium=eq.false&limit=20")
    
    keyboard = []
    for t in topics:
        keyboard.append([InlineKeyboardButton(f"📚 {t['name']}", callback_data=f"topic_{t['id']}")])
    
    keyboard.append([InlineKeyboardButton("⭐ UNLOCK PREMIUM - 25 GHS", callback_data="unlock")])
    
    await update.message.reply_text(
        f"🎯 Welcome {user.first_name}!\n\nSelect a topic:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data
    
    if data == "unlock":
        await q.edit_message_text(
            "🔓 Premium: 25 GHS one-time\n\nContact @support to purchase.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        )
    elif data == "back":
        await start(update, context)
    elif data.startswith("topic_"):
        topic_id = data.split("_")[1]
        await start_quiz(update, context, topic_id)
    elif data.startswith("ans_"):
        parts = data.split("_")
        q_idx = int(parts[1])
        a_idx = int(parts[2])
        await check(update, context, q_idx, a_idx)
    elif data == "next":
        context.user_data['idx'] = context.user_data.get('idx', 0) + 1
        await send_q(update, context)

async def start_quiz(update, context, topic_id):
    qs = await supabase_get(f"questions?topic_id=eq.{topic_id}&limit=10")
    if not qs:
        await update.callback_query.edit_message_text("No questions yet.")
        return
    
    context.user_data['questions'] = qs
    context.user_data['idx'] = 0
    context.user_data['score'] = 0
    await send_q(update, context)

async def send_q(update, context):
    qs = context.user_data.get('questions', [])
    idx = context.user_data.get('idx', 0)
    
    if idx >= len(qs):
        await results(update, context)
        return
    
    q = qs[idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"ans_{idx}_{i}")] for i, opt in enumerate(opts)]
    
    await update.callback_query.edit_message_text(
        f"Q{idx+1}/{len(qs)}\n\n{q['question_text']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check(update, context, q_idx, a_idx):
    qs = context.user_data.get('questions', [])
    q = qs[q_idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    correct = (opts[a_idx] == q['correct_answer'])
    
    if correct:
        context.user_data['score'] = context.user_data.get('score', 0) + 1
        msg = f"✅ CORRECT!\n\n{q['correct_answer']}"
    else:
        msg = f"❌ WRONG!\n\nCorrect: {q['correct_answer']}"
    
    if q.get('explanation'):
        msg += f"\n\n📖 {q['explanation']}"
    
    await update.callback_query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Next", callback_data="next")]])
    )

async def results(update, context):
    score = context.user_data.get('score', 0)
    total = len(context.user_data.get('questions', []))
    pct = (score/total)*100 if total else 0
    
    await update.callback_query.edit_message_text(
        f"📊 QUIZ COMPLETE!\n\nScore: {score}/{total} ({pct:.0f}%)\n\n{ '🏆 GREAT!' if pct>=70 else '📚 Keep practicing!' }",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="back")]])
    )

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))
    logger.info("Bot started!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
