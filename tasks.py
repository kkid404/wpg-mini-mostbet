import asyncio
import os
import re
import string
import csv
import smtplib
from datetime import datetime, timedelta

import requests
import urllib.request
import paramiko
import random
from celery import Celery
from openai import OpenAI
from fastapi import HTTPException
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from io import StringIO
from models import ServerStatus, Server, Domain, WhitePageStatus
from tools.certbot import generate_lets_encrypt_cert, configure_ssl_in_apache
from tools.config import config_read
from tools.system_func import change_wp_status, change_server_status, add_wp_creds

config = config_read("config.ini")
celery = Celery('tasks', broker='redis://localhost:6379')

client = OpenAI(
    api_key=config.get('OPENAI', 'apikey'),
)


@celery.task
def configure_server(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            password=server_password,
            port=server_port
        )

        # Генерация ключей на локальном сервере
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        public_key_path = private_key_path + ".pub"
        if not os.path.exists(private_key_path):
            os.system(f"ssh-keygen -t rsa -b 4096 -f {private_key_path} -q -N ''")

        # Чтение публичного ключа
        with open(public_key_path, 'r') as f:
            public_key = f.read()

        # Добавление публичного ключа на сервер
        ssh.exec_command("mkdir -p ~/.ssh && chmod 700 ~/.ssh")
        ssh.exec_command(f"echo '{public_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys")

        ssh.close()

        # Проверка подключения по ключу
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )
        print(f"Successfully connected to {server_ip} using SSH key.")

        commands = [
            "dnf update -y >/dev/null 2>&1",
            "setenforce 0",
            "dnf install wget -y >/dev/null 2>&1",
            "dnf install httpd httpd-tools -y >/dev/null 2>&1",
            "systemctl start httpd >/dev/null 2>&1",
            "systemctl enable httpd >/dev/null 2>&1",
            "dnf install firewalld -y >/dev/null 2>&1",
            "systemctl start firewalld >/dev/null 2>&1",
            "systemctl enable firewalld >/dev/null 2>&1",
            "firewall-cmd --permanent --add-service=http >/dev/null 2>&1",
            "firewall-cmd --permanent --add-port=61208/tcp >/dev/null 2>&1",
            "systemctl reload firewalld >/dev/null 2>&1",
            "dnf install mysql-server -y >/dev/null 2>&1",
            "systemctl start mysqld >/dev/null 2>&1",
            "systemctl enable mysqld >/dev/null 2>&1",
            f"""mysql -e "DELETE FROM mysql.user WHERE User='';" """,
            f"""mysql -e "DROP DATABASE test;" """,
            f"""mysql -e "DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';" """,
            f"""mysql -e "FLUSH PRIVILEGES;" """,
            "dnf install php php-mysqlnd php-cli php-curl php-gd php-xml php-mbstring -y >/dev/null 2>&1",
            "systemctl restart httpd >/dev/null 2>&1",
            "curl -O https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar >/dev/null 2>&1",
            "php wp-cli.phar --info >/dev/null 2>&1",
            "chmod +x wp-cli.phar",
            "mv wp-cli.phar /usr/local/bin/wp",
            "dnf install -y epel-release --nogpgcheck",
            "dnf install -y certbot python3-certbot-apache --nogpgcheck",
            "dnf install -y glances",
            "tee /etc/systemd/system/glances.service > /dev/null <<EOL\n"
            "[Unit]\n"
            "Description=Glances in Web Server Mode\n"
            "After=network.target\n\n"
            "[Service]\n"
            "ExecStart=/usr/bin/glances -w --bind 0.0.0.0\n"
            "Restart=on-failure\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
            "EOL",
            "systemctl daemon-reload",
            "systemctl enable glances.service",
            "systemctl start glances.service",
        ]

        # Установка WP-CLI
        for command in commands:
            print(command)
            stdin, stdout, stderr = ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def generate_private_key(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            password=server_password,
            port=server_port
        )

        # Генерация ключей на локальном сервере
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        public_key_path = private_key_path + ".pub"
        if not os.path.exists(private_key_path):
            os.system(f"ssh-keygen -t rsa -b 4096 -f {private_key_path} -q -N ''")

        # Чтение публичного ключа
        with open(public_key_path, 'r') as f:
            public_key = f.read()

        # Добавление публичного ключа на сервер
        ssh.exec_command("mkdir -p ~/.ssh && chmod 700 ~/.ssh")
        ssh.exec_command(f"echo '{public_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys")

        ssh.close()

        # Проверка подключения по ключу
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )
        print(f"Successfully connected to {server_ip} using SSH key.")

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def install_certbot(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )
        print(f"Successfully connected to {server_ip} using SSH key.")

        commands = [
            "dnf install -y epel-release --nogpgcheck",
            "dnf install -y certbot python3-certbot-apache --nogpgcheck"
        ]

        for command in commands:
            print(command)
            stdin, stdout, stderr = ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def install_wpcli(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )
        print(f"Successfully connected to {server_ip} using SSH key.")

        commands = [
            "curl -O https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar >/dev/null 2>&1",
            "php wp-cli.phar --info >/dev/null 2>&1",
            "chmod +x wp-cli.phar",
            "mv wp-cli.phar /usr/local/bin/wp"
        ]

        for command in commands:
            print(command)
            stdin, stdout, stderr = ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def reboot_system(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )
        print(f"Successfully connected to {server_ip} using SSH key.")

        stdin, stdout, stderr = ssh.exec_command(f"shutdown -r")
        stdout.channel.recv_exit_status()

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def selinux_off(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )
        print(f"Successfully connected to {server_ip} using SSH key.")

        stdin, stdout, stderr = ssh.exec_command(f"setenforce 0")
        stdout.channel.recv_exit_status()

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def delete_posts(domain, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        stdin, stdout, stderr = ssh.exec_command(f"wp post delete "
                                                 f"$(wp post list --post_type=post --format=ids "
                                                 f"--path=/var/www/{domain}) "
                                                 f"--path=/var/www/{domain} --force --allow-root")
        stdout.channel.recv_exit_status()

        change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring domain {domain}: {e}")
    finally:
        ssh.close()


@celery.task
def install_wordpress(domain, keyword, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        db_name = db_user = domain.replace('.', '_').replace('-', '_')
        db_password = generate_random_password()

        commands = [
            f"mysql -e 'CREATE DATABASE {db_name};'",
            f"mysql -e 'CREATE USER \"{db_user}\"@\"localhost\" IDENTIFIED BY \"{db_password}\";'",
            f"mysql -e 'GRANT ALL PRIVILEGES ON {db_name}.* TO \"{db_user}\"@\"localhost\";'",
            f"mysql -e 'FLUSH PRIVILEGES;'",
            f"""{wp_cli_path} core download --path=/var/www/{domain}""",
            f"""{wp_cli_path} config create --dbname={db_name} --dbuser={db_user} --dbpass={db_password} --path=/var/www/{domain}""",
        ]

        for command in commands:
            print(command)
            stdin, stdout, stderr = ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()  # Дожидаемся завершения команды
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')

            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)  # Логирование вывода команды, можно заменить на логгер

        set_fs_method_command = f"{wp_cli_path} config set FS_METHOD 'direct' --path=/var/www/{domain}"
        stdin, stdout, stderr = ssh.exec_command(set_fs_method_command)
        stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        print(output)
        print(error)

        set_disallow_file_edit = f"{wp_cli_path} config set DISALLOW_FILE_EDIT true --raw --path=/var/www/{domain}"
        stdin, stdout, stderr = ssh.exec_command(set_disallow_file_edit)
        stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        print(output)
        print(error)

        # Создание файла .htaccess
        htaccess_content = "# BEGIN WordPress\n<IfModule mod_rewrite.c>\nRewriteEngine On\nRewriteBase /" \
                           "\nRewriteRule ^index\\.php$ - [L]\nRewriteCond %{REQUEST_FILENAME} !-f" \
                           "\nRewriteCond %{REQUEST_FILENAME} !-d\nRewriteRule . /index.php [L]" \
                           "\n</IfModule>\n# END WordPress\n\n<Files wp-config.php>\norder allow,deny\ndeny from all\n" \
                           "</Files>\n\n<Files .htaccess>\norder allow,deny\ndeny from all\n</Files>"

        ssh.exec_command(f"""bash -c 'echo "{htaccess_content}" > /var/www/{domain}/.htaccess'""")

        # Установка WordPress
        random_title = generate_random_title(keyword)
        random_title = random_title.replace("\"", '')
        admin_user = generate_nickname()
        admin_password = generate_random_password()
        add_wp_creds(domain, admin_user, admin_password)

        install_command = f"""{wp_cli_path} core install --url={domain} --title="{random_title}" --admin_user={admin_user} --admin_password={admin_password} --admin_email=admin@{domain} --path=/var/www/{domain}"""
        stdin, stdout, stderr = ssh.exec_command(install_command)
        stdout.channel.recv_exit_status()

        ssh.exec_command(f'{wp_cli_path} post delete 1 --force --allow-root --path=/var/www/{domain}')
        ssh.exec_command(f'{wp_cli_path} post delete 2 --force --allow-root --path=/var/www/{domain}')

        try:
            get_category_id_command = f"{wp_cli_path} term list category --name=Uncategorized --field=term_id --allow-root --path=/var/www/{domain}"
            stdin, stdout, stderr = ssh.exec_command(get_category_id_command)
            stdout.channel.recv_exit_status()
            category_id = stdout.read().decode('utf-8').strip()

            if category_id:
                rename_category_command = f"{wp_cli_path} term update category {category_id} --name='Articles' --slug='articles' --allow-root --path=/var/www/{domain}"
                stdin, stdout, stderr = ssh.exec_command(rename_category_command)
                stdout.channel.recv_exit_status()
                print(f"Category 'Uncategorized' renamed to 'Articles'.")
            else:
                print("Category 'Uncategorized' or 'Uncategorised' not found. ")
        except Exception as e:
            print(f"Error while renaming category: {e}")

        print("Создаю страницу контактов")
        about_us_content = generate_about_us_page(domain)

        stdin, stdout, stderr = ssh.exec_command(f'{wp_cli_path} post create --post_type=page --post_title="About Us" --post_content="{about_us_content}" --post_status=publish --allow-root')
        stdout.channel.recv_exit_status()

        print("меняю статус")
        change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def newadmin_wordpress(domain, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        admin_user = generate_nickname()
        admin_password = generate_random_password()
        add_wp_creds(domain, admin_user, admin_password)

        install_command = f"""{wp_cli_path} user create {admin_user} {admin_user}@{domain} --role=administrator --user_pass={admin_password} --path=/var/www/{domain}"""
        stdin, stdout, stderr = ssh.exec_command(install_command)
        stdout.channel.recv_exit_status()

        print("меняю статус")
        change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def configure_http(domain, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        configure_http_in_apache(ssh, domain)

        change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def restart_apache(server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        # Перезапуск Apache для применения конфигурации
        stdin, stdout, stderr = ssh.exec_command("systemctl restart httpd")
        stdout.channel.recv_exit_status()  # Дождаться завершения команды

        # Логирование вывода и ошибок
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')

        if error:
            print(f"Error restarting Apache: {error}")
            change_server_status(server_ip, ServerStatus.ERROR)
        else:
            print("Apache restarted successfully.")
            change_server_status(server_ip, ServerStatus.ADDED)

    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def install_plugins(domain, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        deactivate_all_plugins_command = f"{wp_cli_path} plugin deactivate --all --path=/var/www/{domain} --allow-root"
        stdin, stdout, stderr = ssh.exec_command(deactivate_all_plugins_command)
        stdout.channel.recv_exit_status()
        print("Deactivate all plugins output:", stdout.read().decode('utf-8'))

        # Удаление всех плагинов
        delete_all_plugins_command = f"{wp_cli_path} plugin delete --all --path=/var/www/{domain} --allow-root"
        stdin, stdout, stderr = ssh.exec_command(delete_all_plugins_command)
        stdout.channel.recv_exit_status()
        print("Delete all plugins output:", stdout.read().decode('utf-8'))

        # Установка необходимых плагинов
        plugins = ['wp-smushit', 'wordpress-seo', 'cookie-notice', 'contact-form-7',
                   'jetpack', 'wp-simple-firewall']
        for plugin in plugins:
            try:
                install_plugin_command = f"{wp_cli_path} plugin install {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(install_plugin_command)
                stdout.channel.recv_exit_status()
                install_output = stdout.read().decode('utf-8')
                print(f"Plugin install output for {plugin}:", install_output)

                # Активация плагина
                activate_plugin_command = f"{wp_cli_path} plugin activate {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(activate_plugin_command)
                stdout.channel.recv_exit_status()
                activate_output = stdout.read().decode('utf-8')
                print(f"Plugin activation output for {plugin}:", activate_output)

                # Проверка активации плагина
                check_activation_command = f"{wp_cli_path} plugin is-active {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(check_activation_command)
                stdout.channel.recv_exit_status()
                is_active = stdout.read().decode('utf-8').strip()

                if "active" not in is_active:
                    print(f"{plugin} is not active, reactivating...")
                    stdin, stdout, stderr = ssh.exec_command(activate_plugin_command)
                    stdout.channel.recv_exit_status()
                    print(f"Reactivation output for {plugin}:", stdout.read().decode('utf-8'))

                init_plugins = """
                        wp eval "do_action('init'); do_action('wp_loaded');"
                        """
                stdin, stdout, stderr = ssh.exec_command(init_plugins)
                stdout.channel.recv_exit_status()

            except:
                print(f"Plugin not activated {plugin}")
                continue

        change_wp_status(domain, WhitePageStatus.DONE, complete_step="plugins_installed")
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def multi_install_plugin(domains, plugin, server_ip, server_login, server_password, server_port):
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        for domain in domains:
            change_wp_status(domain, WhitePageStatus.CONFIGURE)
            try:
                install_plugin_command = f"{wp_cli_path} plugin install {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(install_plugin_command)
                stdout.channel.recv_exit_status()
                install_output = stdout.read().decode('utf-8')
                print(f"Plugin install output for {plugin}:", install_output)

                # Активация плагина
                activate_plugin_command = f"{wp_cli_path} plugin activate {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(activate_plugin_command)
                stdout.channel.recv_exit_status()
                activate_output = stdout.read().decode('utf-8')
                print(f"Plugin activation output for {plugin}:", activate_output)

                # Проверка активации плагина
                check_activation_command = f"{wp_cli_path} plugin is-active {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(check_activation_command)
                stdout.channel.recv_exit_status()
                is_active = stdout.read().decode('utf-8').strip()

                if "active" not in is_active:
                    print(f"{plugin} is not active, reactivating...")
                    stdin, stdout, stderr = ssh.exec_command(activate_plugin_command)
                    stdout.channel.recv_exit_status()
                    print(f"Reactivation output for {plugin}:", stdout.read().decode('utf-8'))

                init_plugins = """
                                        wp eval "do_action('init'); do_action('wp_loaded');"
                                        """
                stdin, stdout, stderr = ssh.exec_command(init_plugins)
                stdout.channel.recv_exit_status()

            except:
                print(f"Plugin not installed {plugin}")
                change_wp_status(domain, WhitePageStatus.ERROR)
                continue

            change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:

        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def multi_delete_plugin(domains, plugin, server_ip, server_login, server_password, server_port):

    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        for domain in domains:
            change_wp_status(domain, WhitePageStatus.CONFIGURE)
            try:
                deactivate_plugin_command = f"{wp_cli_path} plugin deactivate {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(deactivate_plugin_command)
                stdout.channel.recv_exit_status()
                install_output = stdout.read().decode('utf-8')
                print(f"Plugin deactivate output for {plugin}:", install_output)

                delete_plugin_command = f"{wp_cli_path} plugin delete {plugin} --path=/var/www/{domain} --allow-root"
                stdin, stdout, stderr = ssh.exec_command(delete_plugin_command)
                stdout.channel.recv_exit_status()
                activate_output = stdout.read().decode('utf-8')
                print(f"Plugin delete output for {plugin}:", activate_output)

            except:
                print(f"Plugin not removed {plugin}")
                change_wp_status(domain, WhitePageStatus.ERROR)
                continue

            change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:

        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def change_theme(domain, theme_slug, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        # Установка выбранной темы
        install_theme_command = f"{wp_cli_path} theme install {theme_slug} --activate --path=/var/www/{domain} --allow-root"
        stdin, stdout, stderr = ssh.exec_command(install_theme_command)
        stdout.channel.recv_exit_status()
        print(stdout, stderr)

        change_wp_status(domain, WhitePageStatus.DONE, complete_step="theme_changed")
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def create_posts(domain, keyword, posts_count, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"
        base_date = datetime.now()

        for _ in range(posts_count):
            try:
                post_title, post_content, image_url = generate_post_content(keyword)
                post_title = post_title.replace("\"", '').replace("\'", '')
                post_content = post_content.replace("\"", "\'")

                image_name = f"{keyword}_{random.randint(1,99999)}.jpg"

                # Загрузка изображения в WordPress
                local_image_path = f"/tmp/{image_name}"  # Локальный путь для сохранения изображения
                urllib.request.urlretrieve(image_url, local_image_path)  # Скачиваем изображение

                # Загружаем изображение на сервер через SSH
                sftp = ssh.open_sftp()
                remote_image_path = f"/var/www/{domain}/wp-content/uploads/{image_name}"
                sftp.put(local_image_path, remote_image_path)
                sftp.close()

                # Добавление изображения в WordPress
                upload_image_command = (
                    f'{wp_cli_path} media import "{remote_image_path}" --path=/var/www/{domain} --porcelain --allow-root'
                )
                stdin, stdout, stderr = ssh.exec_command(upload_image_command)
                stdout.channel.recv_exit_status()
                attachment_id = stdout.read().decode('utf-8').strip()  # Получаем ID изображения

                base_date = post_date = generate_random_date(base_date, 5)
                post_date = post_date.strftime('%Y-%m-%d %H:%M:%S')

                # Публикация поста без миниатюры
                create_post_command = (
                    f'{wp_cli_path} post create '
                    f'--post_title="{post_title}" '
                    f'--post_content="{post_content}" '
                    f'--post_status=publish '
                    f'--post_type=post '
                    f'--path=/var/www/{domain} '
                    f'--post_date="{post_date}" '
                    f'--porcelain --allow-root'
                )
                stdin, stdout, stderr = ssh.exec_command(create_post_command)
                stdout.channel.recv_exit_status()
                error_message = stderr.read().decode('utf-8').strip()
                if error_message:
                    print(f"Error from wp-cli: {error_message}")

                post_id = stdout.read().decode('utf-8').strip()  # Получаем ID поста
                print(post_id)

                if post_id.isdigit():
                    # Установка миниатюры (featured image) для поста
                    set_thumbnail_command = (
                        f'{wp_cli_path} post meta set {post_id} _thumbnail_id {attachment_id} --path=/var/www/{domain} --allow-root'
                    )
                    ssh.exec_command(set_thumbnail_command)
                    print(f"Post titled '{post_title}' created successfully with image ID {attachment_id}.")
                else:
                    print(f"Failed to create post for '{post_title}'.")
            except Exception as e:
                print(f"Error while creating post: {e}")
                continue

        change_wp_status(domain, WhitePageStatus.DONE, complete_step="posts_created")
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def add_form(domain, keyword, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        wp_cli_path = "/usr/local/bin/wp"

        # Получаем текущий активный файл functions.php
        get_functions_php_path = (
            f'{wp_cli_path} eval "echo get_template_directory() . \'/functions.php\';" --path=/var/www/{domain} --allow-root'
        )
        stdin, stdout, stderr = ssh.exec_command(get_functions_php_path)
        stdout.channel.recv_exit_status()
        functions_php_path = stdout.read().decode('utf-8').strip()

        if not functions_php_path:
            print("Error: Could not retrieve the functions.php path.")
            return

        form_title = generate_random_title(keyword)
        form_title = form_title.replace("\"", '')

        # Код для добавления в functions.php
        functions_php_code = f"""
function add_contact_form_to_content($content) {{
    $args = array(
        'post_type'      => 'wpcf7_contact_form',
        'posts_per_page' => 1,
        'order'          => 'DESC'
    );

    $form_query = new WP_Query($args);

    if ($form_query->have_posts()) {{
        while ($form_query->have_posts()) {{
            $form_query->the_post();
            $form_id = get_the_ID();
            $form_title = get_the_title();
        }}
        wp_reset_postdata();
    }} else {{
        return $content;
    }}

    $random_title = '{form_title}';

    $shortcode = '[contact-form-7 id="' . $form_id . '" title="' . $random_title . '"]';

    if (is_single() || is_page() || is_front_page()) {{
        $content = '
            <section id="contact-form">
                <h2 style="text-align: center;">' . $random_title . '</h2>
                <div>' . do_shortcode($shortcode) . '</div>
            </section>' . $content;
    }}

    return $content;
}}
add_filter('the_content', 'add_contact_form_to_content');
                    """

        add_code_to_functions_php(ssh, functions_php_path, functions_php_code)

        change_wp_status(domain, WhitePageStatus.DONE, complete_step="form_added")
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


@celery.task
def delete_domain(domain, server_ip, server_login, server_password, server_port):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        db_name = db_user = db_password = domain.replace('.', '_').replace('-', '_')
        commands = [
            f"rm -rf /var/www/{domain} 2>&1",
            f"rm /etc/httpd/conf.d/{domain}.conf 2>&1",
            f"""mysql -e "DELETE FROM mysql.user WHERE User={db_user};" """,
            f"""mysql -e "DROP DATABASE {db_name};" """,
            "systemctl restart httpd >/dev/null 2>&1",
        ]

        # Выполнение команд на сервере
        for command in commands:
            print(command)
            stdin, stdout, stderr = ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()  # Дожидаемся завершения команды
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)  # Логирование вывода команды, можно заменить на логгер

        change_wp_status(domain, WhitePageStatus.ADDED)
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error deleting {domain}: {e}")
    finally:
        ssh.close()


@celery.task
def create_certs(domains, server_ip, server_login, server_password, server_port):
    change_server_status(server_ip, ServerStatus.CONFIGURE)
    ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{server_ip}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        ssh.connect(
            hostname=server_ip,
            username=server_login,
            pkey=ssh_key,
            port=server_port
        )

        generate_lets_encrypt_cert(ssh, domains)

        change_server_status(server_ip, ServerStatus.ADDED)
    except Exception as e:
        change_server_status(server_ip, ServerStatus.ERROR)
        print(f"Error configuring server {server_ip}: {e}")
    finally:
        ssh.close()


def add_code_to_functions_php(ssh, functions_php_path, code):
    try:
        temp_file_path = "/tmp/new_functions.php"

        temp_existing_path = "/tmp/existing_functions.php"

        exec_command = f'cat {functions_php_path} > {temp_existing_path}'
        ssh.exec_command(exec_command)

        # Читаем существующее содержимое
        sftp = ssh.open_sftp()
        existing_code = sftp.file(temp_existing_path).read().decode('utf-8')

        new_code = existing_code + "\n" + code

        # Пишем новый код во временный файл
        new_file = sftp.file(temp_file_path, 'w')
        new_file.write(new_code)
        new_file.close()

        if sftp:
            sftp.close()

        exec_command = f'sudo cp {temp_file_path} {functions_php_path}'
        ssh.exec_command(exec_command)
    except Exception as e:
        print(f"Error adding code to functions.php: {e}")


def generate_new_topic(keyword):
    prompt = f"Generate a new topic based on the theme: {keyword}. Provide only the new topic and nothing else. Avoid any topics related to AI or artificial intelligence."

    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a skilled blog writer."},
            {"role": "user", "content": prompt}
        ],
        model="gpt-4o",
        max_tokens=50,
        temperature=0.7,
    )
    topic = response.choices[0].message.content
    return topic


def generate_post_content(keyword: str) -> (str, str):
    topic = generate_new_topic(keyword)
    prompt = f"""Write a natural-sounding detailed blog post about {topic}. Include personal anecdotes, real-life examples, and use conversational language. Allow for small errors in words and sentences to make the content less polished and more authentic. Vary the sentence structure to avoid detection as AI-generated content and ensure less repetitive writing. Incorporate informal phrases, contractions, and occasional interjections, just like in everyday speech, to make the text feel more human. Focus on adding genuine insights, emotions, and spontaneous thoughts that reflect real-life experiences. Write in simpler language and avoid using complex terms and abbreviations. Throughout the text, use different writing styles that are not drastically different but provide a natural flow and diversity in tone. Avoid any content related to AI or artificial intelligence."""
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a blog writer."},
            {"role": "user", "content": prompt}
        ],
        model="gpt-4o",
        max_tokens=4096,
        temperature=0.75,
        top_p=0.9,
        frequency_penalty=0.6,
        presence_penalty=0.7,

    )

    post_content = response.choices[0].message.content
    post_title = topic

    image_response = client.images.generate(
        model="dall-e-2",
        prompt=f"Generate an image that represents the concept of {keyword}.",
        n=1,
        size="1024x1024"
    )
    image_url = image_response.dict()['data'][0]['url']

    return post_title, post_content, image_url


def generate_random_title(keyword):
    prompt = f"Generate a catchy title for a sales form with the keyword: {keyword}"

    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a skilled blog writer."},
            {"role": "user", "content": prompt}
        ],
        model="gpt-4o",
    )
    print(response)
    title = response.choices[0].message.content
    return title


def generate_about_us_page(domain):
    address_prompt = "Generate a random, realistic address located in the United States. Provide only the new address and nothing else."
    response_address = client.chat.completions.create(
        messages=[
            {"role": "user", "content": address_prompt}
        ],
        model="gpt-4o",
    )
    random_address = response_address.choices[0].message.content

    # Генерация случайного номера телефона
    phone_number = f"+1 ({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
    email = f"info@{domain}"

    # Контактная информация
    contact_info = f"""
<h3>Contact Us</h3>
<p><strong>Address:</strong> {random_address}</p>
<p><strong>Phone:</strong> {phone_number}</p>
<p><strong>Email:</strong> {email}</p>
    """

    return contact_info


def generate_random_password(length=24):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))


