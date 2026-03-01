import os, sys, subprocess, json, getpass

BW_EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "bin", "bw.exe")
SSH_KEY_MAIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "git", ".ssh", "id_ed25519_main")
SSH_KEY_SECURITY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "git", ".ssh", "id_ed25519_security")

MAPPINGS = [
    {"name": "Github Oleksii Rovnianskyi (oleksii-rovnianskyi)", "key_file": SSH_KEY_MAIN},
    {"name": "Github Oleksii Rovnianskyi 0scorp919", "key_file": SSH_KEY_SECURITY}
]

def unlock_bw():
    try:
        env = os.environ.copy()
        env["BITWARDENCLI_APPDATA_DIR"] = os.path.join(os.path.dirname(BW_EXE), ".bw_data")

        # Load env for host config
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k.strip() == "BW_HOST":
                            subprocess.run([BW_EXE, "config", "server", v.strip().strip("'\"")], capture_output=True, env=env)

        status = json.loads(subprocess.run([BW_EXE, "status"], capture_output=True, text=True, env=env).stdout).get("status")
        if status == "unlocked":
            res = subprocess.run([BW_EXE, "unlock", "--raw"], capture_output=True, text=True, env=env)
            if res.returncode == 0: return res.stdout.strip(), env

        mp = getpass.getpass("Enter Vaultwarden Master Password: ")
        env["BW_PASSWORD"] = mp
        res = subprocess.run([BW_EXE, "unlock", "--passwordenv", "BW_PASSWORD", "--raw"], capture_output=True, text=True, env=env)
        if res.returncode == 0: return res.stdout.strip(), env
        return None, None
    except Exception as e:
        print(f"Error unlocking BW: {e}")
        return None, None

def get_item(name, token, env):
    res = subprocess.run([BW_EXE, "get", "item", name, "--session", token], capture_output=True, text=True, env=env)
    if res.returncode == 0:
        return json.loads(res.stdout)
    return None

def update_item(item, token, env):
    item_json = json.dumps(item)
    # The record might have reprompt on, requiring the password again? "bw encode" can prepare the JSON, then "bw edit item <id>"
    encoded = subprocess.run([BW_EXE, "encode"], input=item_json, capture_output=True, text=True, env=env).stdout.strip()
    res = subprocess.run([BW_EXE, "edit", "item", item["id"], encoded, "--session", token], capture_output=True, text=True, env=env)
    return res.returncode == 0

def migrate():
    print("Checking Vaultwarden status...")
    token, env = unlock_bw()
    if not token:
        print("Failed to unlock Vaultwarden.")
        return

    subprocess.run([BW_EXE, "sync", "--session", token], capture_output=True, env=env)

    for mapping in MAPPINGS:
        name = mapping["name"]
        key_file = mapping["key_file"]
        if not os.path.exists(key_file):
            print(f"Key file {key_file} not found. Skipping {name}.")
            continue

        print(f"\nProcessing {name}...")
        with open(key_file, "r") as f:
            key_content = f.read().strip()

        item = get_item(name, token, env)
        if not item:
            print(f"Item '{name}' not found in Vaultwarden!")
            continue

        # Update custom field "SSH"
        fields = item.get("fields", [])
        ssh_field = None
        for f in fields:
            if f["name"] == "SSH":
                ssh_field = f
                break

        if ssh_field:
            ssh_field["value"] = key_content
        else:
            fields.append({"name": "SSH", "value": key_content, "type": 1}) # 1 = text/hidden text
            item["fields"] = fields

        print(f"Uploading key for {name}...")
        if update_item(item, token, env):
            print("Successfully updated Vaultwarden.")
            print(f"Removing local key {key_file}...")
            os.remove(key_file)
            pub_key = key_file + ".pub"
            if os.path.exists(pub_key):
                os.remove(pub_key)
        else:
            print("Failed to update item.")

if __name__ == "__main__":
    migrate()
