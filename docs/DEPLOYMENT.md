# Первый публичный запуск

Ниже — минимальная установка на Debian/Ubuntu с Nginx, systemd и SQLite. Она
рассчитана на `cringewiki.wratixor.ru` и Python 3.11+.

## До начала

1. A/AAAA-запись домена должна вести на сервер.
2. Порты 80 и 443 должны быть открыты в firewall и у хостинга.
3. Не запускайте `python -m server.seed` на публичном сервере: он создаёт
   демонстрационные учётные записи с известным паролем. При обычном запуске
   системные точки «Пользователи» и «Теги» создаются сами.

## Установка приложения

```bash
sudo apt update
sudo apt install -y git python3 nginx certbot python3-certbot-nginx
sudo useradd --system --home /var/lib/cringewiki --create-home --shell /usr/sbin/nologin cringewiki
sudo git clone https://github.com/wratixor/cringewiki.git /opt/cringewiki
sudo chown -R root:root /opt/cringewiki
sudo mkdir -p /var/lib/cringewiki
sudo chown cringewiki:cringewiki /var/lib/cringewiki
```

Создайте `/etc/systemd/system/cringewiki.service`:

```ini
[Unit]
Description=Cringewiki
After=network.target

[Service]
Type=simple
User=cringewiki
Group=cringewiki
WorkingDirectory=/opt/cringewiki
Environment=CRINGEWIKI_DB=/var/lib/cringewiki/cringewiki.sqlite3
Environment=CRINGEWIKI_HOST=127.0.0.1
Environment=CRINGEWIKI_PORT=8766
Environment=CRINGEWIKI_SECURE_COOKIES=1
ExecStart=/usr/bin/python3 /opt/cringewiki/run.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/cringewiki

[Install]
WantedBy=multi-user.target
```

Запустите и проверьте приложение только на loopback-интерфейсе:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cringewiki
curl http://127.0.0.1:8766/api/index
sudo journalctl -u cringewiki -f
```

## HTTPS через Nginx

Создайте отключённый до проверки DNS сайт
`/etc/nginx/sites-available/cringewiki`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name cringewiki.wratixor.ru;

    client_max_body_size 256k;

    location / {
        proxy_pass http://127.0.0.1:8766;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }
}
```

Включите его лишь после проверки DNS и firewall, затем выпустите сертификат:

```bash
sudo ln -s /etc/nginx/sites-available/cringewiki /etc/nginx/sites-enabled/cringewiki
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d cringewiki.wratixor.ru
sudo nginx -t && sudo systemctl reload nginx
curl -I https://cringewiki.wratixor.ru/web/
```

`certbot` добавит HTTPS-конфигурацию и редирект с HTTP. Проверьте автопродление
сертификата: `sudo systemctl status certbot.timer`.

## После запуска

- зарегистрируйте первый реальный аккаунт через сайт;
- ежедневно делайте резервную копию `/var/lib/cringewiki/cringewiki.sqlite3`
  вне сервера;
- перед обновлением сделайте резервную копию, затем выполните
  `sudo git -C /opt/cringewiki pull --ff-only` и
  `sudo systemctl restart cringewiki`;
- не открывайте порт 8766 в firewall: внешнему миру нужны только 80 и 443.

Это ранний публичный прототип. До массового запуска необходимы ограничение
частоты регистраций/входов, журналирование без секретов, модерация и отдельный
разбор угроз.
