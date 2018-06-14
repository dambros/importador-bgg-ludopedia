import sys
import time
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

    session = requests.Session()
    bgg_user = input("Username BGG: ")
    ludopedia_email = input("Email Ludopedia: ")
    ludopedia_pass = input("Password Ludopedia: ")

    bgg_collection = get_bgg_collection(bgg_user)
    login_ludopedia(session, ludopedia_email, ludopedia_pass)
    export_collection(session, bgg_collection)

    print(colorama.Fore.GREEN + 'Importação finalizada com sucesso!\n\n')


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
            raise ValueError('Usuário inválido, abortando...')
        else:
            total_jogos = root.attrib['totalitems'];
            print('Total de jogos encontrado no BGG: {}\n'.format(total_jogos))

            for item in root.findall('item'):
                name = item.find('name').text
                status = item.find('status')
                year = item.find('yearpublished').text
                collection.append((name, status.attrib, year))

    return collection


def login_ludopedia(session, email, password):
    print("Obtendo dados do Ludopedia...\n")
    login_url = '{}{}'.format(LUDOPEDIA_URL, 'login')
    payload = {'email': email, 'pass': password}

    r = session.post(login_url, data=payload)

    if 'senha incorretos' in r.text:
        print(colorama.Fore.RED + 'Não foi possível logar com as informações '
                                  'fornecidas, abortando...')
        sys.exit(0)


def export_collection(session, collection):
    print("Importando coleção...\n")
    ludopedia_search_url = '{}{}'.format(LUDOPEDIA_URL,
                                         'classes/ajax/aj_search.php')
    params = {'tipo': 'jogo', 'count': 'true', 'pagina': 1, 'qt_rows': 10}

    ludopedia_add_game_url = '{}{}'.format(LUDOPEDIA_URL,
                                           'classes/jogo_usuario_ajax.php')

    for game in collection:
        params['nm_jogo'] = game[0]
        r = session.get(ludopedia_search_url, params=params)
        data = r.json()['data']

        if data:
            jogo = data[0]
            year = game[2]

            if jogo['ano_publicacao'] == year:
                id_jogo = jogo['id_jogo']
                own = game[1]['own']
                wishlist = game[1]['wishlist']
                payload_add_game = {
                    'id_jogo': id_jogo,
                    'fl_tem': own,
                    'fl_quer': wishlist
                }
                session.post(ludopedia_add_game_url, data=payload_add_game)


if __name__ == "__main__":
    start()
