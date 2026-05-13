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
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{endpoint}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        return r.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu"""
    user = update.effective_user
    
    # Get free topics only (for main menu)
    topics = await supabase_get("topics?select=id,name,is_premium&is_premium=eq.false&order=display_order.asc&limit=20")
    
    keyboard = []
    # Show topics in rows of 2
    row = []
    for i, t in enumerate(topics):
        row.append(InlineKeyboardButton(f"📚 {t['name']}", callback_data=f"topic_{t['id']}"))
        if len(row) == 2 or i == len(topics) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("⭐ UPGRADE TO PREMIUM", callback_data="upgrade")])
    keyboard.append([InlineKeyboardButton("📊 MY PROGRESS", callback_data="progress")])
    keyboard.append([InlineKeyboardButton("ℹ️ HELP", callback_data="help")])
    
    await update.message.reply_text(
        f"🚗 *DVTheory Driving Test Bot*\n\n"
        f"Welcome {user.first_name}! 👋\n\n"
        f"📚 *FREE Topics:* {len(topics)}\n"
        f"⭐ *Premium Topics:* 70+\n"
        f"📝 *Total Questions:* 910+\n\n"
        f"Select a topic to start practicing:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    query = update.callback_query
    await query.answer()
    
    topics = await supabase_get("topics?select=id,name,is_premium&is_premium=eq.false&order=display_order.asc&limit=20")
    
    keyboard = []
    row = []
    for i, t in enumerate(topics):
        row.append(InlineKeyboardButton(f"📚 {t['name']}", callback_data=f"topic_{t['id']}"))
        if len(row) == 2 or i == len(topics) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("⭐ UPGRADE TO PREMIUM", callback_data="upgrade")])
    keyboard.append([InlineKeyboardButton("📊 MY PROGRESS", callback_data="progress")])
    keyboard.append([InlineKeyboardButton("ℹ️ HELP", callback_data="help")])
    
    await query.edit_message_text(
        f"🏠 *Main Menu*\n\n"
        f"Select a topic to start practicing:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show premium upgrade options"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💰 BUY PREMIUM - 25 GHS", callback_data="buy_premium")],
        [InlineKeyboardButton("🔙 BACK TO MENU", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        f"⭐ *Upgrade to Premium* ⭐\n\n"
        f"✨ *Benefits:*\n"
        f"• 70+ specialized topics\n"
        f"• 910+ exam-style questions\n"
        f"• Detailed explanations\n"
        f"• Track your progress\n"
        f"• No ads\n\n"
        f"💰 *Price:* 25 GHS (One-time payment)\n\n"
        f"Click below to upgrade:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user progress"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    try:
        # Get user stats
        users = await supabase_get(f"users?id=eq.{user_id}&select=total_questions_answered,total_correct,is_premium")
        
        if users:
            user = users[0]
            total = user.get('total_questions_answered', 0)
            correct = user.get('total_correct', 0)
            accuracy = (correct / total * 100) if total > 0 else 0
            is_premium = user.get('is_premium', False)
        else:
            total = 0
            correct = 0
            accuracy = 0
            is_premium = False
        
        keyboard = [
            [InlineKeyboardButton("🏠 MAIN MENU", callback_data="menu")],
            [InlineKeyboardButton("⭐ UPGRADE", callback_data="upgrade")] if not is_premium else []
        ]
        # Remove empty rows
        keyboard = [row for row in keyboard if row]
        
        await query.edit_message_text(
            f"📊 *Your Progress* 📊\n\n"
            f"✅ Questions answered: {total}\n"
            f"⭐ Correct answers: {correct}\n"
            f"📈 Accuracy: {accuracy:.1f}%\n"
            f"🔓 Premium: {'✅ ACTIVE' if is_premium else '❌ NOT ACTIVE'}\n\n"
            f"Keep practicing to improve your score! 🚀",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Progress error: {e}")
        await query.edit_message_text(
            "📊 *Your Progress*\n\nNo data yet. Complete some quizzes to see your stats!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN MENU", callback_data="menu")]]),
            parse_mode='Markdown'
        )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🏠 MAIN MENU", callback_data="menu")]]
    
    await query.edit_message_text(
        f"ℹ️ *Help & Information* ℹ️\n\n"
        f"*How to use:*\n"
        f"1. Select a topic from the menu\n"
        f"2. Answer 10 random questions\n"
        f"3. Get instant feedback\n"
        f"4. Track your progress\n\n"
        f"*Commands:*\n"
        f"/start - Main menu\n"
        f"/menu - Return to menu\n\n"
        f"*Premium Access:*\n"
        f"• 70+ topics\n"
        f"• 910+ questions\n"
        f"• 25 GHS one-time\n\n"
        f"📧 Support: @nanaosae",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    """Start a quiz for selected topic"""
    query = update.callback_query
    await query.answer()
    
    # Get topic details
    topics = await supabase_get(f"topics?id=eq.{topic_id}&select=name,is_premium")
    if not topics:
        await query.edit_message_text("Topic not found.")
        return
    
    topic = topics[0]
    
    # Check premium
    if topic.get('is_premium'):
        users = await supabase_get(f"users?id=eq.{update.effective_user.id}&select=is_premium")
        is_premium = users[0].get('is_premium', False) if users else False
        if not is_premium:
            await query.edit_message_text(
                f"🔒 *{topic['name']}* is a premium topic!\n\n"
                f"Upgrade to Premium for only 25 GHS to unlock all 70+ topics and 910+ questions!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⭐ UPGRADE NOW", callback_data="upgrade")],
                    [InlineKeyboardButton("🔙 BACK TO MENU", callback_data="menu")]
                ]),
                parse_mode='Markdown'
            )
            return
    
    # Get questions
    questions = await supabase_get(f"questions?topic_id=eq.{topic_id}&limit=10&order=random()")
    
    if not questions:
        await query.edit_message_text(
            "No questions available for this topic yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="menu")]])
        )
        return
    
    # Store quiz state
    context.user_data['quiz'] = {
        'topic_id': topic_id,
        'topic_name': topic['name'],
        'questions': questions,
        'current': 0,
        'score': 0,
        'total': len(questions)
    }
    
    await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send current question"""
    quiz = context.user_data.get('quiz')
    if not quiz:
        await menu(update, context)
        return
    
    idx = quiz['current']
    questions = quiz['questions']
    
    if idx >= len(questions):
        await show_results(update, context)
        return
    
    q = questions[idx]
    
    keyboard = [
        [InlineKeyboardButton(f"A. {q['option_a'][:60]}", callback_data=f"ans_{idx}_0")],
        [InlineKeyboardButton(f"B. {q['option_b'][:60]}", callback_data=f"ans_{idx}_1")],
        [InlineKeyboardButton(f"C. {q['option_c'][:60]}", callback_data=f"ans_{idx}_2")]
    ]
    
    text = f"📚 *{quiz['topic_name']}*\n"
    text += f"📊 Q{idx + 1}/{quiz['total']} | ⭐ Score: {quiz['score']}\n\n"
    text += f"❓ *{q['question_text']}*"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, q_idx: int, a_idx: int):
    """Check answer and show result"""
    query = update.callback_query
    await query.answer()
    
    quiz = context.user_data.get('quiz')
    if not quiz or q_idx != quiz['current']:
        return
    
    q = quiz['questions'][q_idx]
    options = [q['option_a'], q['option_b'], q['option_c']]
    selected = options[a_idx]
    is_correct = (selected == q['correct_answer'])
    
    if is_correct:
        quiz['score'] += 1
        feedback = f"✅ *CORRECT!* 🎉\n\n{q['correct_answer']}"
    else:
        feedback = f"❌ *WRONG!*\n\n💡 Correct answer: {q['correct_answer']}"
    
    if q.get('explanation'):
        feedback += f"\n\n📖 *Explanation:* {q['explanation']}"
    
    # Update user stats in background
    user_id = update.effective_user.id
    try:
        users = await supabase_get(f"users?id=eq.{user_id}&select=total_questions_answered,total_correct")
        if users:
            current = users[0]
            new_answered = current.get('total_questions_answered', 0) + 1
            new_correct = current.get('total_correct', 0) + (1 if is_correct else 0)
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                    json={"total_questions_answered": new_answered, "total_correct": new_correct}
                )
    except:
        pass
    
    keyboard = [[InlineKeyboardButton("➡️ NEXT QUESTION", callback_data="next")]]
    
    await query.edit_message_text(
        feedback,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    quiz['current'] += 1

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Move to next question"""
    query = update.callback_query
    await query.answer()
    await send_question(update, context)

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quiz results"""
    query = update.callback_query
    quiz = context.user_data.get('quiz')
    
    if not quiz:
        await menu(update, context)
        return
    
    score = quiz['score']
    total = quiz['total']
    percentage = (score / total) * 100 if total > 0 else 0
    
    if percentage >= 80:
        rating = "🏆 *EXCELLENT!* You're ready!"
    elif percentage >= 60:
        rating = "👍 *GOOD!* Keep practicing!"
    else:
        rating = "📚 *NEED PRACTICE!* Try again!"
    
    text = f"📊 *Quiz Complete!*\n\n"
    text += f"⭐ Score: {score}/{total} ({percentage:.0f}%)\n\n"
    text += f"{rating}\n\n"
    text += f"What would you like to do next?"
    
    keyboard = [
        [InlineKeyboardButton("🔄 PRACTICE AGAIN", callback_data=f"topic_{quiz['topic_id']}")],
        [InlineKeyboardButton("🏠 MAIN MENU", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Clear quiz from context
    context.user_data['quiz'] = None

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle premium purchase"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"💰 *Purchase Premium - 25 GHS* 💰\n\n"
        f"To upgrade to Premium, please contact:\n"
        f"📧 @nanaosae\n\n"
        f"Or send mobile money to:\n"
        f"📱 [Your Mobile Money Number]\n\n"
        f"After payment, you'll receive a premium code to activate.\n\n"
        f"Type /menu to go back.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MENU", callback_data="menu")]])
    )

# ========== MAIN ==========
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("DVTheory Bot is running...")
    await app.run_polling()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route all callbacks"""
    query = update.callback_query
    data = query.data
    
    if data == "menu":
        await menu(update, context)
    elif data == "upgrade":
        await show_premium(update, context)
    elif data == "progress":
        await show_progress(update, context)
    elif data == "help":
        await show_help(update, context)
    elif data == "buy_premium":
        await buy_premium(update, context)
    elif data.startswith("topic_"):
        topic_id = int(data.split("_")[1])
        await start_quiz(update, context, topic_id)
    elif data.startswith("ans_"):
        parts = data.split("_")
        await check_answer(update, context, int(parts[1]), int(parts[2]))
    elif data == "next":
        await next_question(update, context)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
