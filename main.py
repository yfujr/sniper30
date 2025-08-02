import requests
import random
import string
import threading
import time
import os
from queue import Queue

# ========== CONFIG ==========
THREADS = 100
VALID_FILE = 'valid.txt'
CHECKED_FILE = 'checked.txt'
BIRTHDAY = '1999-04-20'
LOG_TAKEN = True
USERNAME_LENGTH = 4
MAX_PROXY_RETRIES = 3
DELAY_IF_RATE_LIMITED = 30

PROXY_LIST = [
    'http://1.0.171.213', 'http://108.162.192.12', 'http://108.162.192.173',
    'http://108.162.193.160', 'http://108.141.130.146', 'http://108.162.192.185',
    'http://1.0.170.50', 'http://108.162.192.194', 'http://108.162.192.0',
    'http://102.177.176.110', 'socks4://1.0.103.97', 'socks4://1.54.41.16',
    'http://1.52.197.113', 'http://1.54.172.229', 'http://1.52.198.150'
]

# ========== UTILS ==========
class bcolors:
    OK = '\033[94m'
    FAIL = '\033[91m'
    END = '\033[0m'

lock = threading.Lock()
checked_usernames = set()
successful_usernames = []
proxy_lock = threading.Lock()
proxy_queue = Queue()
username_queue = Queue()
proxy_retry_counts = {}

for proxy in PROXY_LIST:
    proxy_queue.put(proxy)

# ========== FILE LOAD ==========
if os.path.exists(CHECKED_FILE):
    with open(CHECKED_FILE, 'r') as f:
        for line in f:
            checked_usernames.add(line.strip())

# ========== GENERATORS ==========
def generate_username():
    pos0 = string.ascii_lowercase + string.digits
    pos1 = pos2 = string.ascii_lowercase + string.digits + '_'
    pos3 = string.ascii_lowercase + string.digits

    while True:
        uname = random.choice(pos0) + random.choice(pos1) + random.choice(pos2) + random.choice(pos3)
        if '__' in uname or uname[0] == '_' or uname[-1] == '_':
            continue
        return uname

def refill_username_queue(count=1000):
    with lock:
        for _ in range(count):
            uname = generate_username()
            if uname not in checked_usernames:
                username_queue.put(uname)

# ========== LOGGING ==========
def log_success(username, thread_id):
    with lock:
        successful_usernames.append(username)
        print(f"{bcolors.OK}[+] {username} is available [T{thread_id}]{bcolors.END}")
        with open(VALID_FILE, 'a') as f:
            f.write(username + '\n')

def log_taken(username, thread_id):
    if LOG_TAKEN:
        print(f"{bcolors.FAIL}[TAKEN] {username} [T{thread_id}]{bcolors.END}")

def record_checked(username):
    with lock:
        if username not in checked_usernames:
            checked_usernames.add(username)
            with open(CHECKED_FILE, 'a') as f:
                f.write(username + '\n')

# ========== PROXY/REQUEST HANDLING ==========
def get_proxy():
    while True:
        proxy = proxy_queue.get()
        retries = proxy_retry_counts.get(proxy, 0)
        if retries < MAX_PROXY_RETRIES:
            return proxy
        else:
            # Put it back after delay
            time.sleep(DELAY_IF_RATE_LIMITED)
            proxy_retry_counts[proxy] = 0
            proxy_queue.put(proxy)

def release_proxy(proxy, bad=False):
    if bad:
        proxy_retry_counts[proxy] = proxy_retry_counts.get(proxy, 0) + 1
    else:
        proxy_retry_counts[proxy] = 0
    proxy_queue.put(proxy)

def check_username(username, proxy):
    url = f"https://auth.roblox.com/v1/usernames/validate?request.username={username}&request.birthday={BIRTHDAY}"
    try:
        r = requests.get(url, proxies={'http': proxy, 'https': proxy}, timeout=10)
        if r.status_code == 429:
            return None, 429
        r.raise_for_status()
        return r.json().get('code') == 0, r.status_code
    except:
        return None, None

# ========== THREAD WORK ==========
def worker(thread_id):
    while True:
        if username_queue.empty():
            refill_username_queue()

        username = username_queue.get()
        with lock:
            if username in checked_usernames:
                continue

        proxy = get_proxy()
        result, status = check_username(username, proxy)

        if status == 429:
            release_proxy(proxy, bad=True)
            print(f"{bcolors.FAIL}[T{thread_id}] Rate limited. Retrying with new proxy...{bcolors.END}")
            time.sleep(1)
            username_queue.put(username)  # Retry this username
            continue
        else:
            release_proxy(proxy, bad=(result is None))

        record_checked(username)

        if result:
            log_success(username, thread_id)
        else:
            log_taken(username, thread_id)

# ========== START ==========
print(f"[*] Starting {THREADS} threads with rotating proxies. Press Ctrl+C to stop.\n")
refill_username_queue()

for i in range(THREADS):
    threading.Thread(target=worker, args=(i+1,), daemon=True).start()

try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("\n[!] Stopped by user.")
    print(f"\n✅ Found {len(successful_usernames)} valid usernames:\n")
    for u in successful_usernames:
        print(f" - {u}")
