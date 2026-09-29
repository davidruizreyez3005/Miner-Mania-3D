#!/usr/bin/env bash
# Create a phone-sized AVD (720x1280, xhdpi, portrait - the game's design
# resolution) on the API 30 image from install_android_emulator.sh, boot it
# headless with KVM and SwiftShader graphics, and prepare it for automated
# input: animations off, the immersive-mode hint already acknowledged, screen
# kept on and unlocked.
#
#   tools/ci/start_android_emulator.sh <sdk_dir> <log_dir> [boot_timeout_s]
#
# Needs /dev/kvm (hardware acceleration). Prints the device serial.
set -euo pipefail

sdk="${1:?usage: start_android_emulator.sh <sdk_dir> <log_dir> [boot_timeout_s]}"
logs="${2:?usage: start_android_emulator.sh <sdk_dir> <log_dir> [boot_timeout_s]}"
timeout_s="${3:-600}"
avd_name="mm3d_api30"
serial="emulator-5554"
adb="$sdk/platform-tools/adb"

export ANDROID_HOME="$sdk" ANDROID_SDK_ROOT="$sdk"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.android/avd}"
mkdir -p "$logs" "$ANDROID_AVD_HOME/$avd_name.avd"

if ! "$sdk/emulator/emulator" -accel-check >"$logs/accel-check.txt" 2>&1; then
  cat "$logs/accel-check.txt" >&2
  echo "error: no hardware acceleration (KVM) for the emulator" >&2
  exit 1
fi

cat > "$ANDROID_AVD_HOME/$avd_name.ini" <<EOF
avd.ini.encoding=UTF-8
path=$ANDROID_AVD_HOME/$avd_name.avd
path.rel=avd/$avd_name.avd
target=android-30
EOF
cat > "$ANDROID_AVD_HOME/$avd_name.avd/config.ini" <<EOF
AvdId=$avd_name
avd.ini.displayname=$avd_name
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=4
hw.ramSize=4096
vm.heapSize=512
hw.lcd.width=720
hw.lcd.height=1280
hw.lcd.density=320
hw.initialOrientation=portrait
hw.gpu.enabled=yes
hw.gpu.mode=swiftshader_indirect
hw.keyboard=yes
hw.mainKeys=no
hw.audioInput=no
hw.audioOutput=no
hw.camera.back=none
hw.camera.front=none
disk.dataPartition.size=6G
image.sysdir.1=system-images/android-30/google_apis/x86_64/
tag.id=google_apis
tag.display=Google APIs
PlayStore.enabled=false
fastboot.forceColdBoot=yes
EOF

nohup "$sdk/emulator/emulator" -avd "$avd_name" -no-window -no-audio -no-boot-anim -no-snapshot -no-metrics \
  -wipe-data -gpu swiftshader_indirect -accel on -port 5554 >"$logs/emulator.log" 2>&1 &
echo $! > "$logs/emulator.pid"

"$adb" start-server >/dev/null 2>&1 || true
deadline=$((SECONDS + timeout_s))
until [[ "$("$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]] \
    && "$adb" -s "$serial" shell service check package 2>/dev/null | grep -q ": found" \
    && "$adb" -s "$serial" shell pm path android >/dev/null 2>&1; do
  if (( SECONDS > deadline )); then
    echo "error: the emulator did not boot within ${timeout_s}s" >&2
    tail -n 40 "$logs/emulator.log" >&2
    exit 1
  fi
  if ! kill -0 "$(cat "$logs/emulator.pid")" 2>/dev/null; then
    echo "error: the emulator exited" >&2
    tail -n 40 "$logs/emulator.log" >&2
    exit 1
  fi
  sleep 5
done
echo "Booted in ${SECONDS}s" >&2

sh_() { "$adb" -s "$serial" shell "$@"; }
sh_ settings put global window_animation_scale 0
sh_ settings put global transition_animation_scale 0
sh_ settings put global animator_duration_scale 0
sh_ settings put secure immersive_mode_confirmations confirmed
sh_ settings put system screen_off_timeout 1800000
sh_ svc power stayon true
sh_ input keyevent KEYCODE_WAKEUP
sh_ wm dismiss-keyguard >/dev/null 2>&1 || sh_ input keyevent 82
{
  echo "fingerprint: $(sh_ getprop ro.build.fingerprint | tr -d '\r')"
  echo "abilist: $(sh_ getprop ro.product.cpu.abilist | tr -d '\r')"
  echo "native bridge: $(sh_ getprop ro.dalvik.vm.native.bridge | tr -d '\r')"
  echo "screen: $(sh_ wm size | tr -d '\r'), $(sh_ wm density | tr -d '\r')"
  echo "opengles: $(sh_ getprop ro.opengles.version | tr -d '\r')"
} | tee "$logs/device.txt" >&2
echo "$serial"
