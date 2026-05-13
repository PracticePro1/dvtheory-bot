import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from functools import wraps

import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)
from tenacity import retry, stop_after_attempt, wait_exponential

# ========== CONFIGURATION ==========
# Get from environment variables (set in Railway)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')

# For development - remove these when deploying to Railway
if not TELEGRAM_TOKEN:
    TELEGRAM_TOKEN = "8681173639:AAH8oHPK0UvEjZavAEa2THc3dNMeVCVAiPo"
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:DVtheorybot2026%40@db.uiddbckrjparmtbdegzx.supabase.co:5432/postgres"

# ========== DATABASE CONNECTION ==========
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    logging.info("Database connected")

async def get_db():
    return await db_pool.acquire()

async def return_db(conn):
    await db_pool.release(conn)

# ========== BOT HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - shows topics"""
    user = update.effective_user
    
    # Create or get user
    conn = await get_db()
    try:
        await conn.execute("""
            INSERT INTO users (id, username, first_name, is_premium)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
        """, user.id, user.username or "", user.first_name or "", False)
        
        # Check if user is premium
        is_premium = await conn.fetchval("SELECT is_premium FROM users WHERE id = $1", user.id)
        context.user_data['is_premium'] = is_premium
        
        # Get topics
        if is_premium:
            topics = await conn.fetch("SELECT id, name, is_premium, icon FROM topics ORDER BY display_order")
        else:
            topics = await conn.fetch("SELECT id, name, is_premium, icon FROM topics WHERE is_premium = false ORDER BY display_order LIMIT 20")
        
    finally:
        await return_db(conn)
    
    # Build keyboard
    keyboard = []
    for topic in topics:
        lock = "🔓 " if is_premium or not topic['is_premium'] else "🔒 "
        keyboard.append([
            InlineKeyboardButton(f"{lock}{topic['name']}", callback_data=f"topic_{topic['id']}")
        ])
    
    if not is_premium:
        keyboard.append([
            InlineKeyboardButton("⭐ UNLOCK PREMIUM - 25 GHS", callback_data="unlock_premium")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎯 *Welcome to DVTheory!* 🚗\n\n"
        f"Hello {user.first_name}! Pass your driving test with confidence.\n\n"
        f"📚 Select a topic below to start:\n"
        f"💰 Premium: {'✅ ACTIVE' if is_premium else '❌ NOT ACTIVE'}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "unlock_premium":
        await show_premium_options(update, context)
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
    elif data == "back_to_topics":
        await start(update, context)

async def show_premium_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show premium purchase options"""
    query = update.callback_query
    
    text = (
        "🔓 *UNLOCK PREMIUM ACCESS* 🔓\n\n"
        "Get lifetime access to ALL 50+ topics and 910+ questions!\n\n"
        "✨ *Premium Benefits:*\n"
        "• All 50+ topics unlocked\n"
        "• 910+ exam-style questions\n"
        "• Detailed explanations\n"
        "• No ads\n\n"
        "💰 *Price: 25 GHS (One-time payment)*\n\n"
        "Click below to purchase:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Pay with Mobile Money/Card - 25 GHS", callback_data="purchase_premium")],
        [InlineKeyboardButton("🔙 Back to Topics", callback_data="back_to_topics")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_id: int):
    """Start a quiz for selected topic"""
    query = update.callback_query
    
    conn = await get_db()
    try:
        # Get topic name
        topic = await conn.fetchrow("SELECT name, is_premium FROM topics WHERE id = $1", topic_id)
        
        if topic['is_premium'] and not context.user_data.get('is_premium'):
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
        
        # Get questions
        questions = await conn.fetch("""
            SELECT id, question_text, option_a, option_b, option_c, correct_answer, explanation
            FROM questions
            WHERE topic_id = $1
            ORDER BY RANDOM()
            LIMIT 10
        """, topic_id)
        
        if not questions:
            await query.edit_message_text("No questions available for this topic yet.")
            return
        
        # Store quiz state
        context.user_data['current_topic_id'] = topic_id
        context.user_data['current_topic_name'] = topic['name']
        context.user_data['questions'] = [dict(q) for q in questions]
        context.user_data['current_index'] = 0
        context.user_data['score'] = 0
        
        await send_question(update, context)
        
    finally:
        await return_db(conn)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send current question"""
    questions = context.user_data.get('questions', [])
    idx = context.user_data.get('current_index', 0)
    score = context.user_data.get('score', 0)
    topic = context.user_data.get('current_topic_name', 'Quiz')
    
    if idx >= len(questions):
        await show_results(update, context)
        return
    
    q = questions[idx]
    
    keyboard = []
    for i, opt in enumerate([q['option_a'], q['option_b'], q['option_c']]):
        keyboard.append([InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"answer_{idx}_{i}")])
    
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
    """Check answer and show result"""
    query = update.callback_query
    questions = context.user_data.get('questions', [])
    
    if q_idx >= len(questions):
        return
    
    q = questions[q_idx]
    options = [q['option_a'], q['option_b'], q['option_c']]
    selected = options[a_idx]
    is_correct = (selected == q['correct_answer'])
    
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
    """Move to next question"""
    context.user_data['current_index'] = context.user_data.get('current_index', 0) + 1
    await send_question(update, context)

async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quiz results"""
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
        [InlineKeyboardButton("🏠 Back to Topics", callback_data="back_to_topics")]
    ]
    
    if not context.user_data.get('is_premium'):
        keyboard.append([InlineKeyboardButton("⭐ UNLOCK ALL TOPICS - 25 GHS", callback_data="unlock_premium")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ========== MAIN ==========
async def main():
    logging.basicConfig(level=logging.INFO)
    
    await init_db()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logging.info("Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())