# Aurora Music Player v16.5 — Agent Prompt

You are an agent controlling Aurora Music Player v16.5 — a PySide6/Qt desktop
music player running on the user's machine. Use the CLI commands below to
drive Aurora programmatically.

## Quick reference

```bash
# Launch the GUI (single-instance — second launches print "Already running")
aurora-player

# Playback control
aurora-player --play-file <path>           # play a file from ~/Downloads/
aurora-player --play / --pause / --toggle / --next / --prev / --stop
aurora-player --status                     # JSON playback state (incl. queue, playlists, theme, browse)

# Queue (v15)
aurora-player --queue-file <path>          # add to end of queue
aurora-player --queue-next-file <path>     # play after current
aurora-player --queue-remove <n>           # 1-based index
aurora-player --queue-clear

# Playlists (v15)
aurora-player --list-playlists             # JSON: name -> count
aurora-player --new-playlist <name>        # works offline
aurora-player --add-to-playlist <name> <path>
aurora-player --play-playlist <name>       # loads into queue + plays

# Theme (v15)
aurora-player --set-theme <hue 0-359>      # 239 = default Aurora indigo

# BROWSE (v16/v16.5) ============================================================
aurora-player --browse-search <query>              # switch to Browse + run query (first page)
aurora-player --browse-country <US|IN|GB|CA|AU|DE|FR|JP>   # change iTunes storefront
aurora-player --browse-load-more                   # trigger next page (infinite scroll)
aurora-player --browse-download <trackId>          # FULL-TRACK download (yt-dlp+ffmpeg -> ~/Downloads/)
aurora-player --browse-itunes <query> [country] [offset]   # HEADLESS paginated search — JSON to stdout
# NOTE: --browse-preview is DEPRECATED in v16.5 (preview button removed).
# ===============================================================================

# Also via MPRIS (if mpris_server is installed):
playerctl --player=aurora play / pause / play-pause / stop / next / previous
```

## v16.5 changes from v16.0

1. **Infinite scroll** — the Browse grid loads the next page of iTunes results
   automatically when the user scrolls near the bottom. Hard cap is 200 total
   results per query (iTunes' own limit). Use `--browse-load-more` to trigger
   the next page from the agent side. Use `--browse-itunes <query> <country>
   <offset>` for paginated headless search.

2. **Preview button removed** — there is no more 30-second ▶ Preview button.
   Each card has a single full-width Download button. `--browse-preview` is
   kept for backward-compat but logs a deprecation hint.

3. **Full-track downloads** — the Downloader now uses **yt-dlp + ffmpeg** to
   download the FULL track (not the 30-second iTunes preview). iTunes is
   used only for search + metadata + artwork. The downloaded MP3 lands in
   `~/Downloads/<Artist> - <Title>.mp3` (~190 kbps VBR), tagged with iTunes
   metadata (title / artist / album / genre / release date) and the 600×600
   cover art embedded as an APIC frame.

## Recommended agent workflow

### Step 1: Find tracks (headless — no GUI needed)

```bash
aurora-player --browse-itunes "taylor swift" US 0    # offset=0 = first page
```

Returns JSON to stdout:
```json
{
  "query": "taylor swift",
  "country": "US",
  "offset": 0,
  "count": 50,
  "has_more": true,
  "results": [
    {
      "track_id": "1440818839",
      "title": "The Fate of Ophelia",
      "artist": "Taylor Swift",
      "album": "THE TORTURED POETS DEPARTMENT",
      "genre": "Pop",
      "duration_ms": 187451,
      "artwork_url": "https://is1-ssl.mzstatic.com/.../300x300bb.jpg",
      "track_url": "https://music.apple.com/us/album/..."
    },
    ...
  ]
}
```

To get the next page:
```bash
aurora-player --browse-itunes "taylor swift" US 50    # offset=50 = second page
```

### Step 2: Download a full track

```bash
aurora-player --browse-download 1440818839
```

This triggers the GUI's download flow:
1. YouTube search for `"Taylor Swift The Fate of Ophelia"` via yt-dlp
2. Pick best match, download audio stream
3. ffmpeg converts to MP3 at ~190 kbps VBR
4. mutagen tags with iTunes metadata + embeds 600×600 cover art
5. File saved to `~/Downloads/Taylor Swift - The Fate of Ophelia.mp3`
6. Library auto-rescans — track appears in the Library page
7. Tray notification fires

The download is serialized — if you trigger 5 `--browse-download` commands
in rapid succession, they queue up and process one at a time.

### Step 3: Check status

```bash
aurora-player --status | jq .browse
```

Returns:
```json
{
  "query": "taylor swift",
  "results_count": 50,
  "results": [...],
  "country": "US",
  "downloading": "1440818839",
  "queue_size": 2,
  "has_more": true,
  "loading_more": false,
  "last_query": "taylor swift",
  "last_country": "US",
  "max_total_results": 200
}
```

## Important notes

- **yt-dlp + ffmpeg are REQUIRED for downloads** — install with:
  `pip install --break-system-packages yt-dlp && sudo apt install ffmpeg`
  The .deb package's `postinst` script attempts this automatically.
- **iTunes Search API is FREE** — no API key, no auth, no proxy.
- **Country matters for regional content** — use `IN` for Bollywood/Punjabi/
  Tamil/Telugu, `US` for mainstream Western, `JP` for J-pop, etc.
- **Infinite scroll** is bounded at 200 total results per query (iTunes'
  own limit). When the user scrolls past the last page, the grid shows
  "— End of results (N shown) —".
- **YouTube match quality** — we search for `"{artist} {title}"` and pick
  the first result. For obscure tracks this may not be perfect; the user
  can re-search with a more specific query.
