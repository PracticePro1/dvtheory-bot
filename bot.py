import os
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def supabase_get(endpoint):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        return r.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = await supabase_get("topics?select=id,name&is_premium=eq.false&limit=10")
    keyboard = []
    for t in topics:
        keyboard.append([InlineKeyboardButton(t['name'], callback_data=f"topic_{t['id']}")])
    keyboard.append([InlineKeyboardButton("⭐ Upgrade to Premium", callback_data="upgrade")])
    await update.message.reply_text(
        "🚗 Welcome to DVTheory!\n\nChoose a topic to start practicing:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "upgrade":
        await query.edit_message_text(
            "🔓 PREMIUM ACCESS - 25 GHS\n\nContact @Support to purchase lifetime access to all 910+ questions!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        )
    elif data == "back":
        await start(update, context)
    elif data.startswith("topic_"):
        topic_id = data.split("_")[1]
        await start_quiz(update, context, topic_id)
    elif data.startswith("ans_"):
        parts = data.split("_")
        await check_answer(update, context, int(parts[1]), int(parts[2]))
    elif data == "next":
        context.user_data['idx'] = context.user_data.get('idx', 0) + 1
        await send_question(update, context)

async def start_quiz(update, context, topic_id):
    questions = await supabase_get(f"questions?topic_id=eq.{topic_id}&limit=10")
    if not questions:
        await update.callback_query.edit_message_text("No questions available for this topic.")
        return
    context.user_data['questions'] = questions
    context.user_data['idx'] = 0
    context.user_data['score'] = 0
    await send_question(update, context)

async def send_question(update, context):
    questions = context.user_data.get('questions', [])
    idx = context.user_data.get('idx', 0)
    if idx >= len(questions):
        await show_results(update, context)
        return
    q = questions[idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    keyboard = []
    for i, opt in enumerate(opts):
        keyboard.append([InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"ans_{idx}_{i}")])
    await update.callback_query.edit_message_text(
        f"📚 Question {idx+1}/{len(questions)}\n\n{q['question_text']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_answer(update, context, q_idx, a_idx):
    q = context.user_data['questions'][q_idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    is_correct = (opts[a_idx] == q['correct_answer'])
    if is_correct:
        context.user_data['score'] = context.user_data.get('score', 0) + 1
        msg = f"✅ CORRECT!\n\nAnswer: {q['correct_answer']}"
    else:
        msg = f"❌ WRONG!\n\nCorrect answer: {q['correct_answer']}"
    if q.get('explanation'):
        msg += f"\n\n📖 {q['explanation']}"
    await update.callback_query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Next", callback_data="next")]])
    )

async def show_results(update, context):
    score = context.user_data.get('score', 0)
    total = len(context.user_data.get('questions', []))
    pct = int(score/total*100) if total > 0 else 0
    rating = "🏆 EXCELLENT!" if pct >= 80 else "👍 GOOD!" if pct >= 60 else "📚 NEEDS PRACTICE"
    await update.callback_query.edit_message_text(
        f"📊 QUIZ COMPLETE!\n\nScore: {score}/{total} ({pct}%)\n\n{rating}\n\nKeep practicing to improve!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="back")]])
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))
    logger.info("DVTheory Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
