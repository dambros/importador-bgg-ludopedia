"""
Script to import data from BoardGameGeek into Ludopedia
"""

import sys
import time
from datetime import datetime
from math import ceil
import re
from xml.etree import ElementTree
from configparser import ConfigParser
from itertools import chain
from typing import NamedTuple

import colorama
import requests

BGG_API = 'https://www.boardgamegeek.com/xmlapi2/'
LUDOPEDIA_URL = 'https://www.ludopedia.com.br/'
BGG_PLAYS_PER_PAGE = int(100)

class Player(NamedTuple):
    """Represents a player in a BGG logged play"""
    name: str
    bgg_user: str
    start_position: str
    score: str
    win: bool

def start():
    """ Process input from user and import accordingly """
    colorama.init()
    print(
        "\n\n--------------***Importador BGG - Ludopedia***--------------\n\n"
        "Por favor entre abaixo as informações necessárias para importar "
        "dados do BGG para a Ludopedia\n\n")

    bgg_user = input("Username BGG: ")

    ludopedia_email = input("Email Ludopedia: ")
    ludopedia_pass = input("Password Ludopedia: ")
    (session, ludo_user_id) = login_ludopedia(ludopedia_email, ludopedia_pass)

    option = input("Importar (1) Coleção  (2) Partidas [Padrão: 1]: ")
    if option == '2':
        bgg_plays = get_bgg_plays(bgg_user)
        import_plays(session, bgg_plays, bgg_user, ludo_user_id)
    else:
        bgg_collection = get_bgg_collection(bgg_user)
        import_collection(session, bgg_collection)

    print(f'{colorama.Fore.GREEN}Importação finalizada com sucesso!\n\n')
    input("Pressione ENTER para sair")

def get_from_bgg(api_url, parameters):
    """Successively attempts to get data from BGG given an API"""
    response = requests.get(api_url, params=parameters)
    while response.status_code == 202:
        time.sleep(3)
        response = requests.get(api_url, params=parameters)
    return response

def get_bgg_collection(username):
    """Get all items in a BGG user colection"""
    print("Obtendo coleção do BGG...\n")
    collection_url = f'{BGG_API}collection'
    params = {'username': username}

    response = get_from_bgg(collection_url, params)

    collection = []
    if response.status_code == 200:
        root = ElementTree.fromstring(response.content)

        if root.tag == 'errors':
            print(f'{colorama.Fore.RED}Usuário BGG inválido, abortando...')
            sys.exit(0)
        else:
            total_jogos = root.attrib['totalitems']
            print(f'Total de jogos encontrado no BGG: {total_jogos}\n')

            for item in root.findall('item'):
                name = item.find('name').text
                status = item.find('status')
                year_published = item.find('yearpublished').text
                collection.append((name, status.attrib, year_published))

    return collection


def login_ludopedia(email, password):
    """Logins into Ludopedia manually and returns the session and user_id"""
    print("Obtendo dados do Ludopedia...\n")
    login_url = f'{LUDOPEDIA_URL}login'
    payload = {'email': email, 'pass': password}

    session = requests.Session()
    session_request = session.post(login_url, data=payload)

    if 'senha incorretos' in session_request.text:
        print(f'{colorama.Fore.RED}Não foi possível logar com as informações '
              f'fornecidas, abortando...')
        sys.exit(0)

    user_re = re.search(r'id_usuario=(\d+)', session_request.text)
    user_id = user_re.group(1) if user_re else None

    return (session, user_id)

def import_collection(session, collection):
    """Imports a given collection into Ludopedia"""
    print("Importando coleção...\n")
    ludopedia_search_url = f'{LUDOPEDIA_URL}classes/ajax/aj_search.php'
    params = {'tipo': 'jogo', 'count': 'true', 'pagina': 1, 'qt_rows': 20}

    ludopedia_add_game_url = f'{LUDOPEDIA_URL}classes/jogo_usuario_ajax.php'

    for bgg_game in collection:
        params['nm_jogo'] = bgg_game[0]
        game_request = session.get(ludopedia_search_url, params=params)
        data = game_request.json()['data']

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
                    session.post(ludopedia_add_game_url, data=payload_add_game)
                    break

def get_yearpublished_from_id(game_id):
    """Get the year that a game was published"""
    thing_url = f'{BGG_API}thing'
    params = {'id': game_id}

    response = get_from_bgg(thing_url, params)

    if response.status_code == 200:
        root = ElementTree.fromstring(response.content)
        return root.find("item").find("yearpublished").get("value")
    return None

def get_date_from_user(text, default_date):
    """Ask user for a date on the format dd/mm/aaaa"""
    date = input(f'Partidas {text} [dd/mm/aaaa, padrão: {default_date}]: ')
    try:
        datetime.strptime(date, '%d/%m/%Y')
    except ValueError:
        print(f'\nData invalida, usando o padrão {default_date}')
        date = default_date
    return date

