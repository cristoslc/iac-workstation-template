# shellcheck shell=bash
# Zsh completion system.

autoload -Uz compinit
compinit -d "${XDG_CACHE_HOME:-$HOME/.cache}/zsh/zcompdump"

# Case-insensitive matching for lowercase input.
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}'

# Group completions by type.
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '%B%d%b'
