import os, sys, hashlib
from dotenv import dotenv_values, find_dotenv
from app.core.config import settings

def fingerprint(label, value):
    if value is None:
        print(f"{label}: <None>")
        return
    print(f"{label}: len={len(value)}, repr={repr(value)}")
    print(f"{label}: sha1={hashlib.sha1(value.encode()).hexdigest()}")

print("--- process env ---")
fingerprint("os.environ", os.environ.get("OSS_ACCESS_KEY_SECRET"))

print("--- settings ---")
fingerprint("settings", settings.OSS_ACCESS_KEY_SECRET)

print("--- .env ---")
env_path = find_dotenv(".env", raise_error_if_not_found=False)
env_values = dotenv_values(env_path) if env_path else {}
fingerprint(".env", env_values.get("OSS_ACCESS_KEY_SECRET"))