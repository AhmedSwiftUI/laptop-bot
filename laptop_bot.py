import os
import json
import logging
import pandas as pd
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import mm

# إعدادات
TOKEN = os.getenv("BOT_TOKEN")
CSV_PATH = "Cleaned_Laptop_Data_Final_Version.csv"
IMAGES_FOLDER = "Toplaps_bot_images"
USERS_FILE = "users.json"
ADMIN_ID = 890094476  # 👈 ضع رقم حسابك هنا

DONATION_LINK = "coff.ee/toplap"
CONTACT_LINK = "https://t.me/Ahmed0ksa"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}
purposes = {
    "🎮 الألعاب": "Gaming",
    "🎨 التصميم": "Design",
    "💻 البرمجة والذكاء الاصطناعي": "Programming and AI",
    "📚 الدراسة": "Studying"
}

# تحميل البيانات
df = pd.read_csv(CSV_PATH)
df["Average Price (SAR)"] = pd.to_numeric(df["Average Price (SAR)"], errors="coerce")
df = df.dropna(subset=["Average Price (SAR)"])

# تحميل المستخدمين من الملف
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

users = load_users()

# الواجهات
def main_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 ابدأ من جديد", callback_data="start")],
        [InlineKeyboardButton("💵 دعم المشروع", callback_data="donate")],
        [InlineKeyboardButton("💡 عن توبلاب", callback_data="about")],
        [InlineKeyboardButton("❤️ تواصل معي", callback_data="contact")]
    ])

def purpose_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(k, callback_data=k)] for k in purposes])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_state.pop(cid, None)
    if cid not in users:
        users.add(cid)
        save_users(users)
    send = update.message.reply_text if update.message else update.callback_query.message.reply_text
    await send("👇 حدد غرض استخدامك من اللابتوب:", reply_markup=purpose_keyboard())

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💡 توبلاب هو مساعد ذكي يساعدك تختار أفضل لابتوب يناسب ميزانيتك واستخدامك، سواء كنت طالب، مصمم، مبرمج أو لاعب.\n\n"
        "🚀 الترشيحات مبنية على تحليل بيانات محدثة من مواقع تقنية موثوقة، نتائج اختبارات الأداء (Benchmark)، تقييمات المستخدمين، وخبرة تقنية.\n\n"
        "🎯 هدف توبلاب إنك توصل لأفضل خيار بدون ما تضيع وقتك في المقارنات ويوفر مالك بالاختيار المناسب لك.\n\n"
        "✅ كل لابتوب يتم اختياره بناءً على جودة المواصفات، الأداء مقابل السعر، وتقييم المنتج بشكل عام.\n\n"
        "💰 الأسعار المعروضة هي تقريبا متوسط السعر بسبب اختلاف الأسعار بين المتاجر، ويتم تحديث متوسط السعر أسبوعيًا."
    )
    await send_with_keyboard(update, text)

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_with_keyboard(update, f"📬 تواصل معي:\n{CONTACT_LINK}")

async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_with_keyboard(update, f"❤️ لدعم المشروع:\n{DONATION_LINK}")

