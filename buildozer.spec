[app]
title = SmartHazri
package.name = smarthazri
package.domain = org.smarthazri
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,sql
version = 5.0.0

# Dependencies jo aapke code ke hisab se zaroori hain
requirements = python3,kivy,urllib3,certifi,pillow

orientation = portrait
fullscreen = 0

# Internet aur storage permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
