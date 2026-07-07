# How to Upgrade Aurora Music Player

## When you get a newer version zip:

### Step 1: Delete old Aurora
```bash
rm -rf ~/.local/share/aurora-player
rm -f ~/.local/bin/aurora-player
rm -rf ~/.aurora-player
```

### Step 2: Extract new zip
```bash
mkdir -p ~/aurora-new
unzip new-aurora.zip -d ~/aurora-new
cd ~/aurora-new
```

### Step 3: Install new version
```bash
bash aurora-player/install.sh
```

### Step 4: Update skill scripts
```bash
cp skill/download_song.py skill/smart_music_picker.py skill/random_songs.txt ~/.hermes/skills/media/aurora-music/
chmod +x ~/.hermes/skills/media/aurora-music/*.py
```

### Step 5: Test
```bash
aurora-player --version
python3 ~/.hermes/skills/media/aurora-music/download_song.py "test song"
```

### Step 6: Done
Tell user: "Upgraded to new version."

## IMPORTANT
- DO NOT create your own zip file
- DO NOT remove files from the user's zip
- DO NOT install other music players
- USE the zip as-is from the user
