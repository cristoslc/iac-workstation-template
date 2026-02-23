# Cross-platform shell functions.

# Create directory and cd into it
mkcd() {
  mkdir -p "$1" && cd "$1"
}

# Quick find file by name
ff() {
  find . -name "*$1*" 2>/dev/null
}

# SSH until host comes up (useful for rebooting remote machines)
ssh-until-up() {
  local host="$1"; shift
  false
  while [[ $? -ne 0 ]]; do
    ssh -o ConnectTimeout=5 "$host" "$@" || (sleep 5; false)
  done
}
