# macOS-specific shell configuration.

# Modern ls replacement
if command -v eza &>/dev/null; then
  alias ls='eza'
  alias ll='eza -l'
  alias la='eza -la'
fi

# Use bat for cat
if command -v bat &>/dev/null; then
  alias cat='bat --paging=never'
fi

# macOS-specific aliases
alias flushdns='sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder'
alias showfiles='defaults write com.apple.finder AppleShowAllFiles YES; killall Finder'
alias hidefiles='defaults write com.apple.finder AppleShowAllFiles NO; killall Finder'
