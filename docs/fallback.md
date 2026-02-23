# Fallback: Swap Vicinae for Ulauncher + CopyQ

If Vicinae instability becomes a problem on Linux, swap to Ulauncher + CopyQ.

## Steps

```bash
# 1. Unstow Vicinae dotfiles
cd ~/.workstation/linux/dotfiles && stow -D vicinae

# 2. Install replacements
sudo apt install -y copyq
# Ulauncher via PPA: https://ulauncher.io/#Download
sudo add-apt-repository ppa:agornostal/ulauncher
sudo apt update && sudo apt install -y ulauncher

# 3. Remap keyboard shortcuts
# Open Cinnamon Settings > Keyboard > Shortcuts > Custom
# Replace Vicinae deeplink commands with:
#   Super+V → copyq toggle
#   Super+Space → ulauncher-toggle

# 4. If you create dotfiles for the replacements:
# mkdir -p ~/.workstation/linux/dotfiles/copyq/.config/copyq
# mkdir -p ~/.workstation/linux/dotfiles/ulauncher/.config/ulauncher
# stow copyq && stow ulauncher
```
