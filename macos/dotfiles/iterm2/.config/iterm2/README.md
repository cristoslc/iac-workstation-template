# iTerm2 Preferences

iTerm2 can load preferences from a custom directory.

## Setup

1. Open iTerm2 → Settings → General → Preferences
2. Check "Load preferences from a custom folder or URL"
3. Set the path to: `~/.config/iterm2`
4. Check "Save changes to folder when iTerm2 quits"

After initial setup, iTerm2 will write its preferences to this directory.
The preferences file (`com.googlecode.iterm2.plist`) will be managed by stow.

## First Machine

Configure iTerm2 to your liking, then the plist file appears here automatically.

## Subsequent Machines

After stow deploys this directory, iTerm2 picks up the preferences on next launch.
