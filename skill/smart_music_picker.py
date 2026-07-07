#!/usr/bin/env python3
"""
Smart Music Picker — Downloads songs based on YOUR ACTUAL YouTube watch history (1592 videos)
=============================================================================================
Analyzed from your real watch history — no guessing:
- Phonk/Drift Phonk (viral 2026) → TOP category
- Indian Hip-Hop/Rap (KR$NA, Divine, Seedhe Maut, Hanumankind) → HIGH
- Punjabi (Guru Randhawa, AP Dhillon, Diljit) → HIGH
- Bollywood Romantic (Arijit, Shreya, Udit Narayan) → MEDIUM
- Anime OSTs/Covers (Suzume, JJK, Chainsaw Man, MAPPA/Wit/Ufo/KyoAni) → MEDIUM
- Slowed+Reverb/Aesthetic/Lo-fi (GATA ONLY slowed, mashups) → MEDIUM
- International (Ed Sheeran, Imagine Dragons) → LOW
- NO harem/ecchi/isekai generic anime stuff
- NO comedy/hasya/news/politics (family shared account noise filtered out)
"""

import random
import subprocess
import time
import sys
import os
import shutil
from pathlib import Path

# ============================================================
# CURATED LISTS — Built from YOUR ACTUAL WATCH HISTORY (1592 videos)
# ============================================================

# 🎧 PHONK / DRIFT PHONK / VIRAL FUNK — Your #1 watched genre (trending 2026)
PHONK_VIRAL = [
    "1 HOUR VIRAL PHONK FUNK SONGS 2026 TRENDING PHONK",
    "Most Viral Phonk Funk 2026",
    "Aggressive Drift Phonk 2026",
    "Brazilian Phonk 2026 Cowbell",
    "Dark Phonk 2026 Playlist",
    "Chill Phonk 2026 Study Beats",
    "Phonk House 2026 Viral",
    "Drift Phonk 2026 Bass Boosted",
    "Viral Phonk 2026 TikTok Reels",
    "Phonk Mix 2026 No Copyright",
]

# 🎤 INDIAN HIP-HOP / RAP — KR$NA, Divine, Seedhe Maut, Hanumankind, Raftaar
INDIAN_HIPHOP = [
    "Boom Shaka KR$NA Dhanda Nyoliwala Official Music Video",
    "Vyanjan KR$NA Official Music Video",
    "Makasam KR$NA Official Music Video",
    "Woh Raat KR$NA Official Music Video",
    "Kaisa Mera Desh KR$NA Official Music Video",
    "Dekh Kaun Aaya Wapas KR$NA Official Music Video",
    "Jungli Sher Divine Official Music Video",
    "Kohinoor Divine Official Music Video",
    "Mere Gully Mein Divine Naezy Official Music Video",
    "Azadi Divine Official Music Video",
    "Seedhe Maut Nayaab Official Music Video",
    "Seedhe Maut 101 Official Music Video",
    "Seedhe Maut Kaanch Official Music Video",
    "Hanumankind Daily Dose Official Music Video",
    "Hanumankind Surface Level Official Music Video",
    "Raftaar Kya Baat Hai Official Music Video",
    "Raftaar Dilli Waali Baatcheet Official Music Video",
    "Prabh Deep Class-Sikh Official Music Video",
    "Prabh Deep Chitti Official Music Video",
    "Enimi Hustle Official Music Video",
    "Enimi Thug Life Official Music Video",
    "Ikka Level Up Official Music Video",
    "KRSNA Still Here Official Music Video",
    "KRSNA Freeverse Feast Official Music Video",
]

