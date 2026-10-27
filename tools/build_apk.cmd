@echo off
rem Builds app-release.apk with the Flutter / JDK / Android SDK toolchain.
rem Expects this layout:  %TOOLCHAIN_DIR%\flutter, %TOOLCHAIN_DIR%\jdk-17, %TOOLCHAIN_DIR%\android-sdk
rem TOOLCHAIN_DIR defaults to D:\dev. On another PC run first:  set TOOLCHAIN_DIR=C:\dev   (your folder)
setlocal
if not defined TOOLCHAIN_DIR set TOOLCHAIN_DIR=D:\dev
if not exist "%TOOLCHAIN_DIR%\flutter\bin\flutter.bat" (
  echo Flutter not found in %TOOLCHAIN_DIR%\flutter. Set TOOLCHAIN_DIR first - see MOVING_TO_A_NEW_LAPTOP.md, Step 11.
  exit /b 1
)
set FLUTTER_ROOT=%TOOLCHAIN_DIR%\flutter
set JAVA_HOME=%TOOLCHAIN_DIR%\jdk-17
set ANDROID_HOME=%TOOLCHAIN_DIR%\android-sdk
set ANDROID_SDK_ROOT=%TOOLCHAIN_DIR%\android-sdk
set ANDROID_USER_HOME=%TOOLCHAIN_DIR%\android-user-home
set GRADLE_USER_HOME=%TOOLCHAIN_DIR%\gradle-home
set PUB_CACHE=%TOOLCHAIN_DIR%\pub-cache
set PATH=%FLUTTER_ROOT%\bin;%JAVA_HOME%\bin;%ANDROID_HOME%\platform-tools;%PATH%

cd /d "%~dp0..\app"
call flutter build apk --release
if errorlevel 1 exit /b 1
echo.
echo APK ready: %CD%\build\app\outputs\flutter-apk\app-release.apk
echo Install over USB (phone in USB-debugging mode):  adb install -r build\app\outputs\flutter-apk\app-release.apk
