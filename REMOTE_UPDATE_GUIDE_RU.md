# Удалённые обновления ASCII Studio (полная схема)

Ниже процесс, чтобы обновления прилетали на другие ПК через интернет.

## 1. Что использует приложение

Приложение читает `update_feed_url` (из настроек) и загружает JSON-манифест.

Обязательные поля манифеста:

```json
{
  "latest_version": "1.2.1",
  "installer_url": "https://your-domain/releases/ASCIIStudio_Setup_windows_x64.exe",
  "notes": "Bugfixes and performance improvements"
}
```

Поддерживаемые ключи:
- `latest_version` (обязательно)
- `installer_url` или `url` (обязательно)
- `notes` (опционально)

## 2. Что загружать на сервер

Минимум:
1. Новый installer (`ASCIIStudio_Setup_windows_x64.exe`) или web-bootstrap.
2. Новый `update_manifest.json`.

Рекомендуется:
1. `SHA256SUMS.txt` рядом с релизом.
2. Отдельная страница/README с changelog.

## 3. Где хранить

Подойдут:
- GitHub Releases
- S3/CloudFront
- любой HTTPS-хостинг с прямой ссылкой

Важно:
- ссылка в `installer_url` должна быть прямой на файл,
- TLS/HTTPS обязателен.

## 4. Как выпустить обновление (чеклист)

1. Собрать новую версию (`build_release.bat`).
2. Проверить запуск installer локально.
3. Залить installer на сервер.
4. Обновить `update_manifest.json`:
   - поднять `latest_version`,
   - заменить `installer_url`,
   - обновить `notes`.
5. Залить манифест.
6. В приложении нажать `Проверить обновления`.

## 5. Как настроить клиентские ПК

Вариант A (через UI):
- Settings -> Updates -> `Update feed URL` -> вставить URL вашего манифеста.

Вариант B (через файл настроек):
- файл: `~/.ascii_studio_settings.json`
- добавить/изменить:

```json
{
  "update_feed_url": "https://your-domain/releases/update_manifest.json",
  "auto_check_updates": true
}
```

## 6. Рекомендации по безопасности

1. Подписывать installer кодовой подписью (Authenticode).
2. Хранить SHA256 и сверять перед публикацией.
3. Ограничить запись в release-каталог.
4. Использовать versioning URL (например, `/releases/v1.2.1/...`).

## 7. Откат версии

Если релиз проблемный:
1. Верните предыдущий `installer_url` в манифесте.
2. Установите `latest_version` на стабильную версию.
3. Опубликуйте заметку в `notes`.

## 8. Быстрый пример

`update_manifest.json`:

```json
{
  "latest_version": "1.2.1",
  "installer_url": "https://example.com/ascii/releases/ASCIIStudio_Setup_windows_x64.exe",
  "notes": "Fix preset preview sample loading; improved installer and welcome flow."
}
```

