#!/bin/sh
set -e

export ANDROID_HOME=$ANDROID_SDK_ROOT
export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/build-tools/35.0.0

export GRADLE_OPTS="-Xmx512m -XX:MaxMetaspaceSize=256m -Dsun.net.client.defaultConnectTimeout=300000 -Dsun.net.client.defaultReadTimeout=300000"
export GRADLE_USER_HOME="/tmp/gradle-cache"

APP_NAME="${APP_NAME:-sberWiki}"
PACKAGE="${PACKAGE:-com.sber.wiki}"
VERSION="${VERSION:-1.0.0}"
BUILD_TYPE="${BUILD_TYPE:-release}"

KEYSTORE_PATH="${KEYSTORE_PATH:-/keystore/my-release-key.keystore}"
KEY_ALIAS="${KEY_ALIAS:-my-key-alias}"
KEYSTORE_PASS="${KEYSTORE_PASS:-}"
KEY_PASS="${KEY_PASS:-}"

echo "🚀 Сборка APK для Android"
echo "   Название: $APP_NAME"
echo "   Package:  $PACKAGE"
echo "   Версия:   $VERSION"
echo "   Тип сборки: $BUILD_TYPE"

cd /app

rm -rf "$APP_NAME" 2>/dev/null || true

cordova create "$APP_NAME" "$PACKAGE" "$APP_NAME"
cd "$APP_NAME"

echo "📂 Содержимое исходной папки /wiki:"
ls -la /wiki

rm -rf www
mkdir www
echo "📂 Копируем файлы из /wiki в www ..."
cp -rv /wiki/. www/ 2>&1

echo "📂 Содержимое www после копирования:"
ls -la www/

if [ -f www/index.html ]; then
    echo "✅ index.html найден"
else
    echo "❌ index.html отсутствует!"
fi

cordova platform add android

if [ -f gradle/wrapper/gradle-wrapper.properties ]; then
    sed -i 's|services.gradle.org/distributions|mirror.yandex.ru/mirrors/gradle/distributions|g' gradle/wrapper/gradle-wrapper.properties
fi

VERSION_CODE=$(echo $VERSION | tr -d .)

if [ "$BUILD_TYPE" = "release" ]; then
    echo "📦 Сборка релизной версии..."
    cordova build android --release -- --packageType=apk --versionCode=$VERSION_CODE --versionName="$VERSION" -- --no-daemon --max-workers=2
    UNSIGNED_APK="platforms/android/app/build/outputs/apk/release/app-release-unsigned.apk"
else
    echo "🔧 Сборка debug версии..."
    cordova build android --debug -- --packageType=apk --versionCode=$VERSION_CODE --versionName="$VERSION" -- --no-daemon --max-workers=2
    UNSIGNED_APK="platforms/android/app/build/outputs/apk/debug/app-debug.apk"
fi

if [ ! -f "$UNSIGNED_APK" ]; then
    echo "❌ Ошибка: APK не найден"
    exit 1
fi

if [ "$BUILD_TYPE" = "release" ] && [ -f "$KEYSTORE_PATH" ] && [ -n "$KEYSTORE_PASS" ] && [ -n "$KEY_ALIAS" ]; then
    echo "🔑 Подписываем APK..."
    $ANDROID_HOME/build-tools/36.0.0/zipalign -v -p 4 "$UNSIGNED_APK" /tmp/app-aligned.apk
    $ANDROID_HOME/build-tools/36.0.0/apksigner sign \
        --ks "$KEYSTORE_PATH" \
        --ks-key-alias "$KEY_ALIAS" \
        --ks-pass env:KEYSTORE_PASS \
        --key-pass env:KEY_PASS \
        --out /output/app.apk \
        /tmp/app-aligned.apk
    echo "✅ Подписанный APK в /output/app.apk"
else
    cp "$UNSIGNED_APK" /output/app.apk
    echo "Неподписанный APK скопирован в /output/app.apk"
fi

echo "✅ Сборка завершена"

