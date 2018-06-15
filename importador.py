import sys
import time
import datetime
from xml.etree import ElementTree

import colorama
import requests

BGG_API = 'https://www.boardgamegeek.com/xmlapi2/'
LUDOPEDIA_URL = 'https://www.ludopedia.com.br/'


def start():
    colorama.init()
    print(
        "\n\n--------------***Importador BGG - Ludopedia***--------------\n\n"
        "Por favor entre abaixo as informações necessárias para importar "
        "uma coleção do BGG para a Ludopedia\n\n")

    bgg_user = input("Username BGG: ")
    ludopedia_email = input("Email Ludopedia: ")
    ludopedia_pass = input("Password Ludopedia: ")

    bgg_collection = get_bgg_collection(bgg_user)
    session = login_ludopedia(ludopedia_email, ludopedia_pass)
    import_collection(session, bgg_collection)

    print(colorama.Fore.GREEN + 'Importação finalizada com sucesso!\n\n')
    input("Pressione ENTER para sair")

def start2():
    colorama.init()
    print(
        "\n\n--------------***Importador BGG - Ludopedia***--------------\n\n"
        "Por favor entre abaixo as informações necessárias para importar "
        "uma lista de partidas do BGG para a Ludopedia\n\n")

    bgg_user = input("Username BGG: ")
    ludopedia_email = input("Email Ludopedia: ")
    ludopedia_pass = input("Password Ludopedia: ")

    bgg_plays = get_bgg_plays(bgg_user)
    session = login_ludopedia(ludopedia_email, ludopedia_pass)
    import_plays(session, bgg_plays)

    print(colorama.Fore.GREEN + 'Importação finalizada com sucesso!\n\n')
    input("Pressione ENTER para sair")


def get_bgg_collection(username):
    print("Obtendo coleção do BGG...\n")
    collection_url = '{}{}'.format(BGG_API, 'collection')
    params = {'username': username}

    response = requests.get(collection_url, params=params)
    while response.status_code == 202:
        time.sleep(3)
        response = requests.get(collection_url, params=params)

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

    return session


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

def get_bgg_plays(username):
    print("Obtendo partidas do BGG...\n")
    plays_url = '{}{}'.format(BGG_API, 'plays')
    params = {'username': username}
    # TODO plays has pagination, loop through all pages (100 plays per page)

    response = requests.get(plays_url, params=params)
    while response.status_code == 202:
        time.sleep(3)
        response = requests.get(plays_url, params=params)

    plays = []
    if response.status_code == 200:
        root = ElementTree.fromstring(response.content)

        if root.tag == 'errors':
            print(colorama.Fore.RED + 'Usuário BGG inválido, abortando...')
            sys.exit(0)
        else:
            total_partidas = root.attrib['total']
            print('Total de partidas encontradas no BGG: {}\n'.format(total_partidas))

            for play in root.findall('play'):
                date = play.get('date')
                length = play.get('length')
                location = play.get('location')

                gameName = play.findall('item')[0].get('name')

                commentsEl = play.find('comments')
                comments = commentsEl.text if commentsEl != None else None

                players = []
                for player in play.find('players').findall('player'):
                    name = player.get('name')
                    username = player.get('username')
                    startposition = player.get('startposition')
                    score = player.get('score')
                    win = player.get('win')
                    players.append((name, username, startposition, score, win))

                plays.append((date, length, location, gameName, comments, players))

    return plays

def import_plays(session, plays):
    print("Importando partidas...\n")
    ludopedia_search_url = '{}{}'.format(LUDOPEDIA_URL,
                                         'classes/ajax/aj_search.php')
    params = {'tipo': 'jogo', 'count': 'true', 'pagina': 1, 'qt_rows': 20}

    ludopedia_add_play_url = '{}{}'.format(LUDOPEDIA_URL,
                                           'cadastra_partida')

    for bgg_play in plays:
        (date, length, location, gameName, comments, players) = bgg_play

        params['nm_jogo'] = gameName
        r = session.get(ludopedia_search_url, params=params)
        data = r.json()['data']

        if data:
            for item in data:
                # TODO Check year published
                #year_published = bgg_play[2]

                if 1==1:#item['ano_publicacao'] == year_published:
                    id_jogo = item['id_jogo']
                    # TODO get MY_ID automatically
                    MY_ID = 52973

                    payload_add_play = {
                        'id_jogo': id_jogo,
                        'dt_partida': datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%d/%m/%y'),
                        'qt_partidas': 1,
                        'duracao_h': int(int(length)/60),
                        'duracao_m': int(length)%60,
                        'descricao': comments,

                        # (name, username, startposition, score, win)
                        # TODO not very clear what id_partida_jogador does
                        'id_partida_jogador[]': map(lambda p: 0 if p[1] == "renatoat" else '', players),
                        'id_usuario[]': map(lambda p: MY_ID if p[1] == "renatoat" else None, players),
                        'nome[]': map(lambda p: p[0], players),
                        'fl_vencedor[]': map(lambda p: p[4], players),
                        'vl_pontos[]': map(lambda p: p[3], players),
                        'observacao[]': map(lambda p: 'Jogador {}{}{}'.format(p[2], ', usuário BGG ' if p[1] else '', p[1]), players)
                    }
                    break

if __name__ == "__main__":
    start2()
