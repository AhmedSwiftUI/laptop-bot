import os
import re
import logging
import pandas as pd
import tempfile
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import mm

# === إعدادات ===
TOKEN = os.environ.get("7762927725:AAEapREwoJVXDCZdIs--FBKGKNpSYkok9dU", "")
CSV_PATH = "Cleaned_Laptop_Data_Final_Version.csv"
IMAGES_FOLDER = "Toplaps_bot_images"
DONATION_LINK = "https://buymeacoffee.com/your_link"
CONTACT_LINK = "https://t.me/your_username"
ABOUT_TEXT = "💡 هذا التطبيق يساعدك في اختيار أفضل لابتوب حسب ميزانيتك واستخدامك.\nتم تطويره بواسطة أحمد ❤️"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}
user_bot_messages = {}

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

def reply_main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔁 ابدأ من جديد"), KeyboardButton("🧹 مسح المحادثة")],
        [KeyboardButton("💰 دعم المشروع"), KeyboardButton("ℹ️ عن التطبيق"), KeyboardButton("📞 تواصل معي")]
    ], resize_keyboard=True)

def purpose_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(k, callback_data=k)] for k in purposes])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_state.pop(cid, None)
    await update.message.reply_text("👋 أهلًا بك في مساعد اختيار اللابتوب!\n👇 اختر غرض استخدامك:", reply_markup=reply_main_menu())
    await update.message.reply_text("🎯 اختر أحد الأغراض:", reply_markup=purpose_keyboard())


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cid = query.message.chat_id
    data = query.data

    if data in purposes:
        user_state[cid] = {"purpose": data}
        await query.message.reply_text("💰 كم ميزانيتك؟ (بالريال السعودي)", reply_markup=reply_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip()
    cid = update.message.chat_id

    if text in ["/start", "🔁 ابدأ من جديد"]:
        return await start(update, context)
    if text in ["/clear", "🧹 مسح المحادثة"]:
        await clear_messages(context, cid)
        return await update.message.reply_text("🧹 تم مسح المحادثة.", reply_markup=reply_main_menu())
    if text in ["/about", "ℹ️ عن التطبيق"]:
        return await update.message.reply_text(ABOUT_TEXT, reply_markup=reply_main_menu())
    if text in ["/donate", "💰 دعم المشروع"]:
        return await update.message.reply_text(f"❤️ لدعم المشروع:\n{DONATION_LINK}", reply_markup=reply_main_menu())
    if text in ["/contact", "📞 تواصل معي"]:
        return await update.message.reply_text(f"📬 تواصل معي:\n{CONTACT_LINK}", reply_markup=reply_main_menu())

    if text in purposes:
        user_state[cid] = {"purpose": text}
        return await update.message.reply_text("💰 كم ميزانيتك؟", reply_markup=reply_main_menu())

    if cid not in user_state or "purpose" not in user_state[cid]:
        return await update.message.reply_text("❗ اختر الغرض أولًا عبر /start", reply_markup=reply_main_menu())

    # تحويل الأرقام العربية لفهم الأرقام
    arabic_digits = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    clean_text = re.sub(r'[^\d]', '', text.translate(arabic_digits))

    try:
        budget = int(clean_text)
    except ValueError:
        return await update.message.reply_text("❌ أدخل رقمًا صحيحًا للميزانية.")

    user_state[cid]["budget"] = budget
    purpose = purposes[user_state[cid]["purpose"]]

    results = df[
        (df["Purpose"].str.contains(purpose, case=False)) &
        (df["Average Price (SAR)"] <= budget)
    ].copy()

    if results.empty:
        return await update.message.reply_text("😕 لم نجد لابتوبات بهذه المواصفات.", reply_markup=reply_main_menu())

    results["adjustedScore"] = results["totalScore"] - ((budget - results["Average Price (SAR)"]) / budget * 0.5)
    results = results.sort_values(by="adjustedScore", ascending=False)

    await update.message.reply_text(f"✅ تم العثور على {len(results)} لابتوب يناسب استخدامك وميزانيتك.")


    for _, row in results.head(5).iterrows():
        id_str = str(row['id'])
        caption = format_laptop_info(row)
        image_paths = get_images(id_str)

        if image_paths:
            try:
                media = [InputMediaPhoto(open(p, "rb"), caption=caption if i == 0 else None)
                         for i, p in enumerate(image_paths[:5])]
                msgs = await update.message.reply_media_group(media)
                track_messages(cid, *msgs)
            except Exception as e:
                logger.error(f"❌ خطأ في إرسال الصور: {e}")
                msg = await update.message.reply_text(caption, parse_mode="HTML")
                track_messages(cid, msg)
        else:
            msg = await update.message.reply_text(caption, parse_mode="HTML")
            track_messages(cid, msg)

    pdf_path = generate_pdf(results.head(5))
    with open(pdf_path, "rb") as f:
        msg = await update.message.reply_document(document=f, filename="Laptop_Comparison.pdf", caption="📄 مقارنة بين أفضل اللابتوبات")
        track_messages(cid, msg)

def format_laptop_info(r):
    return (f"💻 {r['Brand']} {r['Model']}\n"
            f"💰 السعر: {r['Average Price (SAR)']} ريال\n"
            f"🧠 المعالج: {r['Processor']}\n"
            f"🎮 كرت الشاشة: {r['GPU']}\n"
            f"💾 الرام: {r['RAM']}\n"
            f"🗃️ التخزين: {r['Storage']}\n"
            f"📺 الشاشة: {r['Display']}\n"
            f"🔋 البطارية: {r['Battery Life']} ساعة")

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

    best_score = results_df['adjustedScore'].max()

    for _, r in results_df.iterrows():
        star = "⭐" if r['adjustedScore'] == best_score else ""
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
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey])
    ])

    for i, r in enumerate(results_df.iterrows(), start=1):
        if r[1]['adjustedScore'] == best_score:
            style.add('BACKGROUND', (0, i), (-1, i), colors.lightgreen)

    table.setStyle(style)
    elements.append(table)
    doc.build(elements)
    return temp.name

def track_messages(cid, *msgs):
    if cid not in user_bot_messages:
        user_bot_messages[cid] = []
    for m in msgs:
        if hasattr(m, "message_id"):
            user_bot_messages[cid].append(m.message_id)

async def clear_messages(context, cid):
    if cid in user_bot_messages:
        for msg_id in user_bot_messages[cid]:
            try:
                await context.bot.delete_message(chat_id=cid, message_id=msg_id)
            except:
                continue
        user_bot_messages[cid] = []

async def set_bot_commands(application):
    commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("about", "عن التطبيق"),
        BotCommand("contact", "تواصل معي"),
        BotCommand("donate", "دعم المشروع"),
        BotCommand("clear", "مسح المحادثة"),
    ]
    await application.bot.set_my_commands(commands)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.post_init = lambda app: app.create_task(set_bot_commands(app))
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
