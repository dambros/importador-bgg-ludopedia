"""
Script to import data from BoardGameGeek into Ludopedia
"""

import os
import re
import sys
import time
from configparser import ConfigParser
from datetime import datetime
from enum import Enum
from itertools import chain
from math import ceil
from typing import List, NamedTuple
from xml.etree import ElementTree

import requests
from PySide6.QtCore import QCoreApplication, QDate, QObject, QThread, QTime, Qt, Signal
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDateTimeEdit, QDialog, QGridLayout,
                               QGroupBox, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
                               QTextEdit, QPushButton, QRadioButton, QWidget)

ICON_PATH = 'res/bgg_ludo.png'

# BGG constants
BGG_API = 'https://www.boardgamegeek.com/xmlapi2/'
BGG_COLLECTION_API = f'{BGG_API}collection'
BGG_PLAYS_API = f'{BGG_API}plays'
BGG_THING_API = f'{BGG_API}thing'
BGG_PLAYS_PER_PAGE = int(100)

# Ludopedia constants
LUDOPEDIA_URL = 'https://www.ludopedia.com.br/'
LUDOPEDIA_ADD_GAME_URL = f'{LUDOPEDIA_URL}classes/jogo_usuario_ajax.php'
LUDOPEDIA_ADD_PLAY_URL = f'{LUDOPEDIA_URL}cadastra_partida'
LUDOPEDIA_LOGIN_URL = f'{LUDOPEDIA_URL}login'
LUDOPEDIA_PLAYS_URL = f'{LUDOPEDIA_URL}partidas?id_usuario='
LUDOPEDIA_SEARCH_URL = f'{LUDOPEDIA_URL}classes/ajax/aj_search.php'
LUDOPEDIA_USER_URL = f'{LUDOPEDIA_URL}usuario/'
LUDOPEDIA_USER_ID_REGEX = re.escape(LUDOPEDIA_PLAYS_URL) + r'(\d+)'
LUDOPEDIA_VIEW_PLAY_URL = f'{LUDOPEDIA_URL}partida?id_partida='
LUDOPEDIA_VIEW_PLAY_REGEX = re.escape(LUDOPEDIA_VIEW_PLAY_URL) + r'(\d+)'

# Formatting
DATE_FORMAT = 'dd/MM/yyyy'
DEBUG_HTML = '<font color="darkseagreen">'
ERROR_HTML = '<font color="orangered">'

ENABLE_DEBUG = False

class MessageType(Enum):
    """Enum for message logging"""
    GENERIC = 1
    ERROR = 2
    DEBUG = 3

class Player(NamedTuple):
    """Represents a player in a BGG logged play"""
    name: str
    bgg_user: str
    start_position: str
    color: str
    score: str
    new: bool
    win: bool

class Play(NamedTuple):
    """Represents a logged BGG play"""
    id: int
    date: str
    length: int
    location: str
    game_name: str
    year_published: int
    comments: str
    players: List[Player]

class InputError(Exception):
    """Exception to be used if there is an input error"""

def create_date_picker(text, parent):
    """Creates a label with the given text and an accompanying date picker"""
    date_edit = QDateTimeEdit(QDate.currentDate(), parent)
    date_edit.setMaximumDate(QDate.currentDate())
    date_edit.setDisplayFormat(DATE_FORMAT)
    date_edit.setCalendarPopup(True)
    date_edit.setDisabled(True)
    date_edit_label = QLabel(text, date_edit)
    date_edit_label.setBuddy(date_edit)
    return (date_edit, date_edit_label)

def format_qdate(date):
    """Format a given QDate according to a standard format"""
    return date.toString(DATE_FORMAT)

