import requests

from models import ServerStatus, WhitePageStatus


def change_server_status(server_ip: str, status: ServerStatus):
    data = {
        "server_ip": server_ip,
        "status": status
    }
    requests.patch(url="https://api.wp-generate.site/server/change_status", json=data)


def change_wp_status(domain: str, status: WhitePageStatus, complete_step=None):
    data = {
        "domain": domain,
        "status": status
    }

    if complete_step is not None:
        data['complete_step'] = complete_step

    requests.patch(url="https://api.wp-generate.site/domains/change_status", json=data)


def add_wp_creds(domain: str, login: str, password: str):
    data = {
        "domain": domain,
        "login": login,
        "password": password,
    }

    requests.patch(url="https://api.wp-generate.site/domains/wp/add_creds", json=data)