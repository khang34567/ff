@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================================================
echo   HE THONG TU DONG BIEN DICH REMOTETOUCH (.APK VA .EXE) - 1 CLICK BUILD
echo ============================================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"
if not exist "%ROOT_DIR%OUTPUT_FILES" mkdir "%ROOT_DIR%OUTPUT_FILES"

:: ----------------------------------------------------------------------------
:: BUOC 1: DONG GOI FILE PC_Controller.exe BANG PYINSTALLER
:: ----------------------------------------------------------------------------
echo [1/2] Dang kiem tra Python va dong goi PC_Controller.exe...
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Khong tim thay Python trong PATH. Dang tu dong cai dat Python 3.11 qua winget...
    winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
)

python -m pip install --upgrade pip
python -m pip install pyinstaller opencv-python numpy pillow

echo [*] Dang chay PyInstaller (--onefile --noconsole)...
python -m PyInstaller --onefile --noconsole --clean --name PC_Controller "%ROOT_DIR%PC_Controller\PC_Controller.py"

if exist "%ROOT_DIR%dist\PC_Controller.exe" (
    copy /Y "%ROOT_DIR%dist\PC_Controller.exe" "%ROOT_DIR%OUTPUT_FILES\PC_Controller.exe" >nul
    copy /Y "%ROOT_DIR%dist\PC_Controller.exe" "%ROOT_DIR%PC_Controller.exe" >nul
    echo [OK] Da xuat thanh cong: OUTPUT_FILES\PC_Controller.exe
) else (
    echo [LOI] Khong the tao PC_Controller.exe. Vui long kiem tra cai dat Python.
)

:: ----------------------------------------------------------------------------
:: BUOC 2: BIEN DICH FILE RemoteTouch_Android.apk BANG GRADLE + ANDROID SDK
:: ----------------------------------------------------------------------------
echo.
echo [2/2] Dang kiem tra JDK 17, Android SDK va bien dich RemoteTouch_Android.apk...

set "TOOLS_DIR=%ROOT_DIR%.build_tools"
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

:: Kiem tra Java (JDK 17)
where javac >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if not exist "%TOOLS_DIR%\jdk-17\bin\javac.exe" (
        echo [*] Dang tai Portable OpenJDK 17...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse' -OutFile '%TOOLS_DIR%\jdk17.zip'"
        powershell -Command "Expand-Archive -Path '%TOOLS_DIR%\jdk17.zip' -DestinationPath '%TOOLS_DIR%\jdk_extracted' -Force"
        for /d %%D in ("%TOOLS_DIR%\jdk_extracted\*") do move "%%D" "%TOOLS_DIR%\jdk-17" >nul
    )
    set "JAVA_HOME=%TOOLS_DIR%\jdk-17"
    set "PATH=!JAVA_HOME!\bin;!PATH!"
)

:: Kiem tra Android SDK
if "%ANDROID_HOME%"=="" (
    if exist "%LOCALAPPDATA%\Android\Sdk" (
        set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
    ) else (
        set "ANDROID_HOME=%TOOLS_DIR%\android-sdk"
    )
)

if not exist "%ANDROID_HOME%\platforms\android-34" (
    echo [*] Dang tai Android Command Line Tools va SDK Platform 34...
    if not exist "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" (
        mkdir "%ANDROID_HOME%\cmdline-tools" 2>nul
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip' -OutFile '%TOOLS_DIR%\cmdline-tools.zip'"
        powershell -Command "Expand-Archive -Path '%TOOLS_DIR%\cmdline-tools.zip' -DestinationPath '%ANDROID_HOME%\cmdline-tools' -Force"
        move "%ANDROID_HOME%\cmdline-tools\cmdline-tools" "%ANDROID_HOME%\cmdline-tools\latest" >nul
    )
    echo y| call "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" --sdk_root="%ANDROID_HOME%" --licenses >nul
    call "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" --sdk_root="%ANDROID_HOME%" "platform-tools" "platforms;android-34" "build-tools;34.0.0"
)

:: Tai Gradle 8.4 neu chua co
if not exist "%TOOLS_DIR%\gradle-8.4\bin\gradle.bat" (
    echo [*] Dang tai Gradle 8.4...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://services.gradle.org/distributions/gradle-8.4-bin.zip' -OutFile '%TOOLS_DIR%\gradle.zip'"
    powershell -Command "Expand-Archive -Path '%TOOLS_DIR%\gradle.zip' -DestinationPath '%TOOLS_DIR%' -Force"
)

cd /d "%ROOT_DIR%RemoteTouch_Android"
call "%TOOLS_DIR%\gradle-8.4\bin\gradle.bat" assembleDebug --no-daemon

if exist "%ROOT_DIR%RemoteTouch_Android\app\build\outputs\apk\debug\RemoteTouch_Android.apk" (
    copy /Y "%ROOT_DIR%RemoteTouch_Android\app\build\outputs\apk\debug\RemoteTouch_Android.apk" "%ROOT_DIR%OUTPUT_FILES\RemoteTouch_Android.apk" >nul
    copy /Y "%ROOT_DIR%RemoteTouch_Android\app\build\outputs\apk\debug\RemoteTouch_Android.apk" "%ROOT_DIR%RemoteTouch_Android.apk" >nul
    echo [OK] Da xuat thanh cong: OUTPUT_FILES\RemoteTouch_Android.apk
) else (
    echo [LOI] Qua trinh build APK gap su co. Hay kiem tra ket noi mang hoac log o tren.
)

cd /d "%ROOT_DIR%"
echo.
echo ============================================================================
echo   HOAN TAT! 2 FILE CUA BAN NAM TAI THU MUC: %ROOT_DIR%OUTPUT_FILES
echo   1. RemoteTouch_Android.apk
echo   2. PC_Controller.exe
echo ============================================================================
pause