class Importador(QWidget):
    """GUI class for the BGG -> Ludopedia importer"""
    enable_editables = Signal(bool)
    alternative_chosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = QThread()
        self.worker = None
        grid_layout = QGridLayout(self)
        login_group_box = self.create_login_group()
        data_group_box = self.create_data_group()
        self.enable_editables.connect(login_group_box.setEnabled)
        self.enable_editables.connect(data_group_box.setEnabled)
        self.import_button = QPushButton('Importar', self)
        self.import_button.setEnabled(False)
        self.enable_editables.connect(self.import_button.setEnabled)
        self.import_button.clicked.connect(self.enable_editables)
        self.import_button.clicked.connect(self.load_data)
        self.bgg_user_line_edit.textChanged.connect(self.enable_import)
        self.ludo_mail_line_edit.textChanged.connect(self.enable_import)
        self.ludo_pass_line_edit.textChanged.connect(self.enable_import)
        grid_layout.addWidget(login_group_box, 1, 1, 1, 2)
        grid_layout.addWidget(data_group_box, 2, 1, 1, 2)
        grid_layout.addWidget(self.import_button, 8, 2)
        self.log_widget = QTextEdit(self)
        self.log_widget.setReadOnly(True)
        grid_layout.addWidget(self.log_widget, 9, 1, 30, 2)

    def create_qlineedit(self, text):
        """Creates a label with the given text and an accompanying line edit"""
        line_edit = QLineEdit(self)
        line_edit_label = QLabel(text, line_edit)
        line_edit_label.setBuddy(line_edit)
        return (line_edit, line_edit_label)

    def create_login_group(self):
        """Create labels and line edits for providing BGG and ludopedia login information"""
        (self.bgg_user_line_edit, bgg_user_label) = self.create_qlineedit('Usuario BoardGameGeek:')
        (self.ludo_mail_line_edit, ludo_mail_label) = self.create_qlineedit('E-mail Ludopedia:')
        (self.ludo_pass_line_edit, ludo_pass_label) = self.create_qlineedit('Senha Ludopedia:')
        self.ludo_pass_line_edit.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        group_box = QGroupBox('Login')
        grid_layout = QGridLayout(group_box)
        grid_layout.addWidget(bgg_user_label, 1, 1)
        grid_layout.addWidget(self.bgg_user_line_edit, 1, 2)
        grid_layout.addWidget(ludo_mail_label, 2, 1)
        grid_layout.addWidget(self.ludo_mail_line_edit, 2, 2)
        grid_layout.addWidget(ludo_pass_label, 3, 1)
        grid_layout.addWidget(self.ludo_pass_line_edit, 3, 2)
        group_box.setLayout(grid_layout)
        return group_box

    def create_data_group(self):
        """Creates group for holding specific choice data selection"""
        button_group = QButtonGroup(self)
        button_group.setExclusive(True)
        colecao_radio_button = QRadioButton('Coleção')
        self.partidas_radio_button = QRadioButton('Partidas')
        colecao_radio_button.setChecked(True)
        button_group.addButton(colecao_radio_button)
        button_group.addButton(self.partidas_radio_button)
        (self.min_date_picker, min_date_label) = create_date_picker('À Partir de:', self)
        (self.max_date_picker, max_date_label) = create_date_picker('Até:', self)
        self.min_date_picker.dateChanged.connect(self.max_date_picker.setMinimumDate)
        colecao_radio_button.toggled.connect(self.min_date_picker.setDisabled)
        colecao_radio_button.toggled.connect(self.max_date_picker.setDisabled)
        self.map_users_button = QPushButton('Ver mapa de usuarios BGG -> Ludopedia', self)
        self.map_users_button.setEnabled(False)
        self.map_users_button.clicked.connect(self.user_map)
        colecao_radio_button.toggled.connect(self.map_users_button.setDisabled)
        group_box = QGroupBox('Dados')
        grid_layout = QGridLayout(group_box)
        grid_layout.addWidget(colecao_radio_button, 1, 1)
        grid_layout.addWidget(self.partidas_radio_button, 1, 2)
        grid_layout.addWidget(min_date_label, 2, 1)
        grid_layout.addWidget(self.min_date_picker, 2, 2)
        grid_layout.addWidget(max_date_label, 3, 1)
        grid_layout.addWidget(self.max_date_picker, 3, 2)
        grid_layout.addWidget(self.map_users_button, 4, 1, 1, 2)
        group_box.setLayout(grid_layout)
        return group_box

    def enable_import(self):
        """Slot to toggle state of the import button"""
        self.import_button.setDisabled(not self.bgg_user_line_edit.text() or
                                       not self.ludo_mail_line_edit.text() or
                                       not self.ludo_pass_line_edit.text())

    def log_text(self, message_type, text):
        """Logs the given text to the QPlainTextWidget"""
        current_time = QTime.currentTime().toString()
        if message_type == MessageType.ERROR:
            self.log_widget.insertHtml(f'[{current_time}] {ERROR_HTML}{text}<br>')
        elif message_type == MessageType.GENERIC:
            self.log_widget.insertHtml(f'[{current_time}] {text}<br>')
        elif message_type == MessageType.DEBUG and ENABLE_DEBUG:
            self.log_widget.insertHtml(f'[{current_time}] {DEBUG_HTML}{text}<br>')

        self.log_widget.moveCursor(QTextCursor.End)
        if ENABLE_DEBUG:
            print(text)

    def disconnect_thread(self):
        """Disconnect the started signal from the thread"""
        self.thread.started.disconnect()

    def configure_thread(self, worker):
        """Does basic thread startup and cleanup configuration"""
        worker.finished.connect(self.thread.quit)
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.message.connect(self.log_text)
        worker.finished.connect(self.disconnect_thread)
        worker.exit_on_error.connect(self.thread.quit)
        worker.exit_on_error.connect(
            lambda: self.enable_editables.emit(True)
        )

    def load_data(self):
        """Load data from bgg"""
        try:
            (session, ludo_user_id) = self.login_ludopedia()
            bgg_user = self.bgg_user_line_edit.text()

            if self.partidas_radio_button.isChecked():
                current_date = format_qdate(QDate.currentDate())
                min_date = parse_date(format_qdate(self.min_date_picker.date()), current_date)
                max_date = parse_date(format_qdate(self.max_date_picker.date()), min_date)
                self.worker = BGGPlayFetcher(bgg_user, min_date, max_date)
                self.configure_thread(self.worker)
                self.worker.finished.connect(
                    lambda plays: self.post_plays(session, plays, bgg_user, ludo_user_id)
                )
            else:
                self.worker = BGGColectionFetcher(bgg_user)
                self.configure_thread(self.worker)
                self.worker.finished.connect(
                    lambda bgg_collection: self.import_collection(session, bgg_collection)
                )
            self.thread.start()
        except InputError:
            self.enable_editables.emit(True)

    def post_plays(self, session, plays, bgg_user, ludo_user_id):
        """Receives plays from the Play Fetched thread and start the Ludopedia Logger"""
        user_map = self.get_bgg_to_ludo_users()
        if bgg_user not in user_map:
            user_map[bgg_user] = ludo_user_id
        self.worker = LudopediaPlayLogger(session, plays, bgg_user, user_map)
        self.worker.request_search.connect(self.request_search_and_show_alternatives,
                                           Qt.BlockingQueuedConnection)
        self.worker.request_alternative.connect(self.request_alternative,
                                                Qt.BlockingQueuedConnection)
        self.alternative_chosen.connect(self.worker.receive_alternative, Qt.DirectConnection)
        self.configure_thread(self.worker)
        self.worker.finished.connect(
            lambda: self.enable_editables.emit(True)
        )
        self.thread.start()

    def user_map(self):
        """Slot to show user map from bgg to ludopedia"""
        user_map_dialog = QDialog(self)
        user_map_dialog.setModal(True)
        bgg_to_ludo = self.get_bgg_to_ludo_users()
        user_list = [f'{key} -> {value}' for key, value in bgg_to_ludo.items()]
        list_widget = QListWidget(user_map_dialog)
        list_widget.addItems(user_list)
        list_widget.setResizeMode(QListView.Adjust)
        list_widget.sortItems()
        grid_layout = QGridLayout(user_map_dialog)
        grid_layout.addWidget(list_widget, 1, 1)
        user_map_dialog.resize(400, 400)
        user_map_dialog.show()

    def login_ludopedia(self):
        """Logins into Ludopedia manually and returns the session and user_id"""
        self.log_text(MessageType.GENERIC, 'Obtendo dados do Ludopedia')
        payload = {'email': self.ludo_mail_line_edit.text(),
                   'pass': self.ludo_pass_line_edit.text()}

        session = requests.Session()
        session_request = session.post(LUDOPEDIA_LOGIN_URL, data=payload)

        if 'senha incorretos' in session_request.text:
            self.log_text(MessageType.ERROR,
                          'Não foi possível logar na Ludopedia com as informações fornecidas')
            raise InputError

        user_re = re.search(r'id_usuario=(\d+)', session_request.text)
        user_id = user_re.group(1) if user_re else None

        return (session, user_id)

    def import_collection(self, session, collection):
        """Imports a given collection into Ludopedia"""
        self.worker = LudopediaCollectionLogger(session, collection)
        self.configure_thread(self.worker)
        self.worker.finished.connect(
            lambda: self.enable_editables.emit(True)
        )
        self.thread.start()

    def show_alternatives_dialog(self, bgg_play, data):
        """Show alternative games to use as the game to log a play"""
        alternatives_dialog = QInputDialog(self)
        alternatives_list = [f'{item["nm_jogo"]} ({item["ano_publicacao"]})' for item in data]
        alternatives_dialog.setComboBoxItems(alternatives_list)
        alternatives_dialog.setOption(QInputDialog.UseListViewForComboBoxItems)
        game_str = f'{bgg_play.game_name} ({bgg_play.year_published})'
        alternatives_dialog.setLabelText(f'Escolha uma alternativa para o jogo "{game_str}"')
        if alternatives_dialog.exec_():
            selected_index = alternatives_list.index(alternatives_dialog.textValue())
            return data[selected_index]
        return None

    def request_search_and_show_alternatives(self, session, bgg_play):
        """Request a new string to use for game search and then show results to be picked"""
        new_search_dialog = QInputDialog(self)
        game_str = f'{bgg_play.game_name} ({bgg_play.year_published})'
        new_search_dialog.setLabelText(f'Jogo "{game_str}" não encontrado\nBuscar por:')
        new_search_dialog.setInputMode(QInputDialog.TextInput)
        if new_search_dialog.exec_():
            data = search_ludopedia_games(session, new_search_dialog.textValue())
            data = self.show_alternatives_dialog(bgg_play, data)
            self.alternative_chosen.emit(data)

    def request_alternative(self, bgg_play, data):
        """Request an alternative from user and emit choice"""
        alternative = self.show_alternatives_dialog(bgg_play, data)
        self.alternative_chosen.emit(alternative)

    def get_bgg_to_ludo_users(self):
        """Reads usuarios.txt file to map a bgg user to its corresponding ludopedia one"""
        try:
            parser = ConfigParser()
            with open("usuarios.txt") as lines:
                lines = chain(("[top]",), lines)
                parser.read_file(lines)
                bgg_to_ludo_user = dict(parser['top'])
                bgg_to_ludo_user_id = dict()
                for bgg_user, ludo_user in bgg_to_ludo_user.items():
                    if ludo_user.isdigit():
                        bgg_to_ludo_user_id[bgg_user] = ludo_user
                        self.log_text(MessageType.DEBUG, f'Usuário do BGG "{bgg_user}" já mapeado'
                                                         f' ao id ludopedia: {ludo_user}')
                    else:
                        ludo_user_id = get_ludo_user_id(ludo_user)
                        if ludo_user_id:
                            self.log_text(MessageType.DEBUG, f'{ludo_user_id} para {ludo_user}')
                            bgg_to_ludo_user_id[bgg_user] = ludo_user_id
                        else:
                            self.log_text(MessageType.ERROR, f'Falha ao buscar id de usuario da'
                                                             f' ludopedia para "{ludo_user}"')
                return bgg_to_ludo_user_id
        except FileNotFoundError:
            self.log_error(MessageType.ERROR, 'Não foi possível encontrar o arquivo "usuarios.txt')
            return {}

