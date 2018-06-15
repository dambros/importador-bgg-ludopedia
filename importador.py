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

    bgg_user = input("Username BGG: ")
    ludopedia_email = input("Email Ludopedia: ")
    ludopedia_pass = input("Password Ludopedia: ")

    bgg_collection = get_bgg_collection(bgg_user)
    session = login_ludopedia(ludopedia_email, ludopedia_pass)
    import_collection(session, bgg_collection)

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


if __name__ == "__main__":
    start()
