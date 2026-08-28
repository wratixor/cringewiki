# Первый публичный запуск

Ниже — минимальная установка на Debian/Ubuntu с Caddy, systemd и SQLite. Она
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
sudo apt install -y git python3
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

## HTTPS через Caddy

Установите Caddy из официального репозитория, затем замените
`/etc/caddy/Caddyfile`:

```caddyfile
cringewiki.wratixor.ru {
    reverse_proxy 127.0.0.1:8766
}
```

Проверьте конфигурацию и перезагрузите Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -I https://cringewiki.wratixor.ru/web/
```

Caddy сам получает и продлевает сертификат, если домен указывает на этот
сервер, а извне доступны порты 80 и 443.

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
