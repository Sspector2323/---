"""Время, погода, курсы валют."""
from datetime import datetime

import requests

from . import S, tool
from .. import config

DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WMO = {0: "ясно", 1: "преимущественно ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "изморозь",
       51: "морось", 53: "морось", 55: "сильная морось", 61: "небольшой дождь", 63: "дождь", 65: "ливень",
       71: "небольшой снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа", 80: "ливни", 81: "ливни",
       82: "сильные ливни", 85: "снегопад", 86: "сильный снегопад", 95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}


@tool("get_datetime", "Текущие дата, время и день недели.")
def get_datetime():
    n = datetime.now()
    return f"{n:%Y-%m-%d %H:%M}, {DAYS[n.weekday()]}"


@tool("weather", "Погода сейчас и прогноз на 3 дня.", {"city": S("Город, по умолчанию город из настроек")})
def weather(city: str | None = None):
    city = city or config.CITY
    geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                       params={"name": city, "count": 1, "language": "ru"}, timeout=10).json()
    if not geo.get("results"):
        return f"Не нашёл город {city}"
    g = geo["results"][0]
    w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
    }).json()
    c, d = w["current"], w["daily"]
    lines = [f"{g['name']} сейчас: {c['temperature_2m']:.0f}°, ощущается {c['apparent_temperature']:.0f}°, "
             f"{WMO.get(c['weather_code'], '')}, ветер {c['wind_speed_10m']:.0f} км/ч"]
    for i, day in enumerate(d["time"]):
        lines.append(f"{day}: {d['temperature_2m_min'][i]:.0f}…{d['temperature_2m_max'][i]:.0f}°, "
                     f"{WMO.get(d['weather_code'][i], '')}, осадки {d['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


@tool("exchange_rates", "Курсы валют ЦБ РФ (доллар, евро, юань и др.).")
def exchange_rates():
    data = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10).json()["Valute"]
    return ", ".join(f"{k}: {data[k]['Value']:.2f} ₽" for k in ("USD", "EUR", "CNY", "KZT", "BYN") if k in data)
