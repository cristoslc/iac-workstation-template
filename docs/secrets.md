# Secrets Management

All secrets are encrypted with SOPS + age. The repo is public — nothing sensitive is ever committed in plaintext.

## Setup

1. Generate an age keypair:
   ```bash
   age-keygen -o ~/.config/sops/age/keys.txt
   chmod 600 ~/.config/sops/age/keys.txt
   ```
   The public key is printed to stdout. Copy it.

2. Update `.sops.yaml` with your public key:
   ```yaml
   creation_rules:
     - path_regex: '.*/secrets/.*'
       age: 'age1your-public-key-here'
   ```

3. Encrypt placeholder files:
   ```bash
   sops -e -i shared/secrets/vars.sops.yml
   sops -e -i shared/secrets/dotfiles/zsh/.config/zsh/secrets.zsh.sops
   sops -e -i linux/secrets/vars.sops.yml
   sops -e -i macos/secrets/vars.sops.yml
   ```

## Daily Workflow

### Edit an encrypted file
```bash
make edit-secrets-shared    # Opens in $EDITOR, re-encrypts on save
make edit-secrets-linux
make edit-secrets-macos

# Or directly:
sops shared/secrets/vars.sops.yml
```

### Decrypt all secrets (for debugging)
```bash
make decrypt     # Decrypts to .decrypted/ dirs
make clean-secrets  # Wipe .decrypted/ dirs
```

## Key Distribution

The age private key must be placed at `~/.config/sops/age/keys.txt` on each machine **before** bootstrap runs.

Options:
- Copy via USB drive
- Paste from a secure note
- Store in 1Password and retrieve via `op read` (requires 1Password to be set up first)

## Key Rotation

1. Generate new keypair: `age-keygen -o new-keys.txt`
2. Update `.sops.yaml` with the new public key
3. Re-encrypt all files: `sops updatekeys <file>` for each encrypted file
4. Distribute the new private key to all machines
5. Delete old key from machines

## Security Notes

- Decrypted files live in `.decrypted/` dirs (gitignored). They exist on disk after bootstrap.
- Full-disk encryption is the mitigation for plaintext secrets on disk.
- The pre-commit hook verifies all `*.sops.*` files contain SOPS metadata before commit.
- Never commit `keys.txt` or any age private key material.
