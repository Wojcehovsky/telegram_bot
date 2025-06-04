import asyncio
import os
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, FSInputFile, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from aiogram.enums import ContentType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# Налаштування
API_TOKEN = '8186990104:AAFwr5olrJcO7eYpUOrS55qFeb39YSVTnZM'
UPLOAD_DIR = r"E:\\Паспорта"
PASSWORD = "1234"
os.makedirs(UPLOAD_DIR, exist_ok=True)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
authorized_users = set()
user_temp_files = {}
PAGE_SIZE = 10

# Стани
class FileStates(StatesGroup):
    waiting_for_password = State()
    collecting_files = State()
    waiting_for_folder_to_save = State()
    waiting_for_search = State()
    selecting_existing_folder = State()

# Клавіатури
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Завантажити файл")],
        [KeyboardButton(text="🔍 Пошук файлу"), KeyboardButton(text="📂 Переглянути папки")]
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="✅Відправити")]],
    resize_keyboard=True
)

# Перевірка доступу
async def check_auth(message: Message, state: FSMContext) -> bool:
    if message.from_user.id not in authorized_users:
        if await state.get_state() != FileStates.waiting_for_password:
            await message.answer("🔐 Введіть пароль для доступу:")
            await state.set_state(FileStates.waiting_for_password)
        return False
    return True

# Обробка пароля
@dp.message(FileStates.waiting_for_password)
async def handle_password(message: Message, state: FSMContext):
    if message.text.strip() == PASSWORD:
        authorized_users.add(message.from_user.id)
        await message.answer("✅ Доступ дозволено!", reply_markup=main_kb)
        await state.clear()
    else:
        await message.answer("❌ Невірний пароль. Спробуйте ще раз:")

# Команда /start
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    if not await check_auth(message, state): return
    await message.answer("👋 Вітаю! Оберіть дію з меню нижче:", reply_markup=main_kb)

# Завантаження файлів
@dp.message(F.text == "📤 Завантажити файл")
async def prompt_upload(message: Message, state: FSMContext):
    if not await check_auth(message, state): return
    await message.answer("📎 Надішліть файли. Коли завершите — натисніть '✅Відправити'.", reply_markup=back_kb)
    await state.set_state(FileStates.collecting_files)

@dp.message(FileStates.collecting_files, F.text == "✅Відправити")
async def prompt_folder_name(message: Message, state: FSMContext):
    await message.answer("📁 Введіть назву папки для збереження:", reply_markup=back_kb)
    await state.set_state(FileStates.waiting_for_folder_to_save)

@dp.message(FileStates.collecting_files, F.content_type.in_({
    ContentType.DOCUMENT, ContentType.PHOTO, ContentType.VIDEO,
    ContentType.AUDIO, ContentType.VOICE, ContentType.STICKER
}))
async def collect_files(message: Message, state: FSMContext):
    if not await check_auth(message, state): return
    user_id = message.from_user.id
    user_temp_files.setdefault(user_id, [])

    if message.document:
        file_id, file_name = message.document.file_id, message.document.file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"{file_id}.jpg"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"{file_id}.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or f"{file_id}.mp3"
    elif message.voice:
        file_id = message.voice.file_id
        file_name = f"{file_id}.ogg"
    elif message.sticker:
        file_id = message.sticker.file_id
        file_name = f"{file_id}.webp"
    else:
        return

    user_temp_files[user_id].append({"file_id": file_id, "file_name": file_name})

@dp.message(FileStates.waiting_for_folder_to_save)
async def save_files_to_folder(message: Message, state: FSMContext):
    folder_name = message.text.strip()
    user_id = message.from_user.id
    files = user_temp_files.pop(user_id, [])

    if not files:
        await message.answer("⚠️ Немає файлів для збереження.", reply_markup=main_kb)
        await state.clear()
        return

    save_path = Path(UPLOAD_DIR) / folder_name
    save_path.mkdir(parents=True, exist_ok=True)

    for item in files:
        file_info = await bot.get_file(item["file_id"])
        full_path = save_path / item["file_name"]
        await bot.download_file(file_info.file_path, full_path)

    await message.answer(f"✅ {len(files)} файл(и) збережено в `{folder_name}`.", parse_mode="Markdown", reply_markup=main_kb)
    await state.clear()

