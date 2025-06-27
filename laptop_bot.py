import os
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

DONATION_LINK = "https://buymeacoffee.com/your_link"
CONTACT_LINK = "https://t.me/Ahmed0ksa"
ABOUT_TEXT = "💡 هذا التطبيق يساعدك في اختيار أفضل لابتوب حسب ميزانيتك واستخدامك.\nتم تطويره بواسطة أحمد ❤️"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_state = {}
purposes = {
    "🎮 الألعاب": "Gaming",
    "🎨 التصميم": "Design",
    "💻 البرمجة والذكاء الاصطناعي": "Programming and AI",
    "📚 الدراسة": "Studying"
}

df = pd.read_csv(CSV_PATH)
df["Average Price (SAR)"] = pd.to_numeric(df["Average Price (SAR)"], errors="coerce")
df = df.dropna(subset=["Average Price (SAR)"])

def main_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 ابدأ من جديد", callback_data="start"), InlineKeyboardButton("ⓘ عن توبلاب", callback_data="about")],
        [InlineKeyboardButton("دعم المشروع 💵", callback_data="donate"), InlineKeyboardButton("💌 تواصل معي", callback_data="contact")]
    ])


def purpose_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(k, callback_data=k)] for k in purposes])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    user_state.pop(cid, None)
    send = update.message.reply_text if update.message else update.callback_query.message.reply_text
    await send("👇 حدد غرض استخدامك من اللابتوب:", reply_markup=purpose_keyboard())

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_with_keyboard(update, ABOUT_TEXT)

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

    try:
        budget = int(text)
    except ValueError:
        return await update.message.reply_text("❌ أدخل رقمًا صحيحًا.", reply_markup=main_inline_keyboard())

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
    style_title = styles['Title']
    style_title.fontName = 'Helvetica-Bold'
    style_title.fontSize = 14

    title = Paragraph("📄 Top 5 Recommended Laptops Based on Your Budget", style_title)
    elements.append(title)
    elements.append(Spacer(1, 12))

    try:
        first_row = results_df.iloc[0]
        purpose = first_row.get("Purpose", "غير معروف")
        budget = int(first_row.get("Average Price (SAR)", 0))
        info_text = f"🔍 <b>Purpose:</b> {purpose} | 💰 <b>Budget:</b> {budget:,} SAR"
    except Exception:
        info_text = "🔍 لم يتم تحديد الغرض أو الميزانية"

    info_paragraph = Paragraph(info_text, styles['Normal'])
    elements.append(info_paragraph)
    elements.append(Spacer(1, 8))

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
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
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

async def set_bot_commands(application):
    commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("about", "عن التطبيق"),
        BotCommand("contact", "تواصل معي"),
        BotCommand("donate", "دعم المشروع"),
    ]
    await application.bot.set_my_commands(commands)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("contact", contact))
    app.add_handler(CommandHandler("donate", donate))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def on_startup(app):
        await set_bot_commands(app)

    app.post_init = on_startup
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