def create_gui(icon):
    """Create and show the GUI Application"""
    app = QApplication()
    app.setApplicationName('Importador BGG -> Ludopedia')
    app.setApplicationVersion('v0.4')
    app.setWindowIcon(QIcon(icon))

    importer = Importador()
    importer.show()
    importer.raise_()
    importer.setVisible(True)
    importer.resize(500, 400)

    sys.exit(app.exec_())

def get_from_bgg(api_url, parameters):
    """Successively attempts to get data from BGG given an API"""
    response = requests.get(api_url, params=parameters)
    # Retry if return codes indicate "too many requests"
    while response.status_code == 202 or response.status_code == 429:
        time.sleep(2)
        response = requests.get(api_url, params=parameters)
    return response

BGG_GAME_TO_PUBLISHED_YEAR = dict()
def get_yearpublished_from_id(game_id):
    """Get the year that a game was published"""
    if game_id in BGG_GAME_TO_PUBLISHED_YEAR:
        return BGG_GAME_TO_PUBLISHED_YEAR[game_id]

    params = {'id': game_id}

    response = get_from_bgg(BGG_THING_API, params)

    if response.status_code == 200:
        root = ElementTree.fromstring(response.content)
        year_published = root.find("item").find("yearpublished").get("value")
        BGG_GAME_TO_PUBLISHED_YEAR[game_id] = year_published
        return year_published
    return None

