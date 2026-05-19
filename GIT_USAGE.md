# Git Usage

This workspace currently has `.git` mounted read-only by the execution
environment, so the repository is initialized with a separate Git directory:

```bash
git --git-dir=.gitdir --work-tree=. status
```

Useful commands:

```bash
git --git-dir=.gitdir --work-tree=. add .
git --git-dir=.gitdir --work-tree=. commit -m "initial reusable runpod comfy agent"
git --git-dir=.gitdir --work-tree=. status --short
```

Ignored project-specific assets:

```text
workflows/
runspecs/
sessions/
config/profiles.json
.env*
```

If this folder is moved to a normal filesystem without the read-only `.git`
mount, you can reinitialize with a standard `.git/` repository and keep the same
`.gitignore` rules.