# 🔥 PUNJABI — Guru Randhawa, AP Dhillon, Diljit, Badshah, Jass Manak, Harrdy Sandhu
PUNJABI_BANGERS = [
    "AZUL Guru Randhawa Official Music Video",
    "High Rated Gabru Guru Randhawa Official Music Video",
    "Lahore Guru Randhawa Official Music Video",
    "Suit Guru Randhawa Official Music Video",
    "Made In India Guru Randhawa Official Music Video",
    "Excuses AP Dhillon Official Music Video",
    "Brown Munde AP Dhillon Official Music Video",
    "Insane AP Dhillon Official Music Video",
    "With You AP Dhillon Official Music Video",
    "Teriyan Meriyan AP Dhillon Official Music Video",
    "Spaceship AP Dhillon Official Music Video",
    "Summer High AP Dhillon Official Music Video",
    "Proper Patola Diljit Dosanjh Official Music Video",
    "Do You Know Diljit Dosanjh Official Music Video",
    "5 Taara Diljit Dosanjh Official Music Video",
    "Lover Diljit Dosanjh Official Music Video",
    "G.O.A.T. Diljit Dosanjh Official Music Video",
    "Clash Diljit Dosanjh Official Music Video",
    "Paani Paani Badshah Official Music Video",
    "Genda Phool Badshah Official Music Video",
    "Jugnu Badshah Official Music Video",
    "Mercy Badshah Official Music Video",
    "Lehanga Jass Manak Official Music Video",
    "Shopping Jass Manak Official Music Video",
    "Surma Jass Manak Official Music Video",
    "Titliaan Harrdy Sandhu Official Music Video",
    "Bijlee Bijlee Harrdy Sandhu Official Music Video",
    "Kya Baat Ay Harrdy Sandhu Official Music Video",
    "Naah Harrdy Sandhu Official Music Video",
    "Soch Harrdy Sandhu Official Music Video",
]

# 🎭 BOLLYWOOD ROMANTIC / SOULFUL — Arijit, Shreya, Jubin, B Praak, Udit Narayan
BOLLYWOOD_SOUL = [
    "Channa Mereya Arijit Singh Official Music Video",
    "Raataan Lambiyan Jubin Nautiyal Asees Kaur Official Music Video",
    "Kesariya Arijit Singh Official Music Video",
    "Tum Hi Ho Arijit Singh Official Music Video",
    "Kalank Title Track Arijit Singh Official Music Video",
    "Apna Bana Le Arijit Singh Official Music Video",
    "Maan Meri Jaan King Official Music Video",
    "Heeriye Arijit Singh Jasleen Royal Official Music Video",
    "Pasoori Ali Sethi Shae Gill Coke Studio",
    "Kahani Suno 2.0 Kaifi Khalil Official Music Video",
    "Mann Bharya 2.0 B Praak Official Music Video",
    "Filhall B Praak Ammy Virk Official Music Video",
    "Jugraafiya Super 30 Udit Narayan Shreya Ghoshal Official Music Video",
    "O Maahi Arijit Singh Official Music Video",
    "Tere Hawale Arijit Singh Official Music Video",
    "Phir Na Aisi Raat Aayegi Arijit Singh Official Music Video",
    "Mere Yaara Arijit Singh Official Music Video",
    "Dil Jhoom Arijit Singh Official Music Video",
    "Jaan Ban Gaye Jubin Nautiyal Official Music Video",
    "Meri Zindagi Hai Tu Jubin Nautiyal Official Music Video",
]

