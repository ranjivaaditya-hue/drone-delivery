# Set up the drone delivery project on your laptop

This guide moves the whole project to a new Windows laptop. Follow the steps in order.
Steps 1–9 take about 20 minutes and are all you need to run the system and the demo.
Steps 10–12 are only for the real drone, rebuilding the Android app, and the flight simulator.

**Links**

| What | Link |
|---|---|
| Code (private repository) | https://github.com/ranjivaaditya-hue/drone-delivery |
| Android app (APK download) | https://github.com/ranjivaaditya-hue/drone-delivery/releases/tag/v1.0.0 |
| This guide | https://github.com/ranjivaaditya-hue/drone-delivery/blob/main/MOVING_TO_A_NEW_LAPTOP.md |
| Full technical details | https://github.com/ranjivaaditya-hue/drone-delivery/blob/main/README.md |

**How it fits together:** your laptop runs two small Python programs. The *backend* is the server
the phone app talks to. The *bridge* turns the drone's MAVLink telemetry (or the built-in demo)
into delivery states and SMS. The phone app connects to your laptop over Wi-Fi.

---

## Step 1: Get access to the code

The repository is private, so the owner (Ranjiv) has to invite you.

1. If you don't have a GitHub account, create one (free): https://github.com/signup
2. Send Ranjiv your **GitHub username**. He adds you as a collaborator.
3. Accept the invitation from the e-mail GitHub sends, or at https://github.com/notifications

---

## Step 2: Install the software (once)