def parse_date(date, default_date):
    """Parses a given date"""
    try:
        datetime.strptime(date, '%d/%m/%Y')
    except ValueError:
        print(f'\nData invalida, usando o padrão {default_date}')
        return default_date
    return date

def get_players_from_play(play):
    """Returns a list of players that took part in a game"""
    players = []
    for player in play.find('players').findall('player'):
        players.append(Player(
            name=player.get('name'),
            bgg_user=player.get('username'),
            start_position=player.get('startposition'),
            color=player.get('color'),
            score=player.get('score'),
            new=player.get('new'),
            win=player.get('win')
        ))
    return players

def parse_play(play, username):
    """Given an BGG xml play, return a tuple with relevant play data"""
    game = play.findall('item')[0]
    comments_element = play.find('comments')
    players = get_players_from_play(play)

    # sort players, me first
    players.sort(key=lambda p: (p[1] != username, p[2]))

    return Play(
        id=play.get('id'),
        date=play.get('date'),
        length=play.get('length'),
        location=play.get('location'),
        game_name=game.get('name'),
        year_published=get_yearpublished_from_id(game.get('objectid')),
        comments=comments_element.text if comments_element is not None else None,
        players=players,
    )

def get_ludo_user_id(ludo_username):
    """Returns the user id (number) for a given username in Ludopedia"""
    session = requests.Session()
    result = session.get(f'{LUDOPEDIA_USER_URL}/{ludo_username}')
    match_id = re.search(LUDOPEDIA_USER_ID_REGEX, result.text)
    if match_id:
        # Return the user_id
        return match_id.group(1)
    return None

