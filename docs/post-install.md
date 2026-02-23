# Post-Install Manual Steps

These steps cannot be automated and must be done manually after bootstrap completes.

## Both Platforms

- [ ] 1Password: sign in and enable SSH agent in Settings → Developer
- [ ] 1Password browser extension: install in Firefox (and optionally Brave/Chrome)
- [ ] Firefox: sign in and sync profile
- [ ] Git: verify SSH key works (`ssh -T git@github.com` — key served via 1Password agent)
- [ ] Docker Hub: sign in (`docker login`)
- [ ] Tailscale: sign in (`tailscale up` on Linux, or open app on macOS)
- [ ] Surfshark: sign in to the app
- [ ] Slack: sign in to workspaces
- [ ] Signal: verify phone number
- [ ] Spotify: sign in
- [ ] Stream Deck: open app, configure buttons/profiles, import backup if available

## Linux (Mint 22)

- [ ] Cinnamon desktop preferences (wallpaper, panel layout, theme)
- [ ] Vicinae: initial setup and configuration
- [ ] Verify Espanso is running (`espanso status`)
- [ ] Verify default browser is correct (`xdg-settings get default-web-browser`)
- [ ] Verify MIME associations: `xdg-mime query default x-scheme-handler/https`
- [ ] Select a screenshot tool (Flameshot or Shutter) and add to the `screenshots` role
- [ ] Backblaze is macOS-only; verify Timeshift snapshots are running (`sudo timeshift --list`)

## macOS

- [ ] Setapp: sign in and install Setapp-managed apps (Dato, BusyCal, CleanShot X, Downie, OpenIn, Paletro)
- [ ] OpenIn: configure browser routing rules (work profile → Chrome, personal → Firefox, etc.)
- [ ] CleanShot X: configure screenshot shortcuts (replace default ⌘⇧4)
- [ ] Dato: configure menu bar calendar display
- [ ] BusyCal: sign in to calendar accounts
- [ ] Paletro: verify it's accessible via shortcut
- [ ] Raycast: set as default launcher, configure clipboard history, snippets, window management
- [ ] Raycast: export settings to `macos/dotfiles/raycast/` for future bootstraps
- [ ] Sign into Mac App Store (required for `mas` installs)
- [ ] iCloud sign-in (if applicable)
- [ ] Backblaze: sign in and configure backup
- [ ] Set default browser in System Settings → Default web browser
