# Aurora Music — Linux Packages

This folder contains build scripts for all major Linux package formats.

## Supported Formats

| Format | File | Target Distros |
|--------|------|----------------|
| **Debian (.deb)** | `build-debian.sh` | Debian, Ubuntu, Kali, Mint, Pop!_OS |
| **AppImage** | `build-appimage.sh` | Any Linux (portable, no install) |
| **Arch (PKGBUILD)** | `PKGBUILD` | Arch Linux, Manjaro, EndeavourOS |
| **Flatpak** | `com.aurora.Music.json` | Any Linux (sandboxed) |
| **RPM (.spec)** | `aurora-music.spec` | Fedora, openSUSE, RHEL, CentOS |

## Quick Build

### Debian/Kali/Ubuntu
```bash
bash linux-packages/build-debian.sh
# Output: packages/aurora-music_17.5.0_all.deb
sudo apt install ./packages/aurora-music_17.5.0_all.deb
```

### AppImage (portable)
```bash
bash linux-packages/build-appimage.sh
# Output: aurora-music-x86_64.AppImage
./aurora-music-x86_64.AppImage  # run without installing
```

### Arch Linux
```bash
cd linux-packages
makepkg -si
```

### Flatpak
```bash
flatpak-builder build-dir linux-packages/com.aurora.Music.json
flatpak build build-dir aurora-music
```

### Fedora/RPM
```bash
rpmbuild -ba linux-packages/aurora-music.spec
```

## Dependencies (all formats)
- Python 3.9+
- PySide6 (Qt 6.8+ for real-time audio sync)
- numpy
- mutagen
- ffmpeg
- yt-dlp (optional, for Browse downloads)

## Kernel Compatibility
- Linux kernel 5.4+ (Ubuntu 20.04+, Debian 11+, Kali 2023+)
- glibc 2.31+
- Works on x86_64, aarch64 (ARM64)