def search_ludopedia_games(session, game_name):
    """Search for a given game in Ludopedia"""
    params = {'tipo': 'jogo', 'count': 'true', 'pagina': 1, 'qt_rows': 20}
    params['nm_jogo'] = game_name
    game_request = session.get(LUDOPEDIA_SEARCH_URL, params=params)
    data = game_request.json()['data']
    return data

class GenericWorker(QObject):
    """Generic worker thread object which can broadcast messages"""
    message = Signal(MessageType, str)
    exit_on_error = Signal()

    def run(self):
        """Base method to run and post exceptions as errors"""
        try:
            self.run_impl()
        except Exception as exc:
            self.post_error(f'Thread exited with "{exc}"')
            self.exit_on_error.emit()
            raise

    def post_debug(self, text):
        """Broadcast debug messages to anyone listening"""
        self.message.emit(MessageType.DEBUG, text)

    def post_error(self, text):
        """Broadcast error messages to anyone listening"""
        self.message.emit(MessageType.ERROR, text)

    def post_generic(self, text):
        """Broadcast messages to anyone listening"""
        self.message.emit(MessageType.GENERIC, text)

class BGGColectionFetcher(GenericWorker):
    """Class that fetches the game collection of a BGG user"""
    finished = Signal(object)

    def __init__(self, bgg_user):
        super().__init__()
        self.bgg_user = bgg_user

    def run_impl(self):
        """Run BGG collection fetcher"""
        collection = self.get_bgg_collection(self.bgg_user)
        self.finished.emit(collection)

    def get_bgg_collection(self, username):
        """Get all items in a BGG user colection"""
        self.post_generic("Obtendo coleção do BGG...")
        params = {'username': username}

        response = get_from_bgg(BGG_COLLECTION_API, params)

        collection = []
        if response.status_code == 200:
            root = ElementTree.fromstring(response.content)

            if root.tag == 'errors':
                self.post_error('Usuário do BGG fornecido é inválido')
                self.exit_on_error.emit()

            total_jogos = root.attrib['totalitems']
            self.post_generic(f'{total_jogos} jogos encontrado no BGG')

            for item in root.findall('item'):
                name = item.find('name').text
                status = item.find('status')
                year_published = item.find('yearpublished').text
                collection.append((name, status.attrib, year_published))

        return collection

