import os
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

logging.basicConfig(level=logging.INFO)

async def supabase_get(endpoint):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        return r.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = await supabase_get("topics?select=id,name&is_premium=eq.false&limit=20")
    keyboard = [[InlineKeyboardButton(t['name'], callback_data=f"topic_{t['id']}")] for t in topics]
    keyboard.append([InlineKeyboardButton("⭐ Upgrade", callback_data="upgrade")])
    await update.message.reply_text("Welcome! Choose a topic:", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    
    if data == "upgrade":
        await q.edit_message_text("Premium: 25 GHS one-time. Contact @nanaosae")
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
    qs = await supabase_get(f"questions?topic_id=eq.{topic_id}&limit=10")
    if not qs:
        await update.callback_query.edit_message_text("No questions")
        return
    context.user_data['questions'] = qs
    context.user_data['idx'] = 0
    context.user_data['score'] = 0
    await send_question(update, context)

async def send_question(update, context):
    qs = context.user_data.get('questions', [])
    idx = context.user_data.get('idx', 0)
    if idx >= len(qs):
        await show_results(update, context)
        return
    q = qs[idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"ans_{idx}_{i}")] for i, opt in enumerate(opts)]
    await update.callback_query.edit_message_text(
        f"Q{idx+1}/{len(qs)}\n\n{q['question_text']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_answer(update, context, q_idx, a_idx):
    q = context.user_data['questions'][q_idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    is_correct = (opts[a_idx] == q['correct_answer'])
    if is_correct:
        context.user_data['score'] += 1
        msg = f"✅ Correct!\n\n{q['correct_answer']}"
    else:
        msg = f"❌ Wrong!\n\nCorrect: {q['correct_answer']}"
    if q.get('explanation'):
        msg += f"\n\n📖 {q['explanation']}"
    await update.callback_query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next", callback_data="next")]])
    )

async def show_results(update, context):
    score = context.user_data.get('score', 0)
    total = len(context.user_data.get('questions', []))
    pct = int(score/total*100) if total else 0
    await update.callback_query.edit_message_text(
        f"Quiz Complete!\n\nScore: {score}/{total} ({pct}%)\n\n{'Great job!' if pct>=70 else 'Keep practicing!'}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]])
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