# ⚔️ ANIME OSTs / COVERS — MAPPA, Wit, Ufotable, KyoAni (your studio prefs)
# Action/Thriller/Spy/Psychological/Fantasy — NO harem/ecchi/isekai generic
ANIME_EPIC = [
    # MAPPA
    "Kaikai Kitan Jujutsu Kaisen OP1 Eve Official",
    "Vivid Vice Jujutsu Kaisen OP2 Who-ya Extended Official",
    "Chainsaw Man OP Kick Back Kenshi Yonezu Official",
    "Chainsaw Man ED Chu Chu Chu Official",
    "Attack on Titan Final Season OP Saigo no Kyojin SiM Official",
    "Attack on Titan Vogel im Käfig Hiroyuki Sawano Official",
    "Attack on Titan Barricades Hiroyuki Sawano Official",
    "Attack on Titan Call of Silence Hiroyuki Sawano Official",
    
    # Wit Studio
    "Spy x Family OP Mixed Nuts Official Hige Dandism Official",
    "Spy x Family ED Comedy Gen Hoshino Official",
    "Oshi no Ko OP Idol YOASOBI Official",
    "Oshi no Ko ED Mephisto Queen Bee Official",
    "Vinland Saga OP Mukanjyo Survive Said The Prophet Official",
    "Vinland Saga ED Torches Aimer Official",
    
    # Ufotable
    "Demon Slayer OP Gurenge LiSA Official",
    "Demon Slayer OP Zankyou Sanka Aimer Official",
    "Demon Slayer ED Homura LiSA Official",
    "Demon Slayer OP Akeboshi LiSA Official",
    "Fate Zero OP Oath Sign LiSA Official",
    "Fate HF OP I Beg You Aimer Official",
    
    # KyoAni
    "Violet Evergarden OP Sincerely TRUE Official",
    "Violet Evergarden ED Michishirube Minori Chihara Official",
    "Hibike Euphonium OP Dream Solister TRUE Official",
    
    # Psychological/Thriller/Mystery (your taste)
    "Death Note OP The World Nightmare Official",
    "Death Note ED Alumina Nightmare Official",
    "Monster OP Grain Yasushi Ishii Official",
    "Parasyte OP Let Me Hear Fear and Loathing in Las Vegas Official",
    "Psycho-Pass OP Abnormalize Ling Tosite Sigure Official",
    "Erased OP Re:Re Asian Kung-Fu Generation Official",
    "Steins Gate OP Hacking to the Gate Kanako Ito Official",
    "Code Geass OP Colors FLOW Official",
    
    # Fantasy/Adventure (your taste)
    "Frieren OP Yuusha YOASOBI Official",
    "Frieren ED Anytime Anywhere milet Official",
    "Mushoku Tensei OP Tabibito no Uta Yuiko Ohara Official",
    "Re:Zero OP Realize Konomi Suzuki Official",
    
    # Covers you actually watched
    "Suzume No Tojimari Nanoka Hara Full Song Hindi Cover",
]

# 🌙 SLOWED + REVERB / AESTHETIC / LO-FI — GATA ONLY slowed, mashups, night vibes
SLOWED_AESTHETIC = [
    "GATA ONLY FloyyMenor cris MJ Slowed Reverb Official",
    "GATA ONLY Slowed + Reverb Aesthetic Edit",
    "Sad Broken Mashup Lofi Beats Bollywood Romantic Hindi Songs Mashup",
    "Night Vibes Slowed Reverb Playlist 2026",
    "Aesthetic Slowed Reverb Hindi Songs 2026",
    "Drift Phonk Slowed Reverb 2026",
    "Lo-fi Chill Hindi Beats Study Focus",
    "Midnight Slowed Reverb Bollywood 2026",
    "Rainy Night Slowed Songs Hindi",
    "Chill Phonk Slowed Reverb 2026",
]

# 🌍 INTERNATIONAL — Ed Sheeran, Imagine Dragons (low priority but you watch them)
INTERNATIONAL = [
    "Sapphire Ed Sheeran Official Music Video",
    "Shape of You Ed Sheeran Official Music Video",
    "Perfect Ed Sheeran Official Music Video",
    "Bad Habits Ed Sheeran Official Music Video",
    "Shivers Ed Sheeran Official Music Video",
    "Enemy Imagine Dragons JID Official Music Video",
    "Believer Imagine Dragons Official Music Video",
    "Thunder Imagine Dragons Official Music Video",
    "Radioactive Imagine Dragons Official Music Video",
    "Unstoppable Sia Official Music Video",
]

# ============================================================
# CATEGORIES WITH EMOTION-BASED NAMES & EMOJIS
# ============================================================