def generate_nickname():
    first_part = ['star', 'dark', 'light', 'quick', 'silent', 'brave', 'shadow', 'fire', 'ice', 'wind']
    second_part = ['runner', 'hunter', 'walker', 'rider', 'warrior', 'seeker', 'caster', 'keeper', 'blade', 'frost']
    third_part = ['x', 'zero', 'nova', 'flare', 'spark', 'void', 'strike', 'edge', 'storm', 'wolf']

    part1 = random.choice(first_part)
    part2 = random.choice(second_part)
    part3 = random.choice(third_part)
    return f'{part1}{part2}{part3}'


def generate_random_date(base_date: datetime, days_range: int) -> datetime:
    days_back = random.randint(1, days_range)
    return base_date - timedelta(days=days_back)


def configure_http_in_apache(ssh, domain):
    # Путь к конфигурационному файлу Apache
    config_file_path = f"/etc/httpd/conf.d/{domain}.conf"

    # Конфигурация виртуального хоста с SSL
    config_content = f"""
<VirtualHost *:80>
    ServerName {domain}
    DocumentRoot /var/www/{domain}

    ErrorLog /var/log/httpd/{domain}_error.log
    CustomLog /var/log/httpd/{domain}_access.log combined

    <Directory /var/www/{domain}>
        AllowOverride All
        Require all granted
    </Directory>

    Header set Access-Control-Allow-Origin "*"
    Header set Access-Control-Allow-Methods "GET, POST, OPTIONS"
    Header set Access-Control-Allow-Headers "Content-Type"
</VirtualHost>
    """

    try:
        # Открытие сессии SFTP для записи файла
        sftp = ssh.open_sftp()
        with sftp.open(config_file_path, 'w') as config_file:
            config_file.write(config_content)
        sftp.close()

        print(f"HTTP configuration for {domain} has been written to {config_file_path}.")

    except Exception as e:
        print(f"Failed to write HTTP configuration: {e}")


