import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage  # Для хранения состояний в памяти

import requests

from config import TOKEN  # Ваш TOKEN из config.py

# Настройка логирования (опционально, для отладки)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()  # Хранилище состояний
dp = Dispatcher(storage=storage)

# Состояния (если нужно для ввода города; page храним в data, не в состояниях)
class WeatherStates(StatesGroup):
    waiting_for_city = State()

# Глобальные данные (лучше кэшировать, чтобы не запрашивать API каждый раз)
weather_data = None
current_city = 'Moscow'

def fetch_weather(city: str):
    """Получает данные о погоде для города"""
    global weather_data, current_city
    api_key = '03c4df2cf3bb4185b03104938251210'  # В проде — из config
    url = f'http://api.weatherapi.com/v1/forecast.json?key={api_key}&q={city}&days=5&aqi=no&alerts=no'
    try:
        response = requests.get(url)
        response.raise_for_status()
        weather_data = response.json()
        current_city = city
        return True
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        return False

def get_keyboard(page: int):
    """Возвращает клавиатуру в зависимости от страницы (0-4)"""
    if page == 0:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Next", callback_data="next")]])
    elif page == 4:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data="back")]])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back"), InlineKeyboardButton(text="➡️ Next", callback_data="next")]
        ])

def get_day_text(page: int):
    """Текст для страницы (день по индексу)"""
    if not weather_data:
        return "Ошибка: данные о погоде не загружены."
    
    if page == 0:
        # Текущий день
        current = weather_data['current']
        day = weather_data['forecast']['forecastday'][0]['day']
        date = weather_data['location']['localtime'][:10]  # Примерно дата
        text = f"🌤️ **Текущая погода в {current_city}** ({date})\n"
        text += f"Температура: {current['temp_c']}°C (ощущается как {current['feelslike_c']}°C)\n"
        text += f"Состояние: {current['condition']['text']}\n"
        text += f"Ветер: {current['wind_kph']} км/ч, Влажность: {current['humidity']}%\n"
        text += f"Макс/мин сегодня: {day['maxtemp_c']}°C / {day['mintemp_c']}°C"
    else:
        # Прогноз на день (page 1-4)
        forecast_day = weather_data['forecast']['forecastday'][page]
        date = forecast_day['date']
        day = forecast_day['day']
        text = f"🌤️ **Прогноз на {date} в {current_city}**\n"
        text += f"Состояние: {day['condition']['text']}\n"
        text += f"Макс/мин: {day['maxtemp_c']}°C / {day['mintemp_c']}°C\n"
        text += f"Осадки: {day['totalprecip_mm']} мм, Шанс дождя: {day['daily_chance_of_rain']}%\n"
        text += f"Ветер: {day['maxwind_kph']} км/ч"
    
    return text

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not fetch_weather(current_city):  # Загружаем данные
        await message.answer("❌ Ошибка загрузки погоды. Попробуйте позже.")
        return
    
    await state.update_data(page=0)  # Устанавливаем начальную страницу
    text = get_day_text(0)
    keyboard = get_keyboard(0)
    await message.answer(text, reply_markup=keyboard, parse_mode='Markdown')

@dp.message(Command("setcity"))
async def cmd_setcity(message: Message, state: FSMContext):
    await message.answer("Введите название города (например, 'London' или 'Москва'):")
    await state.set_state(WeatherStates.waiting_for_city)

@dp.message(WeatherStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if fetch_weather(city):
        await state.update_data(page=0)
        text = get_day_text(0)
        keyboard = get_keyboard(0)
        await message.answer(f"✅ Данные для {city} загружены!", reply_markup=types.ReplyKeyboardRemove())
        await message.answer(text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await message.answer("❌ Город не найден или ошибка API. Попробуйте другой.")
    
    await state.clear()  # Выходим из состояния

@dp.callback_query(F.data == "next")
async def next_page(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_page = data.get('page', 0)
    new_page = min(current_page + 1, 4)  # Не больше 4
    
    await state.update_data(page=new_page)
    text = get_day_text(new_page)
    keyboard = get_keyboard(new_page)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
    await callback_query.answer()  # Убираем "часики"

@dp.callback_query(F.data == "back")
async def back_page(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_page = data.get('page', 0)
    new_page = max(current_page - 1, 0)  # Не меньше 0
    
    await state.update_data(page=new_page)
    text = get_day_text(new_page)
    keyboard = get_keyboard(new_page)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
    await callback_query.answer()

async def main():
    # Инициализируем данные при старте
    fetch_weather(current_city)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())