async def send_with_keyboard(update, text):
    if update.message:
        await update.message.reply_text(text, reply_markup=main_inline_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=main_inline_keyboard())

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = query.message.chat_id
    data = query.data

    if data == "start":
        return await start(update, context)
    if data == "about":
        return await about(update, context)
    if data == "donate":
        return await donate(update, context)
    if data == "contact":
        return await contact(update, context)

    if data in purposes:
        user_state[cid] = {"purpose": data}
        await query.message.reply_text("💰 كم ميزانيتك؟ (بالريال السعودي)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    cid = update.message.chat_id

    if cid not in user_state or "purpose" not in user_state[cid]:
        return await update.message.reply_text("❗ اختر الغرض أولًا عبر الضغط على (ابدأ من جديد).", reply_markup=main_inline_keyboard())

    if not text.isdigit():
        return await update.message.reply_text("❌ أدخل رقمًا صحيحًا.", reply_markup=main_inline_keyboard())

    budget = int(text)
    user_state[cid]["budget"] = budget
    purpose = purposes[user_state[cid]["purpose"]]

    results = df[
        (df["Purpose"].str.contains(purpose, case=False)) &
        (df["Average Price (SAR)"] <= budget)
    ].sort_values(by="totalScore", ascending=False)

    if results.empty:
        return await update.message.reply_text(" لم نجد لابتوبات بهذه المواصفات.", reply_markup=main_inline_keyboard())

    for _, row in results.iterrows():
        id_str = str(row['id'])
        caption = format_laptop_info(row)
        image_paths = get_images(id_str)

        if image_paths:
            try:
                media = [InputMediaPhoto(open(p, "rb")) for p in image_paths[:5]]
                await update.message.reply_media_group(media)
                await update.message.reply_text(caption, parse_mode="HTML")
            except Exception as e:
                logger.error(f"❌ خطأ في إرسال الصور: {e}")
                await update.message.reply_text(caption, parse_mode="HTML")
        else:
            await update.message.reply_text(caption, parse_mode="HTML")

    pdf_path = generate_pdf(results.head(5))
    with open(pdf_path, "rb") as f:
        await update.message.reply_document(document=f, filename="Laptop_Comparison.pdf", caption="📄 مقارنة المواصفات بين أفضل اللابتوبات", reply_markup=main_inline_keyboard())

def format_laptop_info(r):
    brand = r['Brand']
    model = r['Model']
    price = f"{int(r['Average Price (SAR)']):,} ر.س"
    return (
        f"🏷️ <b>الشركة:</b> {brand}\n"
        f"💻 <b>الموديل:</b> <code>{model}</code>\n\n"
        f"💰 <b>السعر:</b> {price}\n\n"
        f"🔧 <b>المواصفات:</b>\n"
        f"🧠 <b>المعالج:</b> {r['Processor']}\n"
        f"🎮 <b>كرت الشاشة:</b> {r['GPU']}\n"
        f"💾 <b>الرام:</b> {r['RAM']}\n"
        f"🗃️ <b>التخزين:</b> {r['Storage']}\n"
        f"📺 <b>الشاشة:</b> {r['Display']}\n"
        f"🔋 <b>البطارية:</b> {r['Battery Life']} ساعة"
    )

def get_images(laptop_id):
    folder = os.path.join(IMAGES_FOLDER, laptop_id)
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

def generate_pdf(results_df):
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(temp.name, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30)
    elements = []

    styles = getSampleStyleSheet()
    title = Paragraph("📄 Top 5 Recommended Laptops Based on Your Budget", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    data = [[
        "⭐", "Model", "Price (SAR)", "Processor", "GPU", "RAM",
        "Storage", "Display", "Battery", "Score"
    ]]

    best_score = results_df['totalScore'].max()

    for _, r in results_df.iterrows():
        is_best = r['totalScore'] == best_score
        star = "⭐" if is_best else ""
        data.append([
            star,
            f"{r['Brand']} {r['Model']}",
            str(r['Average Price (SAR)']),
            r['Processor'],
            r['GPU'],
            r['RAM'],
            r['Storage'],
            r['Display'],
            f"{r['Battery Life']}h",
            r['totalScore']
        ])

    table = Table(data, repeatRows=1, hAlign='LEFT', colWidths=[
        10*mm, 50*mm, 25*mm, 40*mm, 35*mm, 20*mm, 30*mm, 35*mm, 20*mm, 20*mm
    ])

    style = TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey])
    ])

    for i, r in enumerate(results_df.iterrows(), start=1):
        if r[1]['totalScore'] == best_score:
            style.add('BACKGROUND', (0, i), (-1, i), colors.lightgreen)

    table.setStyle(style)
    elements.append(table)
    doc.build(elements)
    return temp.name

# أمر عرض عدد المستخدمين
async def users_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ هذا الأمر مخصص للمطور فقط.")
    await update.message.reply_text(f"📊 عدد المستخدمين المسجلين: {len(users)}")

async def set_bot_commands(application):
    commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("about", "عن التطبيق"),
        BotCommand("contact", "تواصل معي"),
        BotCommand("donate", "دعم المشروع"),
        BotCommand("users_count", "عدد المستخدمين (خاص بالمطور)")
    ]
    await application.bot.set_my_commands(commands)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("contact", contact))
    app.add_handler(CommandHandler("donate", donate))
    app.add_handler(CommandHandler("users_count", users_count))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def on_startup(app):
        await set_bot_commands(app)

    app.post_init = on_startup
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
