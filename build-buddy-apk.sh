#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
JAVA_HOME="$ROOT/.tools/jdk17"
ANDROID_HOME="$ROOT/.tools/android-sdk"
BUILD_TOOLS="$ANDROID_HOME/build-tools/35.0.0"
ANDROID_JAR="$ANDROID_HOME/platforms/android-35/android.jar"
APP="$ROOT/buddy-android/app"
OUT="$ROOT/buddy-android/build/manual"
APK_UNSIGNED="$OUT/buddy-unsigned.apk"
APK_ALIGNED="$OUT/buddy-aligned.apk"
APK_SIGNED="$OUT/buddy.apk"
KEYSTORE="$ROOT/.tools/buddy-debug.jks"

export JAVA_HOME
export PATH="$JAVA_HOME/bin:$BUILD_TOOLS:$PATH"

rm -rf "$OUT"
mkdir -p "$OUT/classes" "$OUT/generated" "$OUT/compiled" "$OUT/dex"

aapt2 compile --dir "$APP/src/main/res" -o "$OUT/compiled/res.zip"
aapt2 link \
  -I "$ANDROID_JAR" \
  --manifest "$APP/src/main/AndroidManifest.xml" \
  --min-sdk-version 23 \
  --target-sdk-version 27 \
  --version-code 1 \
  --version-name 0.1.0 \
  -A "$APP/src/main/assets" \
  --java "$OUT/generated" \
  --auto-add-overlay \
  -o "$APK_UNSIGNED" \
  "$OUT/compiled/res.zip"

find "$APP/src/main/java" "$OUT/generated" -name '*.java' > "$OUT/sources.txt"
javac -source 8 -target 8 \
  -bootclasspath "$ANDROID_JAR" \
  -classpath "$ANDROID_JAR" \
  -d "$OUT/classes" \
  @"$OUT/sources.txt"

d8 \
  --min-api 23 \
  --lib "$ANDROID_JAR" \
  --output "$OUT/dex" \
  $(find "$OUT/classes" -name '*.class')

cd "$OUT/dex"
zip -q -u "$APK_UNSIGNED" classes.dex
cd "$ROOT"

zipalign -f 4 "$APK_UNSIGNED" "$APK_ALIGNED"

if [ ! -f "$KEYSTORE" ]; then
  keytool -genkeypair \
    -keystore "$KEYSTORE" \
    -storepass android \
    -keypass android \
    -alias buddy \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -dname "CN=Buddy,O=Codex,C=CN"
fi

apksigner sign \
  --ks "$KEYSTORE" \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out "$APK_SIGNED" \
  "$APK_ALIGNED"

apksigner verify "$APK_SIGNED"
echo "$APK_SIGNED"