class BGGPlayFetcher(GenericWorker):
    """Class that retrieves all logged plays from a BGG user given a data range"""
    finished = Signal(object)

    def __init__(self, bgg_user, min_date, max_date):
        super().__init__()
        self.bgg_user = bgg_user
        self.min_date = min_date
        self.max_date = max_date

    def run_impl(self):
        """Run BGG play fetcher"""
        plays = self.get_bgg_plays_from_dates(self.bgg_user, self.min_date, self.max_date)
        self.finished.emit(plays)

    def get_bgg_plays_from_dates(self, username, min_date, max_date):
        """Get all logged plays from a BGG user"""

        has_more = True
        page = 1
        total_pages = 1
        plays = []
        while has_more:
            params = {
                'username': username,
                'page': page,
                'mindate': datetime.strptime(min_date, '%d/%m/%Y').strftime('%Y-%m-%d'),
                'maxdate': datetime.strptime(max_date, '%d/%m/%Y').strftime('%Y-%m-%d')
            }

            response = get_from_bgg(BGG_PLAYS_API, params)

            if response.status_code == 200:
                root = ElementTree.fromstring(response.content)

                if root.text is not None and root.text.strip() == 'Invalid object or user':
                    self.post_error('Usuário do BGG fornecido é inválido')
                    self.exit_on_error.emit()

                if page == 1:
                    total_partidas = root.get('total')
                    total_pages = ceil(int(total_partidas)/BGG_PLAYS_PER_PAGE)
                    self.post_generic(f'Total de partidas encontradas no BGG: {total_partidas}')

                self.post_generic(f'Obtendo partidas do BGG, página {page}/{total_pages}')

                plays.extend(parse_play(play, username) for play in root.findall('play'))

                self.post_generic(f'Total de partidas importadas: {len(plays)}')

                if len(plays) >= int(total_partidas):
                    has_more = False
                else:
                    page += 1

        return plays

class LudopediaCollectionLogger(GenericWorker):
    """Class that logs a collection of BGG games into Ludopedia"""
    finished = Signal()

    def __init__(self, session, collection):
        super().__init__()
        self.session = session
        self.collection = collection

    def run_impl(self):
        """Run Collection Logger"""
        self.import_collection(self.session, self.collection)
        self.finished.emit()

    def import_collection(self, session, collection):
        """Imports a given collection into Ludopedia"""
        self.post_generic('Importando coleção...')

        for bgg_game in collection:
            data = search_ludopedia_games(session, bgg_game[0])

            if data:
                for item in data:
                    year_published = bgg_game[2]

                    if item['ano_publicacao'] == year_published:
                        id_jogo = item['id_jogo']
                        own = bgg_game[1]['own']
                        wishlist = bgg_game[1]['wishlist']
                        payload_add_game = {
                            'id_jogo': id_jogo,
                            'fl_tem': own,
                            'fl_quer': wishlist
                        }
                        session.post(LUDOPEDIA_ADD_GAME_URL, data=payload_add_game)
                        break
        self.post_generic('Coleção Importada!')

