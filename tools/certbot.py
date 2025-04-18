def configure_ssl_in_apache(ssh, domain, cert_path, key_path):
    # Путь к конфигурационному файлу Apache
    config_file_path = f"/etc/httpd/conf.d/{domain}-ssl.conf"

    # Конфигурация виртуального хоста с SSL
    config_content = f"""
<VirtualHost *:443>
    ServerName {domain}
    DocumentRoot /var/www/{domain}

    SSLEngine on
    SSLCertificateFile {cert_path}
    SSLCertificateKeyFile {key_path}

    <Directory /var/www/{domain}>
        Options Indexes FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog /var/log/httpd/{domain}_error.log
    CustomLog /var/log/httpd/{domain}_access.log combined
</VirtualHost>
    """

    try:
        # Открытие сессии SFTP для записи файла
        sftp = ssh.open_sftp()
        with sftp.open(config_file_path, 'w') as config_file:
            config_file.write(config_content)
        sftp.close()

        print(f"SSL configuration for {domain} has been written to {config_file_path}.")

    except Exception as e:
        print(f"Failed to write SSL configuration: {e}")


def generate_lets_encrypt_cert(ssh, domains: list):
    for domain in domains:
        try:
            # Генерация сертификата с помощью Certbot
            print(f"Generating Let's Encrypt certificate...")
            gen_cert_command = f"""
            certbot certonly --apache --non-interactive --agree-tos --email admin@{domains[0]} \
            -d {domain}
            """
            stdin, stdout, stderr = ssh.exec_command(gen_cert_command)
            stdout.channel.recv_exit_status()  # Дождаться завершения команды

            # Логирование вывода и ошибок
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')

            if "Congratulations" in output:
                print(f"Let's Encrypt certificate for {domain} has been successfully generated.")
            elif error:
                if error.find("debug") != -1:
                    print(f"DEBUG: {error}")
                    if error.find("Syntax") != -1:
                        print(f"Error generating Let's Encrypt certificate for {domain}: {error}")
                        raise
            else:
                print(f"Unexpected output: {output}")
                raise

            # Путь к сертификатам, сгенерированным Certbot
            cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
            key_path = f"/etc/letsencrypt/live/{domain}/privkey.pem"

            configure_ssl_in_apache(ssh, domain, cert_path, key_path)

        except Exception as e:
            print(f"Failed {domain}")
            print(e)
            raise

    # Разрешаем трафик по https в фаерволе
    stdin, stdout, stderr = ssh.exec_command("firewall-cmd --permanent --add-service=https >/dev/null 2>&1")
    stdout.channel.recv_exit_status()

    stdin, stdout, stderr = ssh.exec_command("systemctl reload firewalld >/dev/null 2>&1")
    stdout.channel.recv_exit_status()

