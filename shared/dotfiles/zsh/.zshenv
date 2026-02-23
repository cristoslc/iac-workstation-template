# shellcheck shell=bash
# Managed by iac-daily-driver-environments.
# PATH setup lives here — sourced before .zshrc, so fragment load order doesn't matter.

# Homebrew (macOS)
if [ -d /opt/homebrew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# uv
if [ -d "$HOME/.local/bin" ]; then
  export PATH="$HOME/.local/bin:$PATH"
fi

# fnm (Node version manager)
if [ -d "$HOME/.local/share/fnm" ]; then
  export PATH="$HOME/.local/share/fnm:$PATH"
  eval "$(fnm env --use-on-cd)"
fi

# uv managed Python
if [ -d "$HOME/.local/share/uv/python" ]; then
  _uv_python_bin="$(find "$HOME/.local/share/uv/python" -maxdepth 2 -name bin -type d | head -1)" 2>/dev/null
  export PATH="$PATH:${_uv_python_bin}"
  unset _uv_python_bin
fi

# Claude Code
if [ -d "$HOME/.claude/local/bin" ]; then
  export PATH="$HOME/.claude/local/bin:$PATH"
fi

# SOPS age key (macOS defaults to ~/Library/Application Support/; we use ~/.config/)
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

# direnv
if command -v direnv &>/dev/null; then
  eval "$(direnv hook zsh)"
fi