class LudopediaPlayLogger(GenericWorker):
    """Class that logs a series of BGG plays into Ludopedia"""
    finished = Signal()
    request_search = Signal(object, object)
    request_alternative = Signal(object, object)

    def __init__(self, session, plays, my_bgg_user, user_map):
        super().__init__()
        self.session = session
        self.plays = plays
        self.my_bgg_user = my_bgg_user
        self.user_map = user_map
        self.alternative = None

    def run_impl(self):
        """Run Play Logger"""
        self.import_plays(self.plays)
        self.finished.emit()

    def receive_alternative(self, alternative):
        """Receives alternative game chosen by user to use for logging"""
        self.alternative = alternative

    def clear_alternative(self):
        """Clear alternative"""
        self.alternative = None

    def get_ludopedia_match_for_game(self, bgg_play, mapped_games):
        """Gets the corresponding ludopedia game for a given BGG game"""
        if bgg_play.game_name in mapped_games:
            self.post_debug(f'Cache-mapped: {bgg_play.game_name}')
            return mapped_games[bgg_play.game_name]

        data = search_ludopedia_games(self.session, bgg_play.game_name)
        if data:
            for item in data:
                if item['ano_publicacao'] == bgg_play.year_published:
                    mapped_games[bgg_play.game_name] = item
                    self.post_debug(f'Auto-mapped: {bgg_play.game_name}')
                    return item

            self.request_alternative.emit(bgg_play, data)
            chosen_option = self.alternative
            self.clear_alternative()
            if chosen_option:
                mapped_games[bgg_play.game_name] = chosen_option
                self.post_debug(f'Manually-mapped: {bgg_play.game_name}')
                return chosen_option
            self.post_debug(f'Automatically mapping {bgg_play.game_name} to {data[0]}')
            return data[0]

        self.request_search.emit(self.session, bgg_play)
        data = self.alternative
        self.clear_alternative()
        if data:
            mapped_games[bgg_play.game_name] = data
            self.post_debug(f'Manually-mapped: {bgg_play.game_name}')
        return data

    def import_plays(self, plays):
        """Import all logged plays into Ludopedia"""
        self.post_generic('Importando partidas...')

        mapped_games = dict()
        imported_plays = 0

        for bgg_play in plays:
            found = self.get_ludopedia_match_for_game(bgg_play, mapped_games)
            if found:
                id_jogo = found['id_jogo']

                players = bgg_play.players
                payload_add_play = {
                    'id_jogo': id_jogo,
                    'dt_partida': datetime.strptime(bgg_play.date, '%Y-%m-%d').strftime('%d/%m/%Y'),
                    'qt_partidas': 1,
                    'duracao_h': int(int(bgg_play.length)/60),
                    'duracao_m': int(bgg_play.length)%60,
                    'descricao': bgg_play.comments,

                    # (name, bgguser, startposition, score, win)
                    'id_partida_jogador[]': self.get_id_partida_jogador(players),
                    'id_usuario[]': map(lambda p: get_id_usuario(p, self.user_map), players),
                    'nome[]': map(lambda p: p.name, players),
                    'fl_vencedor[]': map(lambda p: p.win, players),
                    'vl_pontos[]': map(lambda p: p.score, players),
                    'observacao[]': map(get_observacao_jogador, players)
                }
                result = self.session.post(LUDOPEDIA_ADD_PLAY_URL, data=payload_add_play)
                match_id = re.search(LUDOPEDIA_VIEW_PLAY_REGEX, result.text)
                if match_id:
                    imported_plays += 1
                else:
                    self.post_error(f'Erro ao postar partida #{bgg_play.id}'
                                    f'de {bgg_play.game_name}')

            else:
                self.post_error(f'Jogo não encontrado na Ludopedia: {bgg_play.game_name}')

        self.post_generic(f'{imported_plays}/{len(plays)} partidas importadas!')

    def get_id_partida_jogador(self, players):
        """Get id_partida for every player on a play"""
        return map(lambda p: 0 if self.my_bgg_user.lower() == p.bgg_user.lower() else '', players)

def get_id_usuario(player, ludo_users):
    """Get id_usuario for each player on a play"""
    return ludo_users.get(player.bgg_user.lower(), '')

def get_observacao_jogador(player):
    """Get extra information on a BGG player that can only be mapped to a note on Ludopedia"""
    extra_notes = []
    if player.start_position:
        extra_notes.append(f'Jogador #{player.start_position}')
    if player.color:
        extra_notes.append(f'Cor: {player.color}')
    if player.new == '1':
        extra_notes.append('(Primeira Vez)')
    return ' - '.join(extra_notes)

if __name__ == "__main__":
    ### Set-up paths if running bundled binary
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
        QCoreApplication.addLibraryPath(os.path.join(BUNDLE_DIR, "plugins"))
        ICON_PATH = os.path.join(BUNDLE_DIR, ICON_PATH)
    create_gui(ICON_PATH)
