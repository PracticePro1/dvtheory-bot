import os
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# Check for missing credentials immediately
if not all([TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Missing environment variables for Telegram or Supabase.")

# Standard logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- API CLIENT ---
# Creating a global client is much faster than opening a new one every request
http_client = httpx.AsyncClient(
    base_url=f"{SUPABASE_URL}/rest/v1/",
    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
)

async def supabase_get(endpoint: str):
    """Generic GET request to Supabase with error handling."""
    try:
        r = await http_client.get(endpoint)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Supabase Error ({endpoint}): {e}")
        return None

# --- BOT LOGIC ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: Lists free topics and the upgrade button."""
    topics = await supabase_get("topics?select=id,name&is_premium=eq.false&limit=20")
    
    if topics is None:
        text = "⚠️ Service temporarily unavailable. Please try again later."
        keyboard = []
    else:
        text = "📚 *DVTheory Study Center*\n\nChoose a free topic to start practicing, or upgrade for full access:"
        keyboard = [[InlineKeyboardButton(t['name'], callback_data=f"topic_{t['id']}")] for t in topics]
        keyboard.append([InlineKeyboardButton("⭐ Upgrade to Premium", callback_data="upgrade")])

    # Handle both /start command and "back" button
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main router for button clicks."""
    query = update.callback_query
    data = query.data
    await query.answer() # Prevents button 'loading' spinner

    if data == "upgrade":
        text = "💎 *Premium Access*\n\n✅ Unlock all 50+ topics\n✅ Detailed explanations\n✅ No limits\n\nPrice: *25 GHS* (One-time)\nContact: @nanaosae"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]]))
    
    elif data == "back":
        await start(update, context)
    
    elif data.startswith("topic_"):
        topic_id = data.split("_")[1]
        await start_quiz(query, context, topic_id)
    
    elif data.startswith("ans_"):
        # Format: ans_questionIndex_choiceIndex
        _, q_idx, a_idx = data.split("_")
        await check_answer(query, context, int(q_idx), int(a_idx))
    
    elif data == "next":
        context.user_data['idx'] = context.user_data.get('idx', 0) + 1
        await send_question(query, context)

async def start_quiz(query, context, topic_id):
    """Fetches questions and resets user progress."""
    qs = await supabase_get(f"questions?topic_id=eq.{topic_id}&limit=10")
    
    if not qs:
        await query.edit_message_text("❌ No questions found for this topic.", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]]))
        return
        
    context.user_data.update({
        'questions': qs,
        'idx': 0,
        'score': 0
    })
    await send_question(query, context)

async def send_question(query, context):
    """Displays the current question and options."""
    qs = context.user_data.get('questions', [])
    idx = context.user_data.get('idx', 0)

    if idx >= len(qs):
        await show_results(query, context)
        return

    q = qs[idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    
    # Filter out empty options
    keyboard = [[InlineKeyboardButton(opt, callback_data=f"ans_{idx}_{i}")] 
                for i, opt in enumerate(opts) if opt]

    await query.edit_message_text(
        f"📝 *Topic Practice* ({idx+1}/{len(qs)})\n\n{q['question_text']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_answer(query, context, q_idx, a_idx):
    """Validates choice and shows feedback."""
    # Safety: ensure questions exist in user_data
    if 'questions' not in context.user_data:
        await start(query, context)
        return

    q = context.user_data['questions'][q_idx]
    opts = [q['option_a'], q['option_b'], q['option_c']]
    selected = opts[a_idx]
    is_correct = (selected == q['correct_answer'])

    if is_correct:
        context.user_data['score'] += 1
        header = "✅ *Correct!*"
    else:
        header = f"❌ *Wrong!*\nYour choice: {selected}"

    msg = f"{header}\n\n🎯 *Answer:* {q['correct_answer']}"
    
    if q.get('explanation'):
        msg += f"\n\n📖 {q['explanation']}"

    await query.edit_message_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next Question ➡️", callback_data="next")]])
    )

async def show_results(query, context):
    """Final score screen."""
    score = context.user_data.get('score', 0)
    total = len(context.user_data.get('questions', []))
    pct = int(score/total*100) if total else 0
    
    result_text = "🎉" if pct >= 70 else "👨‍🏫"
    text = (f"🏁 *Quiz Complete!*\n\n"
            f"Score: `{score}/{total}` ({pct}%)\n\n"
            f"{result_text} {'Great job, you are ready!' if pct>=70 else 'Keep practicing to improve!'}")
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Try Another Topic", callback_data="back")]])
    )

def main():
    """Start the bot."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("Bot started and polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