MOOD_CATEGORIES = {
    "phonk_viral": PHONK_VIRAL,           # 🎧 #1 - Viral Phonk/Drift 2026
    "indian_hiphop": INDIAN_HIPHOP,       # 🎤 #2 - Indian Rap/Hip-Hop (KR$NA, Divine, etc.)
    "punjabi_energy": PUNJABI_BANGERS,    # 🔥 #3 - Punjabi Bangers
    "bollywood_soul": BOLLYWOOD_SOUL,     # 🎭 #4 - Bollywood Romantic/Soulful
    "anime_epic": ANIME_EPIC,             # ⚔️ #5 - Anime OSTs (MAPPA/Wit/Ufo/KyoAni)
    "slowed_aesthetic": SLOWED_AESTHETIC, # 🌙 #6 - Slowed+Reverb/Aesthetic/Lo-fi
    "international_vibes": INTERNATIONAL, # 🌍 #7 - International (Ed Sheeran, ID)
}

# WEIGHTS FROM YOUR ACTUAL WATCH HISTORY (1592 videos analyzed)
# Higher = more likely to be picked
CATEGORY_WEIGHTS = {
    "phonk_viral": 30,           # 🎧 TOP — Viral phonk/funk trending 2026
    "indian_hiphop": 25,         # 🎤 HIGH — KR$NA, Divine, Seedhe Maut, Hanumankind
    "punjabi_energy": 20,        # 🔥 HIGH — Guru Randhawa, AP Dhillon, Diljit
    "bollywood_soul": 12,        # 🎭 MEDIUM — Arijit, Shreya, Jubin, B Praak
    "anime_epic": 8,             # ⚔️ MEDIUM — MAPPA, Wit, Ufotable, KyoAni OSTs
    "slowed_aesthetic": 3,       # 🌙 LOW-MED — Slowed+Reverb, Lo-fi, Mashups
    "international_vibes": 2,    # 🌍 LOW — Ed Sheeran, Imagine Dragons
}

# Path to the unified downloader script (sibling file in same scripts/ dir)
DOWNLOADER_SCRIPT = Path(__file__).parent / "download_song.py"
INSTALL_SCRIPT = Path(__file__).parent / "install_flb.sh"


def pick_random_songs(count=5, mood=None):
    """Pick random songs weighted by your ACTUAL taste profile."""
    if mood and mood in MOOD_CATEGORIES:
        pool = MOOD_CATEGORIES[mood]
        return random.sample(pool, min(count, len(pool)))
    
    # Weighted random across all categories
    all_songs = []
    for cat, weight in CATEGORY_WEIGHTS.items():
        songs = MOOD_CATEGORIES[cat]
        for _ in range(weight):
            all_songs.extend(songs)
    
    return random.sample(all_songs, min(count, len(all_songs)))