def get_players_from_play(play):
    """Returns a list of players that took part in a game"""
    players = []
    for player in play.find('players').findall('player'):
        players.append(Player(
            name=player.get('name'),
            bgg_user=player.get('username'),
            start_position=player.get('startposition'),
            score=player.get('score'),
            win=player.get('win')
        ))
    return players

def get_bgg_plays(username):
    """Get all logged plays from a BGG user"""

    min_date = get_date_from_user(f'a partir de', datetime.today().strftime('%d/%m/%Y'))
    max_date = get_date_from_user(f'até', min_date)

    has_more = True
    page = 1
    total_pages = 1
    plays = []
    while has_more:
        plays_url = f'{BGG_API}plays'
        params = {
            'username': username,
            'page': page,
            'mindate': datetime.strptime(min_date, '%d/%m/%Y').strftime('%Y-%m-%d'),
            'maxdate': datetime.strptime(max_date, '%d/%m/%Y').strftime('%Y-%m-%d')
        }

        response = get_from_bgg(plays_url, params)

        if response.status_code == 200:
            root = ElementTree.fromstring(response.content)

            if root.text is not None and root.text.strip() == 'Invalid object or user':
                print(f'{colorama.Fore.RED}Usuário BGG inválido, abortando...')
                sys.exit(0)
            else:
                if page == 1:
                    total_partidas = root.get('total')
                    total_pages = ceil(int(total_partidas)/BGG_PLAYS_PER_PAGE)
                    print(f'Total de partidas encontradas no BGG: {total_partidas}\n')

                print(f'Obtendo partidas do BGG, página {page}/{total_pages}')

                for play in root.findall('play'):
                    date = play.get('date')
                    length = play.get('length')
                    location = play.get('location')

                    game = play.findall('item')[0]
                    game_name = game.get('name')
                    year_published = get_yearpublished_from_id(game.get('objectid'))

                    comments_element = play.find('comments')
                    comments = comments_element.text if comments_element is not None else None

                    players = get_players_from_play(play)

                    # sort players, me first
                    players.sort(key=lambda p: (p[1] != username, p[2]))

                    plays.append((date, length, location, game_name,
                                  year_published, comments, players))

                print(f'Total de partidas importadas: {len(plays)}\n')

                if len(plays) >= int(total_partidas):
                    has_more = False
                else:
                    page += 1

    return plays

def import_plays(session, plays, my_bgg_user, ludo_user_id):
    """Import all logged plays into Ludopedia"""
    print("Importando partidas...\n")
    ludopedia_search_url = f'{LUDOPEDIA_URL}classes/ajax/aj_search.php'
    params = {'tipo': 'jogo', 'count': 'true', 'pagina': 1, 'qt_rows': 20}

    ludopedia_add_play_url = f'{LUDOPEDIA_URL}cadastra_partida'

    try:
        parser = ConfigParser()
        with open("usuarios.txt") as lines:
            lines = chain(("[top]",), lines)
            parser.read_file(lines)
            ludo_users = dict(parser['top'])
    except FileNotFoundError:
        ludo_users = {}

    for bgg_play in plays:
        # Location is not available in Ludopedia so it is not used here
        (date, length, _, game_name, year_published, comments, players) = bgg_play

        params['nm_jogo'] = game_name
        game_request = session.get(ludopedia_search_url, params=params)
        data = game_request.json()['data']

        if data:
            found = None

            for item in data:
                if item['ano_publicacao'] == year_published:
                    found = item
                    break

            if not found:
                print(f'Nenhum jogo encontrado no ano de lançamento: {game_name} {year_published}')

                found = data[0]
                print(f"Importando o primeiro resultado: "
                      f"{found['nm_jogo']} {found['ano_publicacao']}\n")

            id_jogo = found['id_jogo']

            payload_add_play = {
                'id_jogo': id_jogo,
                'dt_partida': datetime.strptime(date, '%Y-%m-%d').strftime('%d/%m/%Y'),
                'qt_partidas': 1,
                'duracao_h': int(int(length)/60),
                'duracao_m': int(length)%60,
                'descricao': comments,

                # (name, bgguser, startposition, score, win)
                'id_partida_jogador[]': map(lambda p: 0 if my_bgg_user.lower() == p.bgg_user.lower() else '', players),
                'id_usuario[]': map(lambda p: ludo_user_id if my_bgg_user.lower() == p.bgg_user.lower() else ludo_users.get(p.bgg_user, ''), players),
                'nome[]': map(lambda p: p.name, players),
                'fl_vencedor[]': map(lambda p: p.win, players),
                'vl_pontos[]': map(lambda p: p.score, players),
                'observacao[]': map(lambda p: f'Jogador {p.start_position}', players)
            }
            session.post(ludopedia_add_play_url, data=payload_add_play)

        else:
            print(f'Jogo não encontrado na Ludopedia: {game_name}')

if __name__ == "__main__":
    start()