# Пошук
@dp.message(F.text == "🔍 Пошук файлу")
async def ask_search(message: Message, state: FSMContext):
    if not await check_auth(message, state): return
    await message.answer("🔎 Введіть назву файлу або папки:", reply_markup=main_kb)
    await state.set_state(FileStates.waiting_for_search)

@dp.message(FileStates.waiting_for_search)
async def search_files(message: Message, state: FSMContext):
    query = message.text.lower().strip()
    found_files = []
    found_folders = []

    for path in Path(UPLOAD_DIR).rglob("*"):
        if path.is_dir() and query in path.name.lower():
            found_folders.append(path)
        elif path.is_file() and query in path.name.lower():
            found_files.append(path)

    if not found_files and not found_folders:
        await message.answer("❌ Нічого не знайдено.", reply_markup=main_kb)
        await state.clear()
        return

    if found_folders:
        if len(found_folders) == 1:
            folder = found_folders[0]
            files = list(folder.glob("*"))
            if files:
                await message.answer(f"📁 Папка `{folder.name}` знайдена. Ось файли:", parse_mode="Markdown")
                for f in files:
                    if f.is_file():
                        await message.answer_document(FSInputFile(f))
            else:
                await message.answer("📂 Папка пуста.")
            await state.clear()
            return

        folder_names = [f.name for f in found_folders]
        await state.update_data(matching_folders=folder_names, folders_page=0)
        await state.set_state(FileStates.selecting_existing_folder)
        await send_folder_page(message, state)

    if found_files:
        await message.answer(f"🗂 Знайдено {len(found_files)} файл(ів):")
        for f in found_files[:10]:
            await message.answer_document(FSInputFile(f))
        if len(found_files) > 10:
            await message.answer("⚠️ Показано лише перші 10 результатів.")
        await state.clear()

# Перегляд папок
@dp.message(F.text == "📂 Переглянути папки")
async def list_folders(message: Message, state: FSMContext):
    if not await check_auth(message, state): return

    folders = sorted([f.name for f in Path(UPLOAD_DIR).iterdir() if f.is_dir()])
    if not folders:
        await message.answer("📁 Папок ще не створено.")
        return

    await state.update_data(matching_folders=folders, folders_page=0)
    await state.set_state(FileStates.selecting_existing_folder)
    await send_folder_page(message, state)

async def send_folder_page(message: Message, state: FSMContext):
    data = await state.get_data()
    folders = data.get("matching_folders", [])
    page = data.get("folders_page", 0)

    start, end = page * PAGE_SIZE, (page + 1) * PAGE_SIZE
    current = folders[start:end]

    buttons = [[KeyboardButton(text=name)] for name in current]
    nav = []
    if page > 0: nav.append(KeyboardButton(text="⬅️ Назад"))
    if end < len(folders): nav.append(KeyboardButton(text="➡️ Вперед"))
    if nav: buttons.append(nav)
    buttons.append([KeyboardButton(text="🔙 Вийти")])

    await message.answer(f"📂 Сторінка {page + 1}:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(FileStates.selecting_existing_folder)
async def handle_existing_folder(message: Message, state: FSMContext):
    text = message.text
    data = await state.get_data()
    folders = data.get("matching_folders", [])
    page = data.get("folders_page", 0)

    if text == "⬅️ Назад" and page > 0:
        await state.update_data(folders_page=page - 1)
        await send_folder_page(message, state)
    elif text == "➡️ Вперед" and (page + 1) * PAGE_SIZE < len(folders):
        await state.update_data(folders_page=page + 1)
        await send_folder_page(message, state)
    elif text == "🔙 Вийти":
        await state.clear()
        await message.answer("🔙 Вийшли з перегляду папок.", reply_markup=main_kb)
    elif text in folders:
        folder = Path(UPLOAD_DIR) / text
        files = list(folder.glob("*"))
        if files:
            await message.answer(f"📁 Вміст папки `{text}`:", parse_mode="Markdown")
            for f in files:
                if f.is_file():
                    await message.answer_document(FSInputFile(f))
        else:
            await message.answer("📂 Папка пуста.")
        await state.clear()
        await message.answer("📋 Повернулись у головне меню.", reply_markup=main_kb)
    else:
        await message.answer("❌ Невідома команда. Оберіть папку або використайте навігацію.")

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