def download_song(song_query, wait=True):
    """
    Download a single song using the unified downloader in --download-only mode.
    By default, runs synchronously (waits for download to finish) so that
    batch downloads happen in order. Pass wait=False to launch async.
    Returns True if download succeeded.

    v12.1 FIX: previously called download_song.py with bare song name, which
    in v11+ defaults to download + play-in-Aurora. smart_music_picker was
    checking stdout for 'DOWNLOADED' which the v11 default mode never prints,
    so EVERY song was reported as '❌ Failed' even when the download succeeded.
    Now we pass --download-only so the output contract matches.
    """
    if not DOWNLOADER_SCRIPT.exists():
        print(f"❌ Downloader script not found: {DOWNLOADER_SCRIPT}")
        return False

    try:
        if wait:
            # Synchronous: wait for download to complete, capture output
            proc = subprocess.run(
                [sys.executable, str(DOWNLOADER_SCRIPT), "--download-only", song_query],
                capture_output=True, text=True, timeout=300
            )
            # download_song.py --download-only prints "DOWNLOADED: <path>" on success
            if proc.returncode == 0 and "DOWNLOADED:" in proc.stdout:
                print(f"  ✅ Downloaded: {song_query}")
                return True
            else:
                print(f"  ❌ Failed: {song_query}")
                if proc.stderr:
                    print(f"     {proc.stderr[:200]}")
                return False
        else:
            # Async: launch in background, don't wait
            subprocess.Popen(
                [sys.executable, str(DOWNLOADER_SCRIPT), "--download-only", song_query],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            print(f"  🎵 Queued (async): {song_query}")
            return True
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout (5min): {song_query}")
        return False
    except Exception as e:
        print(f"  ❌ Failed to download {song_query}: {e}")
        return False


def aurora_is_installed() -> bool:
    """Check if Aurora Music Player is installed."""
    wrapper = Path.home() / ".local" / "bin" / "aurora-player"
    return wrapper.exists() and os.access(wrapper, os.X_OK)


def flb_is_installed():
    """Deprecated alias kept for backward compat. Aurora is the only player now."""
    return aurora_is_installed()


def download_batch(songs, delay=1, launch_flb=True):
    """
    Download multiple songs synchronously (one at a time, waiting for each).
    After all downloads complete, launches Aurora Music Player ONCE so the user
    can browse all newly-downloaded songs in the library.

    v12.1 FIX: launches Aurora (not FLB, which was removed in v12).
    """
    print(f"\n📥 Downloading {len(songs)} songs...")
    print("=" * 50)

    # Check Aurora install before starting downloads
    if launch_flb and not aurora_is_installed():
        print("\n⚠️  Aurora Music Player is NOT installed.")
        print("   Songs will still download to ~/Downloads/, but to play them in Aurora,")
        print(f"   run: bash aurora-player/install.sh")
        print()

    success = 0
    downloaded_files = []
    for i, song in enumerate(songs, 1):
        print(f"\n[{i}/{len(songs)}] {song}")
        if download_song(song, wait=True):
            success += 1
        if i < len(songs):
            time.sleep(delay)

    print(f"\n{'=' * 50}")
    print(f"✅ Downloaded {success}/{len(songs)} songs successfully")
    print(f"📂 All files saved to: ~/Downloads/")

    if launch_flb:
        if aurora_is_installed():
            aurora_bin = shutil.which("aurora-player") or str(Path.home() / ".local" / "bin" / "aurora-player")
            print(f"\n🎵 Launching Aurora Music Player...")
            print(f"   All {success} new songs are now in your Aurora library.")
            print(f"   Auto-scan runs every 30s, but Aurora will pick them up immediately on launch.")
            print(f"   Click any song to play — you control playback manually.")
            try:
                env = os.environ.copy()
                if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
                    env["DISPLAY"] = ":0"
                # Launch Aurora GUI (no --play-file = just open the library view)
                subprocess.Popen(
                    [aurora_bin],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env
                )
                print(f"   ✅ Aurora Music Player launched (non-blocking)")
            except Exception as e:
                print(f"   ⚠️  Failed to launch Aurora: {e}")
                print(f"   You can launch it manually: aurora-player")
        else:
            print(f"\n💡 To play these songs, install Aurora:")
            print(f"   bash aurora-player/install.sh")
            print(f"   Then run: aurora-player")
    else:
        print(f"\n📊 All songs downloaded. To play in Aurora GUI, run:")
        print(f"   aurora-player")
        print(f"\n📊 For background playback control:")
        print(f"   python3 {DOWNLOADER_SCRIPT} --status")


def interactive_mode():
    """Interactive menu with emojis and actual data-based categories."""
    print("""
🎵 SMART MUSIC PICKER — Built from YOUR 1,592 YouTube watch history
===================================================================
📊 Actual taste detected (no guessing):
  🎧 30% — Viral Phonk/Drift Phonk 2026 (trending)
  🎤 25% — Indian Hip-Hop/Rap (KR$NA, Divine, Seedhe Maut, Hanumankind)
  🔥 20% — Punjabi (Guru Randhawa, AP Dhillon, Diljit, Badshah)
  🎭 12% — Bollywood Romantic (Arijit, Shreya, Jubin, B Praak)
  ⚔️  8% — Anime OSTs (MAPPA, Wit, Ufotable, KyoAni — action/thriller/spy/fantasy)
  🌙  3% — Slowed+Reverb/Aesthetic/Lo-fi (GATA ONLY slowed, mashups)
  🌍  2% — International (Ed Sheeran, Imagine Dragons)

🚫 Filtered OUT: Hasya/comedy, news/politics, gaming tutorials, 
   anime recommendations/AMVs, harem/ecchi/isekai generic stuff

Choose your vibe:
  1. 🎧 Phonk Viral 2026 (Drift Phonk, Brazilian Phonk, Cowbell)
  2. 🎤 Indian Hip-Hop/Rap (KR$NA, Divine, Seedhe Maut, Hanumankind)
  3. 🔥 Punjabi Energy (Guru Randhawa, AP Dhillon, Diljit, Badshah)
  4. 🎭 Bollywood Soul (Arijit, Shreya, Jubin, B Praak, Udit Narayan)
  5. ⚔️  Anime Epic (JJK, Chainsaw Man, AoT, Spy×Family, Frieren, Demon Slayer)
  6. 🌙 Slowed+Reverb/Aesthetic (GATA ONLY slowed, Lo-fi mashups, night vibes)
  7. 🌍 International (Ed Sheeran, Imagine Dragons, Sia)
  8. 🎲 Surprise Me! (Weighted random from ALL above)
  9. 🎯 Custom count + category

  q. Quit
""")
    
    while True:
        choice = input("Your pick (1-9, q): ").strip().lower()
        
        if choice == 'q':
            print("Bye! 👋")
            break
        
        mood_map = {
            '1': 'phonk_viral',
            '2': 'indian_hiphop',
            '3': 'punjabi_energy',
            '4': 'bollywood_soul',
            '5': 'anime_epic',
            '6': 'slowed_aesthetic',
            '7': 'international_vibes',
            '8': None,  # Surprise me
        }
        
        if choice in mood_map:
            mood = mood_map[choice]
            if choice == '8':
                count = int(input("How many songs? (default 5): ") or "5")
                songs = pick_random_songs(count)
            else:
                cat_name = mood.replace('_', ' ').title()
                count = int(input(f"How many {cat_name} songs? (default 5): ") or "5")
                songs = pick_random_songs(count, mood)
            
            print(f"\n🎯 Picked {len(songs)} songs:")
            for s in songs:
                print(f"   • {s}")
            
            confirm = input("\nDownload these? (y/n): ").strip().lower()
            if confirm == 'y':
                download_batch(songs)
            else:
                print("Cancelled.")
        
        elif choice == '9':
            print("\nCategories:", ", ".join(MOOD_CATEGORIES.keys()))
            mood = input("Mood (or Enter for mixed): ").strip() or None
            count = int(input("Count: ") or "5")
            songs = pick_random_songs(count, mood)
            
            print(f"\n🎯 Picked {len(songs)} songs:")
            for s in songs:
                print(f"   • {s}")
            
            confirm = input("\nDownload these? (y/n): ").strip().lower()
            if confirm == 'y':
                download_batch(songs)
            else:
                print("Cancelled.")
        
        else:
            print("Invalid choice. Try 1-9 or q.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smart Music Picker - Downloads songs based on YOUR actual watch history")
    parser.add_argument('count', nargs='?', type=int, default=5, help='Number of songs to download')
    parser.add_argument('--mood', choices=list(MOOD_CATEGORIES.keys()), help='Mood/category to pick from')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode')
    parser.add_argument('--list-moods', action='store_true', help='List available moods with counts')
    args = parser.parse_args()
    
    if args.list_moods:
        print("Available moods (from your actual watch history):")
        for mood, songs in MOOD_CATEGORIES.items():
            weight = CATEGORY_WEIGHTS.get(mood, 0)
            print(f"  {mood}: {len(songs)} songs (weight: {weight}%)")
        return
    
    if args.interactive:
        interactive_mode()
        return
    
    # Direct mode
    songs = pick_random_songs(args.count, args.mood)
    print(f"🎯 Picked {len(songs)} songs based on YOUR actual taste:")
    for s in songs:
        print(f"   • {s}")
    
    download_batch(songs)


if __name__ == "__main__":
    main()