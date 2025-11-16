import json
import os
import telebot
from telebot import types
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
from flask import Flask, request, Response
import threading
from waitress import serve
import logging

logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s',
  filename='/home/dayzee/SpotifyTelegramBot//bot.log',
  filemode='a'
)
logger = logging.getLogger()

logger.info('Бот запущен')
web = Flask(__name__)

with open('settings.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

bot = telebot.TeleBot(config['bot_token'])

CACHE_FILE = 'spotify_clients.json'

auth_codes = {}

def search_track(message,spotifyClient,query):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton('Добавить в очередь',callback_data='add_to_queue'))
    index = 0
    search_result = spotifyClient.search(q=query, limit=10, offset=0, type='track',market='US')['tracks']
    limit = 10
    if search_result['total'] < limit:
        limit = search_result['total']
    if limit == 0:
        bot.send_message(message.chat.id,f'Ничего не удалось найти&#10&#10Попробуй поиск с другими параметрами',parse_mode='html')
    while index < limit:
        search_message = bot.send_message(message.chat.id, f'<a href="https://open.spotify.com/track/{search_result['items'][index]['id']}">{get_artist(search_result['items'][index]['artists'])} - {search_result['items'][index]['name']}</a>', parse_mode='html',reply_markup=markup)
        threading.Thread(target=delete_search_history, args=(message.chat.id,search_message.message_id)).start()
        index += 1

def get_artist(artists):
    index = 0
    artist = ''
    while index < len(artists):
        if index == 0:
            artist = artists[index]['name']
        else:
            artist = artist + ', ' + artists[index]['name']
        index = index + 1
    return artist

def add_track_to_queue(message,spotifyClient,track_id):
    if len(spotifyClient.devices()['devices']) > 0:
        track_info = spotifyClient.track(track_id)
        spotifyClient.add_to_queue(uri='https://open.spotify.com/track/' + track_id,
                                   device_id=spotifyClient.devices()['devices'][0]['id'])
        bot.send_message(message.chat.id,
                         f'Добавлено в очередь &#10&#10<a href="https://open.spotify.com/track/{track_id}">{get_artist(track_info['artists'])} - {track_info['name']}</a>',
                         parse_mode='html')
    else:
        bot.send_message(message.chat.id, 'Для выполнения команды нужно чтобы Spotify работал на устройстве',
                         parse_mode='html')

def delete_search_history(chat_id,message_id):
    time.sleep(60)
    bot.delete_message(chat_id,message_id)

def load_clients():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_clients(clients):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(clients, f, ensure_ascii=False, indent=4)

def wait_for_code(user_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        if user_id in auth_codes:
            return auth_codes.pop(user_id)
        time.sleep(1)
    return None

def get_cache_path(chat_id):
    return f".cache-{chat_id}"

def get_token(chat_id):
    token_info = spotify_clients_cache.get(chat_id)
    if not token_info:
        return None

    sp_oauth = SpotifyOAuth(client_id=config['spotify_client_id'],
                            client_secret=config['client_secret'],
                            redirect_uri=config['redirect_uri'],
                            scope=config['scope'],
                            cache_path=get_cache_path(chat_id))
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        spotify_clients_cache[chat_id] = token_info
        save_clients(spotify_clients_cache)
    return token_info['access_token']

def get_devices(message, spotifyClient):
    devices = spotifyClient.devices()['devices']
    if len(devices) > 0:
        for device in devices:
            status = 'Активен' if device.get('is_active', False) else 'Не активен'

            if not device.get('is_active', False):
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton('Сделать активным', callback_data=f'activate_device-{device['id']}'))
                bot.send_message(message.chat.id, f'{device.get('name', 'Неизвестно')}: {status}', reply_markup=markup)
            else:
                bot.send_message(message.chat.id, f'{device.get('name', 'Неизвестно')}: {status}')

def get_active_device(spotifyClient):
    devices = spotifyClient.devices().get('devices', [])
    for device in devices:
        if device.get('is_active'):
            return device.get('id')
    return 0

def run_flask():
    serve(web, host='0.0.0.0', port=8080)

def run_polling():
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Polling error: {e}")
        time.sleep(15)

spotify_clients_cache = load_clients()

@web.route('/callback')
def callback():
    auth_codes[request.args.get('state')] = request.args.get('code')
    return Response('''<html><body><script>window.close();</script></body></html>''',
                    mimetype='text/html')

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,f'Привет, {message.chat.first_name}!&#10&#10Я бот для добавления треков в очередь Spotify.&#10Напиши мне в чат команду "Гайд" и я расскажу, как я работаю', parse_mode='html')

