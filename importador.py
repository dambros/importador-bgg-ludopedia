import sys
import time
from datetime import datetime
import re
from xml.etree import ElementTree
from configparser import ConfigParser
from itertools import chain

import colorama
import requests

BGG_API = 'https://www.boardgamegeek.com/xmlapi2/'
LUDOPEDIA_URL = 'https://www.ludopedia.com.br/'


def start():
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

    print(colorama.Fore.GREEN + 'Importação finalizada com sucesso!\n\n')
    input("Pressione ENTER para sair")

def get_from_bgg(api_url, parameters):
    response = requests.get(api_url, params=parameters)
    while response.status_code == 202:
        time.sleep(3)
        response = requests.get(api_url, params=parameters)
    return response

def get_bgg_collection(username):
    print("Obtendo coleção do BGG...\n")
    collection_url = '{}{}'.format(BGG_API, 'collection')
    params = {'username': username}

    response = get_from_bgg(collection_url, params)

    collection = []
    if response.status_code == 200:
        root = ElementTree.fromstring(response.content)

        if root.tag == 'errors':
            print(colorama.Fore.RED + 'Usuário BGG inválido, abortando...')
            sys.exit(0)
        else:
            total_jogos = root.attrib['totalitems']
            print('Total de jogos encontrado no BGG: {}\n'.format(total_jogos))

            for item in root.findall('item'):
                name = item.find('name').text
                status = item.find('status')
                year_published = item.find('yearpublished').text
                collection.append((name, status.attrib, year_published))

    return collection


def login_ludopedia(email, password):
    print("Obtendo dados do Ludopedia...\n")
    login_url = '{}{}'.format(LUDOPEDIA_URL, 'login')
    payload = {'email': email, 'pass': password}

    session = requests.Session()
    r = session.post(login_url, data=payload)

    if 'senha incorretos' in r.text:
        print(colorama.Fore.RED + 'Não foi possível logar com as informações '
                                  'fornecidas, abortando...')
        sys.exit(0)

    user_re = re.search(r'id_usuario=(\d+)', r.text)
    user_id = user_re.group(1) if user_re else None

    return (session, user_id)

def import_collection(session, collection):
    print("Importando coleção...\n")
    ludopedia_search_url = '{}{}'.format(LUDOPEDIA_URL,
                                         'classes/ajax/aj_search.php')
    params = {'tipo': 'jogo', 'count': 'true', 'pagina': 1, 'qt_rows': 20}

    ludopedia_add_game_url = '{}{}'.format(LUDOPEDIA_URL,
                                           'classes/jogo_usuario_ajax.php')

    for bgg_game in collection:
        params['nm_jogo'] = bgg_game[0]
        r = session.get(ludopedia_search_url, params=params)
        data = r.json()['data']

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

def get_yearpublished_from_id(id):
    thing_url = f'{BGG_API}thing'
    params = {'id': id}

    response = get_from_bgg(thing_url, params)

    if response.status_code == 200:
        root = ElementTree.fromstring(response.content)
        return root.find("item").find("yearpublished").get("value")

def get_bgg_plays(username):
    has_more = True
    page = 0
    plays = []

    today = datetime.today().strftime('%d/%m/%Y')

    min_date = input(f'Partidas a partir de [dd/mm/aaaa, padrão: {today}]: ')

    try:
        datetime.strptime(min_date, '%d/%m/%Y')
    except ValueError:
        print(f'\nData invalida, usando o padrão {today}')
        min_date = today

    max_date = input(f'Partidas até [dd/mm/aaaa, padrão: {min_date}]: ')

    try:
        datetime.strptime(max_date, '%d/%m/%Y')
    except ValueError:
        print(f'\nData invalida, usando o padrão {min_date}')
        max_date = min_date

    while has_more:
        page += 1

        print(f'\nObtendo partidas do BGG, página {page}\n')
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

            if root.text != None and root.text.strip() == 'Invalid object or user':
                print(colorama.Fore.RED + 'Usuário BGG inválido, abortando...')
                sys.exit(0)
            else:
                total_partidas = root.get('total')
                print(f'Total de partidas encontradas no BGG: {total_partidas}\n')

                for play in root.findall('play'):
                    date = play.get('date')
                    length = play.get('length')
                    location = play.get('location')

                    game = play.findall('item')[0]
                    game_name = game.get('name')
                    year_published = get_yearpublished_from_id(game.get('objectid'))

                    commentsEl = play.find('comments')
                    comments = commentsEl.text if commentsEl != None else None

                    players = []
                    for player in play.find('players').findall('player'):
                        name = player.get('name')
                        bgguser = player.get('username')
                        startposition = player.get('startposition')
                        score = player.get('score')
                        win = player.get('win')
                        players.append((name, bgguser, startposition, score, win))

                    # sort players, me first
                    players.sort(key=lambda p: (p[1] != username, p[2]))

                    plays.append((date, length, location, game_name, year_published, comments, players))

                print(f'Total de partidas importadas: {len(plays)}\n')

                if len(plays) >= int(total_partidas):
                    has_more = False

    return plays

def import_plays(session, plays, my_bgg_user, ludo_user_id):
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
        (date, length, location, game_name, year_published, comments, players) = bgg_play

        params['nm_jogo'] = game_name
        r = session.get(ludopedia_search_url, params=params)
        data = r.json()['data']

        if data:
            found = None

            for item in data:
                if item['ano_publicacao'] == year_published:
                    found = item
                    break

            if not found:
                print(f'Nenhum jogo encontrado no ano de lançamento: {game_name} {year_published}')

                found = data[0]
                print(f"Importando o primeiro resultado: {found['nm_jogo']} {found['ano_publicacao']}\n")

            id_jogo = found['id_jogo']

            payload_add_play = {
                'id_jogo': id_jogo,
                'dt_partida': datetime.strptime(date, '%Y-%m-%d').strftime('%d/%m/%Y'),
                'qt_partidas': 1,
                'duracao_h': int(int(length)/60),
                'duracao_m': int(length)%60,
                'descricao': comments,

                # (name, bgguser, startposition, score, win)
                'id_partida_jogador[]': map(lambda p: 0 if my_bgg_user == p[1] else '', players),
                'id_usuario[]': map(lambda p: ludo_user_id if my_bgg_user == p[1] else ludo_users.get(p[1], ''), players),
                'nome[]': map(lambda p: p[0], players),
                'fl_vencedor[]': map(lambda p: p[4], players),
                'vl_pontos[]': map(lambda p: p[3], players),
                'observacao[]': map(lambda p: f'Jogador {p[2]}', players)
            }
            session.post(ludopedia_add_play_url, data=payload_add_play)

        else:
            print(f'Jogo não encontrado na Ludopedia: {game_name}')

if __name__ == "__main__":
    start()
