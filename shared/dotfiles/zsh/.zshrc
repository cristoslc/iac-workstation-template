# Managed by iac-daily-driver-environments.
# Machine-specific overrides go in ~/.config/zsh/local.zsh (gitignored).

# History: commands prefixed with a space are not recorded.
# Protects against accidentally persisting secrets in shell history.
setopt HIST_IGNORE_SPACE

# Source all zsh config fragments.
# Shared, platform, secrets, and local files are all picked up by this glob.
for conf in "$HOME/.config/zsh/"*.zsh(N); do
  source "$conf"
done

# fzf keybindings and completion (Ctrl+R history, Ctrl+T files, Alt+C dirs)
if command -v fzf &>/dev/null; then
  eval "$(fzf --zsh 2>/dev/null)" || source <(fzf --zsh) 2>/dev/null || true
fi
