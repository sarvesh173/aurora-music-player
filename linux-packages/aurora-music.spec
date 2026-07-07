Name:       aurora-music
Version:    17.5.0
Release:    1%{?dist}
Summary:    Lightweight Material 3 music player with browse, equalizer, visualizer
License:    MIT
URL:        https://github.com/aurora/aurora-music
Source0:    aurora_player.py
BuildArch:  noarch
Requires:   python3-pyside6-qtwidgets
Requires:   python3-pyside6-qtmultimedia
Requires:   python3-pyside6-qtsvg
Requires:   python3-numpy
Requires:   python3-mutagen
Requires:   ffmpeg
Recommends: yt-dlp

%description
Aurora Music Player — a fast, native Qt music player with Material Design 3
dark theme. Features: library scan, browse (iTunes search + yt-dlp download),
10-band equalizer, 6-mode visualizer with real-time audio sync, A-B loop,
playlists, queue, live hue-slider theming, agent CLI.

%prep
cp %{SOURCE0} .

%install
install -Dm755 aurora_player.py %{buildroot}/opt/aurora-music/aurora_player.py
install -d %{buildroot}/usr/bin
cat > %{buildroot}/usr/bin/aurora-music << 'LAUNCHER'
#!/usr/bin/env bash
exec python3 /opt/aurora-music/aurora_player.py "$@"
LAUNCHER
chmod +x %{buildroot}/usr/bin/aurora-music

%files
/opt/aurora-music/aurora_player.py
/usr/bin/aurora-music

%changelog
* Mon Jul 07 2026 Aurora Project - 17.5.0-1
- v17.5: Real-time audio sync (QAudioBufferOutput), A-B loop, button animations
