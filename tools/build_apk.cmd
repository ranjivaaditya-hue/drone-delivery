@echo off
rem Builds app-release.apk with the toolchain installed under D:\dev.
rem Change DEV if you installed Flutter / JDK / Android SDK somewhere else.
setlocal
set DEV=D:\dev
set FLUTTER_ROOT=%DEV%\flutter
set JAVA_HOME=%DEV%\jdk-17
set ANDROID_HOME=%DEV%\android-sdk
set ANDROID_SDK_ROOT=%DEV%\android-sdk
set ANDROID_USER_HOME=%DEV%\android-user-home
set GRADLE_USER_HOME=%DEV%\gradle-home
set PUB_CACHE=%DEV%\pub-cache
set PATH=%FLUTTER_ROOT%\bin;%JAVA_HOME%\bin;%ANDROID_HOME%\platform-tools;%PATH%

cd /d "%~dp0..\app"
call flutter build apk --release
if errorlevel 1 exit /b 1
echo.
echo APK ready: %CD%\build\app\outputs\flutter-apk\app-release.apk
echo Install over USB (phone in USB-debugging mode):  adb install -r build\app\outputs\flutter-apk\app-release.apk