1. **Python 3.13**: https://www.python.org/downloads/windows/
   In the installer, **tick "Add python.exe to PATH"** at the bottom, then click *Install Now*.
   (Python 3.11 to 3.13 work. Don't use the Microsoft Store version.)
2. **Git for Windows**: https://git-scm.com/download/win (keep all the default options).
3. **Mission Planner** (only for the real drone):
   https://ardupilot.org/planner/docs/mission-planner-installation.html

Check the installs: open a **new** Command Prompt (Windows key, type `cmd`, press Enter) and run:

```bat
python --version
```
```bat
git --version
```

Both should print a version number.

---

## Step 3: Download the code

In the Command Prompt:

```bat
mkdir C:\Projects
```
```bat
cd /d C:\Projects
```
```bat
git clone https://github.com/ranjivaaditya-hue/drone-delivery.git
```
```bat
cd drone-delivery
```

The first time, Git opens a browser window to sign in to GitHub. Sign in with the account that was
invited in Step 1. Any folder works. Avoid a OneDrive-synced folder, because the Python environment
inside it is large and syncs badly.

All later commands are run **inside this folder** (`C:\Projects\drone-delivery`).

---

## Step 4: One-command setup

```bat
tools\setup_new_pc.cmd
```

This takes 1–3 minutes. It:

1. creates a private Python environment in the `.venv` folder,
2. installs the packages (FastAPI, uvicorn, pymavlink, requests, Twilio, pytest),
3. creates the settings file `.env` from `.env.example` (see Step 5),
4. runs the self-test.

It should end with **`58 passed`** and **`Setup complete`**. If it doesn't, see Troubleshooting at the end.

---

## Step 5: Environment variables (the `.env` file)

All settings live in one file: `.env` in the project folder. It is **not stored on GitHub on purpose**,
because it is where SMS passwords go. The setup script created it from `.env.example`, which holds
**exactly the values used on the original laptop**. For the demo you don't need to change anything.

To view or edit it:

```bat
notepad .env
```

Full contents, as used on the original laptop:

```ini
DRONE_ID=DRONE-001
WAREHOUSE_PHONE=+910000000002
DEFAULT_CUSTOMER_NAME=Demo Customer
DEFAULT_CUSTOMER_PHONE=+910000000001
API_HOST=0.0.0.0
API_PORT=8000
DB_PATH=backend/data/deliveries.db
API_BASE_URL=http://127.0.0.1:8000
MAVLINK_CONNECTION=udpin:0.0.0.0:14551
TARGET_SYSTEM_ID=0
MISSION_FILE=mission/delivery_mission.waypoints
RELEASE_PWM_TOLERANCE=100
RELEASE_SEQ_FALLBACK=true
TAKEOFF_ALT_M=1.5
SMS_PROVIDER=mock
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_MESSAGING_SERVICE_SID=
DEMO_STEP_SECONDS=6
LOG_LEVEL=INFO
BRIDGE_DATA_DIR=pc_bridge/data
```

What each one means:

| Variable | Value | What it does | Change it? |
|---|---|---|---|
| `DRONE_ID` | `DRONE-001` | Drone name shown in the app and SMS | No |
| `WAREHOUSE_PHONE` | `+910000000002` | Number that gets the warehouse SMS (placeholder) | For real SMS: a real number, format `+91XXXXXXXXXX` |
| `DEFAULT_CUSTOMER_NAME` | `Demo Customer` | Customer name when the PC creates a delivery by itself | Optional |
| `DEFAULT_CUSTOMER_PHONE` | `+910000000001` | Customer number for those deliveries (placeholder) | For real SMS |
| `API_HOST` | `0.0.0.0` | Backend accepts connections from the phone | No |
| `API_PORT` | `8000` | Backend port | No |
| `DB_PATH` | `backend/data/deliveries.db` | Delivery database (created automatically) | No |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Where the bridge finds the backend (same laptop) | No |
| `MAVLINK_CONNECTION` | `udpin:0.0.0.0:14551` | Port where the bridge receives the drone telemetry copy | No |
| `TARGET_SYSTEM_ID` | `0` | 0 = use the first ArduPilot drone heard | No |
| `MISSION_FILE` | `mission/delivery_mission.waypoints` | Mission layout (takeoff, delivery point, servo, RTL) | Yes, for the real mission (Step 10) |
| `RELEASE_PWM_TOLERANCE` | `100` | ± microseconds around the release servo PWM | No |
| `RELEASE_SEQ_FALLBACK` | `true` | Backup release detection if telemetry messages are lost | No |
| `TAKEOFF_ALT_M` | `1.5` | Height (m) that counts as "taken off" | No |
| `SMS_PROVIDER` | `mock` | `mock` only prints the SMS. `twilio` sends real SMS | `twilio` for real SMS |
| `TWILIO_ACCOUNT_SID` | *(empty)* | From the Twilio console | For real SMS |
| `TWILIO_AUTH_TOKEN` | *(empty)* | Twilio password. **Never share it or put it on GitHub** | For real SMS |
| `TWILIO_FROM_NUMBER` | *(empty)* | Your Twilio phone number | For real SMS |
| `TWILIO_MESSAGING_SERVICE_SID` | *(empty)* | Alternative to the FROM number | Optional |
| `DEMO_STEP_SECONDS` | `6` | Demo speed (one mission ≈ 8 × this) | Optional |
| `LOG_LEVEL` | `INFO` | Amount of detail in the log windows | No |
| `BRIDGE_DATA_DIR` | `pc_bridge/data` | Bridge's SMS log and queue (created automatically) | No |

`.env.example` also lists optional overrides, commented out: `TAKEOFF_SEQ`, `DELIVERY_WP_SEQ`,
`RELEASE_SEQ`, `RTL_SEQ`, `RELEASE_SERVO_CHANNEL`, `RELEASE_SERVO_PWM`. Use them only if the
mission file can't be used (README section 5.3).

---

## Step 6: Let the phone reach the laptop (Windows settings)

1. **Settings → Network & internet → Wi-Fi →** *(your Wi-Fi name)* **→ Network profile type: Private.**
   On a "Public" network Windows blocks the phone.
2. The first time the backend starts (Step 7), a **Windows Defender Firewall** window asks about Python.
   Tick **Private networks** and click **Allow access**.

If you missed that window, open Command Prompt **as administrator** and run:

```bat
netsh advfirewall firewall add rule name="Drone Delivery API" dir=in action=allow protocol=TCP localport=8000 profile=private
```

---

## Step 7: Start the system (demo mode, no drone needed)

```bat
tools\start_demo.cmd
```

Two windows open. **Keep both open while you use the app.**

- **Delivery backend (FastAPI)** prints the address for the phone, for example
  `http://192.168.1.25:8000`. Note it.
- **PC bridge - DEMO** shows events and the SMS (printed, not sent, in mock mode).

---

## Step 8: Connect the phone app

The phone and the laptop must be on the **same Wi-Fi**.

**The app is already installed on the phone:** open it, tap the **gear icon** (top right), enter the
address from Step 7, e.g. `192.168.1.25:8000`, and tap **Save**. The dot next to the gear turns green.

**To install the app on a phone:**

1. On the phone, sign in to GitHub in the browser (the repository is private), then open
   https://github.com/ranjivaaditya-hue/drone-delivery/releases/tag/v1.0.0
2. Under *Assets*, tap **DroneDelivery-v1.0.0.apk** to download it.
3. Open the file. If Android asks, allow *Install unknown apps* for the browser.
4. If Play Protect warns, tap **More details → Install anyway**. The app is not from the Play Store.
5. Open **Drone Delivery**, allow notifications, and enter the address as above.

Quick check: open `http://<address>/api/health` in the phone's browser. It must show `{"status":"ok", ...}`.

---

## Step 9: Run a test delivery

**Automatic:** in the app, open the **Warehouse** tab and tap **Start demo mission**. Over about
50 seconds, Home goes through: Drone has taken off → Drone is on the way → Package delivered →
Drone returning home → Delivery completed. Each change also arrives as a phone notification.
The bridge window prints 7 SMS (3 customer, 4 warehouse).

**Step by step**, one phase per command. Close the *PC bridge - DEMO* window first (keep the
backend window). Then, in a Command Prompt in the project folder:

```bat
.venv\Scripts\python.exe pc_bridge\main.py --event TAKEOFF
```
```bat
.venv\Scripts\python.exe pc_bridge\main.py --event EN_ROUTE
```
```bat
.venv\Scripts\python.exe pc_bridge\main.py --event PACKAGE_RELEASED
```
```bat
.venv\Scripts\python.exe pc_bridge\main.py --event RTL_STARTED
```
```bat
.venv\Scripts\python.exe pc_bridge\main.py --event HOME_COMPLETED
```

Check the phone after each one. Each command prints the next one to run. Running
`PACKAGE_RELEASED` twice shows the duplicate protection: no change and no second SMS.

---

## Step 10: The real drone

1. Connect Mission Planner to the drone as usual (ELRS link).
2. In Mission Planner press **Ctrl+F** and click **MAVLink**. Choose **UDP Client**, enter
   **127.0.0.1** and port **14551**, leave **Write access unticked**, and connect. This gives the
   bridge a read-only copy of the telemetry. Mission Planner keeps working normally. Turn it on
   again after every Mission Planner restart.
3. Start the system in live mode instead of the demo:
   ```bat
   tools\start_live.cmd
   ```
4. The bridge window should show `Locked onto vehicle: system id 1`. Every 30 s it prints a
   **Link check** and warns if needed messages are missing.
5. Tell the bridge your mission: in Mission Planner's PLAN screen use **Save File**, put the
   `.waypoints` file in the `mission` folder, and set `MISSION_FILE=mission\yourfile.waypoints` in `.env`.
6. Recommended ArduPilot settings: `SERVO9_FUNCTION = 0` (the release servo output),
   `MIS_RESTART = 1`, MAVLink2 on the ELRS port, and telemetry rates of at least 1 Hz for
   *Mode/Status*, *Position* and *RC*. Details: README section 5.

Check a recorded flight before trusting live SMS. Mission Planner saves a `.tlog` for every
session (in `Documents\Mission Planner\logs`). Replay it with:

```bat
.venv\Scripts\python.exe pc_bridge\main.py --replay "C:\path\to\flight.tlog"
```

---

## Step 11 (optional): Rebuild the Android app

Only needed if you change the app's code. You can always download the APK from the release (Step 8).
This installs about 10 GB of tools.

**11.1 Pick a tools folder.** Use `C:\dev` (or any path without spaces). This is your `TOOLCHAIN_DIR`.

**11.2 Download and unpack (exact versions that are known to work):**

| Tool | Download | Unpack so that this file exists |
|---|---|---|
| Flutter 3.47.6 | https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.47.6-stable.zip | `C:\dev\flutter\bin\flutter.bat` |
| JDK 17 (Temurin, Windows x64, **.zip**) | https://adoptium.net/temurin/releases/?version=17&os=windows&arch=x64&package=jdk | `C:\dev\jdk-17\bin\java.exe` (rename the unpacked folder to `jdk-17`) |
| Android command-line tools (Windows) | https://developer.android.com/studio#command-line-tools-only | `C:\dev\android-sdk\cmdline-tools\latest\bin\sdkmanager.bat` (rename the inner `cmdline-tools` folder to `latest`) |

**11.3 Install the Android SDK parts.** The new `sdkmanager` breaks on the `;` in package names
on Windows, so the names go through a text file. Paste these into a Command Prompt one by one, and
type `y` if it asks you to accept the license:

```bat
set TOOLCHAIN_DIR=C:\dev
```
```bat
set JAVA_HOME=%TOOLCHAIN_DIR%\jdk-17
```
```bat
(echo platform-tools& echo platforms;android-36& echo build-tools;36.0.0& echo ndk;28.2.13676358)> "%TEMP%\sdk-packages.txt"
```
```bat
"%TOOLCHAIN_DIR%\android-sdk\cmdline-tools\latest\bin\sdkmanager.bat" --package_file="%TEMP%\sdk-packages.txt"
```

**11.4 Tell Flutter where things are (once):**

```bat
"%TOOLCHAIN_DIR%\flutter\bin\flutter.bat" config --no-analytics
```
```bat
"%TOOLCHAIN_DIR%\flutter\bin\flutter.bat" config --android-sdk "%TOOLCHAIN_DIR%\android-sdk" --jdk-dir "%TOOLCHAIN_DIR%\jdk-17"
```

**11.5 Keep app updates working.** Android only installs an update over the existing app if it
is signed with the same key. Ask Ranjiv for his file `D:\dev\android-user-home\debug.keystore`
and copy it to `C:\dev\android-user-home\debug.keystore` **before the first build**. Without it,
uninstall the old app from the phone before installing your build.

**11.6 Build:**

```bat
set TOOLCHAIN_DIR=C:\dev
```
```bat
tools\build_apk.cmd
```

The first build downloads Gradle and takes 5–10 minutes. The APK appears at
`app\build\app\outputs\flutter-apk\app-release.apk`.

These are the toolchain environment variables. `tools\build_apk.cmd` sets them itself from
`TOOLCHAIN_DIR`, so you don't need to add them to Windows:

| Variable | Value |
|---|---|
| `TOOLCHAIN_DIR` | `C:\dev` (your folder from 11.1) |
| `FLUTTER_ROOT` | `%TOOLCHAIN_DIR%\flutter` |
| `JAVA_HOME` | `%TOOLCHAIN_DIR%\jdk-17` |
| `ANDROID_HOME`, `ANDROID_SDK_ROOT` | `%TOOLCHAIN_DIR%\android-sdk` |
| `ANDROID_USER_HOME` | `%TOOLCHAIN_DIR%\android-user-home` (holds `debug.keystore`) |
| `GRADLE_USER_HOME` | `%TOOLCHAIN_DIR%\gradle-home` |
| `PUB_CACHE` | `%TOOLCHAIN_DIR%\pub-cache` |
| `PATH` (added in front) | `flutter\bin`, `jdk-17\bin`, `android-sdk\platform-tools` |

To publish a new version, raise `version:` in `app\pubspec.yaml` (e.g. `1.0.1+2`; the number
after `+` must go up), build, and create a new GitHub release with the APK.

---

## Step 12 (optional): Flight simulator test

The project was checked against the official ArduPilot simulator (SITL) running in WSL.

1. Install WSL with Ubuntu. Run this in Command Prompt **as administrator**, then restart the laptop:
   ```bat
   wsl --install -d Ubuntu-24.04
   ```
2. Download the ArduCopter simulator (official ArduPilot server):
   ```bat
   wsl -d Ubuntu-24.04 -- bash -c "mkdir -p ~/sitl && cd ~/sitl && curl -fLo arducopter https://firmware.ardupilot.org/Copter/stable/SITL_x86_64_linux_gnu/arducopter && chmod +x arducopter && curl -fLo copter.parm https://raw.githubusercontent.com/ArduPilot/ardupilot/master/Tools/autotest/default_params/copter.parm"
   ```
3. Start the simulator in its own window and leave it running:
   ```bat
   wsl -d Ubuntu-24.04 -- bash -c "cd ~/sitl && ./arducopter -w -S --model + --speedup 3 --defaults copter.parm -I0 --home -35.363261,149.165230,584,353"
   ```
4. Run `tools\start_live.cmd`, then fly the delivery mission in the simulator. `--drop 0.3` simulates
   30% packet loss on the telemetry link:
   ```bat
   .venv\Scripts\python.exe tools\sitl_delivery_test.py --drop 0.3
   ```

---

## What is not on GitHub (on purpose)

| Item | Why | What to do |
|---|---|---|
| `.env` | Can hold SMS passwords | Created by `tools\setup_new_pc.cmd` with the same values (Step 5) |
| Old test deliveries (`backend\data\deliveries.db`) | Test data with names and numbers | Not needed. The database starts empty |
| `debug.keystore` | App signing key | Only needed to rebuild the app as an update (Step 11.5) |
| Flutter / JDK / Android SDK | About 10 GB of tools | Only needed to rebuild the app (Step 11) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognised | Reinstall Python with **"Add python.exe to PATH"** ticked, then open a new Command Prompt |
| Setup says *Could not create .venv* | Install Python from python.org, not the Microsoft Store |
| `git clone` says *Repository not found* | Accept the GitHub invitation (Step 1) and sign in with that account |
| Windows says *Windows protected your PC* for a `.cmd` file | Click **More info → Run anyway** (only happens if the files came from a ZIP) |
| App: *Can't reach the delivery server* | Same Wi-Fi? Network set to Private (Step 6)? Firewall allowed? Test `http://<address>/api/health` in the phone browser |
| App stays on *Preparing for takeoff* | The bridge isn't running. Start `tools\start_demo.cmd`, or use the step commands (Step 9) |
| Warehouse tab: *Event monitor offline* | Same cause: start the bridge window |
| Address changed after a router restart | The backend window shows the new address at start. Enter it again in the app (gear icon) |
| Bridge: *No ArduPilot HEARTBEAT received yet* | Mission Planner forwarding (Step 10.2) is off or uses a different port |
| Phone gets no notifications | Allow notifications for the app. Set battery to **Unrestricted** (Settings → Apps → Drone Delivery → Battery) |
| APK build: *sdkmanager did not install NDK* | Repeat Step 11.3. The package-file method is required on Windows |
| APK won't install over the old app | Signing keys differ: copy `debug.keystore` (Step 11.5), or uninstall the old app first |