@bot.message_handler(commands=['help'])
def help(message):
    gaid = '''Главная моя функция - это добавлять треки в текущую очередь. Для этого мне нужна ссылка на трек. Получить ее можно двумя способами.&#10&#10Первый способ. Я умею искать треки, если известно точное наименование исполнителя и название трека, то можно прислать мне сообщение "@brooklite_spotify_bot Найди {Исполнитель}-{Название трека}".&#10&#10Пример:&#10&#10@brooklite_spotify_bot Найди Michael Jackson-Billie Jean Обязательно с разделителем "-" без пробелов, чтобы я понял, где Исполнитель, а где Название трека. Если изветсно только название исполнителя или только название трека, то можно написать "@brooklite_spotify_bot Найди {что искать}"&#10&#10Пример:&#10&#10@brooklite_spotify_bot Найди ABBA&#10&#10В ответ на такое сообщение пришлю варианты поиска в виде двух кнопок: "Искать по исполнителю" и "Искать по названию трека". После нажатия на кнопку - вывожу роезультат. В чате появятся 10 треков, которые мне удалось найти. Под каждым вариантом будет кнопка "Добавить в очередь", которая добавит трек в очередь. Через 5 минут история поиска будет удалена, чтобы не засорять чат.&#10&#10Переходим ко второму варианту. Если по результату поиска не удалось найти, что хотелось, то можно поискать непосредственно в поиске Spotify. В меню кнопка "Spotify" откроет поиск в приложении или в браузере, если приложение не установлено.&#10&#10<u>Важное замечание! Для работы ссылки в браузере потребуется VPN.</u> В приложении такой проблемы нет.&#10&#10В Spotify на выбранном треке нужно нажать ... -> "Поделиться" -> "Больше" -> Telegram -> и прислать мне, боту BrookLite. Либо нажать ... ->  "Поделиться" -> "Скопировать ссылку" -> и прислать ссылку мне в этот чат. Я добавлю твой трек в очередь. &#10&#10Еще я могу показать текущую очередь и что сейчас играет. в меню кнопка "Показать очередь"'''
    bot.send_message(message.chat.id, gaid, parse_mode='html')

@bot.message_handler(commands=['spotify'])
def spotify(message):
    bot.send_message(message.chat.id,'Если не установлен Spotify, то <a href="https://open.spotify.com/search">ссылка</a> откроется в браузере. Возможно потребуется VPN',  parse_mode='html')

@bot.message_handler(commands=['queue'])
def queue(message):
    auth_token = get_token(str(message.chat.id))
    if not auth_token:
       bot.send_message(message.chat.id, "Нужно авторизоваться в Spotify")
       return
    else:
       spotifyClient = spotipy.Spotify(auth=auth_token)
    if len(spotifyClient.devices()['devices']) > 0:
        queue=spotifyClient.queue()
        mess = f'Сейчас играет:&#10<a href="https://open.spotify.com/track/{queue['currently_playing']['id']}">{get_artist(queue['currently_playing']['artists'])} - {queue['currently_playing']['name']}</a>'
        index = 0
        mess = mess + f'&#10&#10Далее в очереди:&#10'
        while index < 10:
            if index == 0:
                mess =mess + f'<a href="https://open.spotify.com/track/{queue['queue'][index]['id']}">{get_artist(queue['queue'][index]['artists'])} - {queue['queue'][index]['name']}</a>'
            else:
                mess = mess + f'&#10<a href="https://open.spotify.com/track/{queue['queue'][index]['id']}">{get_artist(queue['queue'][index]['artists'])} - {queue['queue'][index]['name']}</a>'
            index += 1
        bot.send_message(message.chat.id, mess, parse_mode='html')
    else:
        bot.send_message(message.chat.id,'Для выполнения команды нужно чтобы Spotify работал на устройстве',parse_mode='html')

@bot.message_handler(commands=['info'])
def info(message):
    bot.send_message(message.chat.id,f'Разработано @just_dayzee&#10&#10BrookLite Int. 2023', parse_mode='html')

@bot.message_handler(commands=['admin_tools'])
def admin_tools(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True,row_width=3)
    markup.add(types.KeyboardButton('⏮'),types.KeyboardButton('⏯'),types.KeyboardButton('⏭'))
    markup.add(types.KeyboardButton('Показать все устройства'))
    bot.send_message(message.chat.id,f'Панель администратора', reply_markup=markup)