@celery.task
def generate_csv_and_send_email(domains_data, recipient_email):
    # Создаем временный буфер для CSV-файла
    output = StringIO()
    writer = csv.writer(output)

    # Записываем заголовки CSV
    writer.writerow(['Domain', 'Server IP', 'Added Date', 'WP Login', 'WP Password'])

    # Записываем данные доменов
    for domain in domains_data:
        writer.writerow([
            domain['domain'],
            domain['server_ip'],
            domain['added_at'],
            domain['wp_login'],
            domain['wp_pass']
        ])

    output.seek(0)

    # Настраиваем отправку email
    sender_email = "no-reply@wp-generate.info"  # Замените на ваш email
    sender_password = "!W#Zf?0bGc&a"  # Замените на ваш пароль
    smtp_server = "mail.wp-generate.info"  # Замените на ваш SMTP-сервер
    smtp_port = 587  # Порт SMTP

    # Создаем объект письма
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = 'CSV отчет о доменах'
    body = 'Здравствуйте! Ваш отчет сформирован. Скачайте прикрепленный файл, чтобы ознакомится с отчетом.'
    msg.attach(MIMEText(body, 'plain'))

    # Прикрепляем CSV-файл
    csv_attachment = MIMEApplication(output.getvalue(), Name='domains.csv')
    csv_attachment['Content-Disposition'] = 'attachment; filename="domains.csv"'
    msg.attach(csv_attachment)
    output.close()

    # Отправка письма
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            print(f"Email sent to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def extract_db_credentials(wp_config_content):
    """Извлекаем данные для подключения к базе данных из содержимого wp-config.php."""

    # Попробовать альтернативы с двойными и одинарными кавычками:
    db_name_match = re.search(r"define\(\s*['\"]DB_NAME['\"],\s*['\"](.+?)['\"]\s*\);", wp_config_content)
    db_user_match = re.search(r"define\(\s*['\"]DB_USER['\"],\s*['\"](.+?)['\"]\s*\);", wp_config_content)
    db_password_match = re.search(r"define\(\s*['\"]DB_PASSWORD['\"],\s*['\"](.+?)['\"]\s*\);", wp_config_content)

    # Проверить успешность поиска для каждой переменной
    if db_name_match and db_user_match and db_password_match:
        db_name = db_name_match.group(1)
        db_user = db_user_match.group(1)
        db_password = db_password_match.group(1)
        return db_name, db_user, db_password
    else:
        # В случае ошибки выполнения регулярного выражения
        raise ValueError("Не удалось извлечь учетные данные из wp-config.php.")


@celery.task
def transfer_wordpress_site(
        domain,
        source_server,
        source_ssh_user,
        source_ssh_pass,
        source_ssh_port,
        dest_server,
        dest_ssh_user,
        dest_ssh_pass,
        dest_ssh_port
):
    change_wp_status(domain, WhitePageStatus.CONFIGURE)
    source_ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        source_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{source_server}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        source_ssh.connect(
            hostname=source_server,
            username=source_ssh_user,
            pkey=ssh_key,
            port=source_ssh_port
        )

        stdin, stdout, stderr = source_ssh.exec_command(f"cd /var/www/ && tar -czvf {domain}.tar.gz {domain}")
        stdout.channel.recv_exit_status()
        domain_archive = f"/var/www/{domain}.tar.gz"

        # Извлекаем данные из wp-config.php
        wp_config_file_path = f"/var/www/{domain}/wp-config.php"
        sftp = source_ssh.open_sftp()
        wp_config_file = sftp.file(wp_config_file_path, "r")
        wp_config_content = wp_config_file.read().decode()
        print(wp_config_content)
        wp_config_file.close()

        db_name, db_user, db_password = extract_db_credentials(wp_config_content)

        # Экспортируем базу данных
        db_backup_file = f"/root/{db_name}.sql"
        stdin, stdout, stderr = source_ssh.exec_command(f"mysqldump {db_name} > {db_backup_file}")
        stdout.channel.recv_exit_status()

        # Копируем конфигурационный файл Apache
        apache_config_file = f"/etc/httpd/conf.d/{domain}.conf"

        stdin, stdout, stderr = source_ssh.exec_command("dnf install sshpass -y")
        stdout.channel.recv_exit_status()

        stdin, stdout, stderr = source_ssh.exec_command(
            f"sshpass -p '{dest_ssh_pass}' "
            f"scp -o StrictHostKeyChecking=no "
            f"{domain_archive} "
            f"{db_backup_file} "
            f"{apache_config_file} "
            f"{dest_ssh_user}@{dest_server}:/tmp/"
        )
        stdout.channel.recv_exit_status()

        # Закрываем соединение с исходным сервером
        source_ssh.close()
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error transfer {domain}: {e}")
        raise

    dest_ssh = paramiko.SSHClient()
    try:
        # Подключение по SSH
        dest_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key_path = f"/home/maksim/.ssh/id_rsa_{dest_server}"
        ssh_key = paramiko.RSAKey.from_private_key_file(private_key_path)
        dest_ssh.connect(
            hostname=dest_server,
            username=dest_ssh_user,
            pkey=ssh_key,
            port=dest_ssh_port
        )

        stdin, stdout, stderr = dest_ssh.exec_command(f"cd /var/www && tar -xzvf /tmp/{domain}.tar.gz")
        stdout.channel.recv_exit_status()

        sql_commands = [
            f"""mysql -e "CREATE DATABASE {db_name};" """,
            f"""mysql -e "CREATE USER '{db_user}'@'localhost' IDENTIFIED BY '{db_password}';" """,
            f"""mysql -e "GRANT ALL PRIVILEGES ON {db_name}.* TO '{db_user}'@'localhost';" """,
            f"""mysql -e "FLUSH PRIVILEGES;" """,
            f"mysql {db_name} < /tmp/{db_name}.sql"
        ]

        for command in sql_commands:
            print(command)
            stdin, stdout, stderr = dest_ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)



        stdin, stdout, stderr = dest_ssh.exec_command(f"cp /tmp/{domain}.conf /etc/httpd/conf.d/" )
        stdout.channel.recv_exit_status()

        stdin, stdout, stderr = dest_ssh.exec_command(f"systemctl restart httpd.service")
        stdout.channel.recv_exit_status()

        commands = [
            "dnf install -y epel-release --nogpgcheck",
            "dnf install -y certbot python3-certbot-apache --nogpgcheck",
            "dnf install mod_ssl -y",
            "firewall-cmd --permanent --add-service=https",
            "firewall-cmd --reload",
        ]

        for command in commands:
            print(command)
            stdin, stdout, stderr = dest_ssh.exec_command(f"{command}")
            stdout.channel.recv_exit_status()
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            if error:
                print(f"Error executing command: {command}. Error: {error}")
                continue
            print(output)

        stdin, stdout, stderr = dest_ssh.exec_command(f"certbot certonly --apache --non-interactive --agree-tos --email admin@{domain} -d {domain}")
        stdout.channel.recv_exit_status()

        ssl_conf = f"""
<VirtualHost *:443>
    ServerName {domain}
    DocumentRoot /var/www/{domain}

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/{domain}/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/{domain}/privkey.pem

    <Directory /var/www/{domain}>
        Options Indexes FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog /var/log/httpd/{domain}_error.log
    CustomLog /var/log/httpd/{domain}_access.log combined
</VirtualHost>
        """
        conf_file_path = f"/etc/httpd/conf.d/{domain}-ssl.conf"
        command = f"echo '{ssl_conf}' > {conf_file_path}"
        stdin, stdout, stderr = dest_ssh.exec_command(command)
        stdout.channel.recv_exit_status()

        # Перезапускаем HTTP сервер в последний раз
        stdin, stdout, stderr = dest_ssh.exec_command(f"systemctl restart httpd.service")
        stdout.channel.recv_exit_status()

        # Закрываем соединение
        dest_ssh.close()
        change_wp_status(domain, WhitePageStatus.DONE)
    except Exception as e:
        change_wp_status(domain, WhitePageStatus.ERROR)
        print(f"Error transfer {domain}: {e}")
        raise