@bot.message_handler(commands=['auth'])
def auth(message):
    chat_id = str(message.chat.id)
    cache_path = get_cache_path(chat_id)
    sp_oauth = SpotifyOAuth(
        client_id=config['spotify_client_id'],
        client_secret=config['client_secret'],
        redirect_uri=config['redirect_uri'],
        scope=config['scope'],
        cache_path=cache_path
    )
    auth_url = sp_oauth.get_authorize_url(state=str(chat_id))

    bot.send_message(message.chat.id, f'Перейдите по <a href="{auth_url}">ссылке</a> для авторизации в Spotify', parse_mode='html')

    code = wait_for_code(chat_id)
    if not code:
        bot.send_message(message.chat.id, "Время ожидания истекло.")
        return

    token_info = sp_oauth.get_access_token(code)
    if token_info:
        spotify_clients_cache[chat_id] = token_info
        save_clients(spotify_clients_cache)

        bot.send_message(message.chat.id, "Авторизация прошла успешно!")
    else:
        bot.send_message(message.chat.id, "Ошибка при авторизации!")


@bot.callback_query_handler(func=lambda callback: True)
def callback_message(callback):
    auth_token = get_token(str(callback.message.chat.id))
    if not auth_token:
       bot.send_message(callback.message.chat.id, "Нужно авторизоваться в Spotify")
       return
    else:
       spotifyClient = spotipy.Spotify(auth=auth_token)

    match callback.data:
        case 'add_to_queue':
            add_track_to_queue(callback.message,spotifyClient,callback.message.json['entities'][0]['url'].replace('https://open.spotify.com/track/',''))
        case 'search_by_artist':
            search_track(callback.message,spotifyClient,'artist:' + callback.message.text.replace('Найди ',''))
            bot.delete_message(callback.message.chat.id,callback.message.message_id)
        case 'search_by_track':
            search_track(callback.message,spotifyClient,'track:' + callback.message.text.replace('Найди ',''))
            bot.delete_message(callback.message.chat.id, callback.message.message_id)
        case _ if callback.data.startswith("activate_device"):
            device_id = callback.data.split("-")[1]
            spotifyClient.transfer_playback(device_id=device_id, force_play=True)
            bot.answer_callback_query(callback.id)

@bot.message_handler()
def user_command(message):
    auth_token = get_token(str(message.chat.id))
    if not auth_token:
        bot.send_message(message.chat.id, "Нужно авторизоваться в Spotify")
        return
    else:
        spotifyClient = spotipy.Spotify(auth=auth_token)
    match message.text:
        case '⏮':
            spotifyClient.previous_track(device_id=get_active_device(spotifyClient))
            telebot.apihelper.delete_message(token=bot.token, chat_id=message.chat.id, message_id=message.message_id)
        case '⏯':
            if spotifyClient.current_playback()['is_playing']:
                spotifyClient.pause_playback(device_id=get_active_device(spotifyClient))
            else:
                spotifyClient.start_playback(device_id=get_active_device(spotifyClient))
            telebot.apihelper.delete_message(token=bot.token, chat_id=message.chat.id, message_id=message.message_id)
        case '⏭':
            spotifyClient.next_track(device_id=get_active_device(spotifyClient))
            telebot.apihelper.delete_message(token=bot.token, chat_id=message.chat.id, message_id=message.message_id)
        case 'Показать все устройства':
            get_devices(message, spotifyClient)
        case _ if message.text.startswith('https://open.spotify.com/wrapped/share'):
            add_track_to_queue(message, spotifyClient, message.text.split('track-id=')[1])
        case _ if message.text.startswith('https://open.spotify.com/track/'):
            add_track_to_queue(message, spotifyClient,
                               message.text.replace('https://open.spotify.com/track/', '').split('?si=')[0])
        case _ if message.text.startswith('@brooklite_spotify_bot Найди ') or message.text.startswith('@brooklite_spotify_bot найди '):
            query = message.text.replace('найди', 'Найди')
            query = query.replace('@brooklite_spotify_bot Найди ', '')
            if '-' in query:
                search_param = query.split('-')
                search_track(message, spotifyClient, 'artist:' + search_param[0] + ' track:' + search_param[1])
            else:
                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton('Искать по исполнителю', callback_data='search_by_artist'))
                markup.row(types.InlineKeyboardButton('Искать по названию трека', callback_data='search_by_track'))
                bot.send_message(message.chat.id, query, reply_markup=markup)

#bot.polling(none_stop=True)
if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    polling_thread = threading.Thread(target=run_polling)
    flask_thread.start()
    polling_thread.start()
    flask_thread.join()
    polling_thread.join()