# Fuzzball CLI on a Mac

Setup for the hackathon cluster at `fb-hack.civilfritz.net`, from download to a running job. Every command fits on one line. Paste one line at a time: a command split across lines, or one with a `\` before a space, reaches the CLI broken.

Sources:
- Download page: `https://ui.fb-hack.civilfritz.net/downloads/cli`
- Contexts and login: CIQ's Fuzzball docs, [Initial Login](https://docs.ciq.com/fuzzball/initial-configuration/initial-login), section "Creating Contexts and Logging In"
- Fuzzfile syntax: [Fuzzfile Syntax Guide](https://docs.ciq.com/fuzzball/appendices/workflow-syntax)
- This cluster's values: `https://ui.fb-hack.civilfritz.net/init.js` (`cliApiURL`, `cliAuthURL`)

## 1. Install

The download page's steps name the file `fuzzball-vv4.3.1-darwin-arm64`. Chrome saves it as `fuzzball-v4.3.1-darwin-arm64`, with one `v`.

```
mkdir -p ~/bin
```
```
mv ~/Downloads/fuzzball-v4.3.1-darwin-arm64 ~/bin/fuzzball
```
```
chmod +x ~/bin/fuzzball
```
```
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc
```
```
source ~/.zshrc
```

## 2. Let macOS run it

macOS blocks the file with "Apple could not verify 'fuzzball' is free of malware". The binary has no Apple developer signature and is not notarized, and Chrome marks every download with a quarantine flag. This command removes the flag:

```
xattr -d com.apple.quarantine ~/bin/fuzzball
```

Check: `fuzzball --version` prints the version.

## 3. Create a context

The download page's steps skip this step. Without it, `fuzzball login` fails with `no active context exists`.

A context is an entry in `~/.config/fuzzball/config.yaml` on your machine. It holds the API address, the sign-in URL (this cluster's Keycloak realm) and your login token. Each person creates their own; the name (`simulaxon` here) is local and any name works.

```
fuzzball context create simulaxon api.fb-hack.civilfritz.net https://auth.fb-hack.civilfritz.net/auth/realms/a4393007-90cc-40e3-9a51-6a58605d67aa fuzzball-cli
```

`context create` also makes the new context active. If a broken paste created a bad context, delete it and run the command again:

```
fuzzball context delete simulaxon
```

## 4. Log in

```
fuzzball login
```

A browser page opens for sign-in with the team account. Check:

```
fuzzball context show
```

It lists `Group Name: team13@fb-hack.local`.

## 5. Volumes

Volumes live on the cluster. Contexts do not affect them. The `team13` storage provisioner grants access to `team13@fb-hack.local` and the `team13` group, so every teammate signed in to that account or group sees the same volumes.

| Volume | Provisioner | Mount | Contents |
|---|---|---|---|
| `simulaxon-data` | `team13` | `/data` | Simulaxon weights, study data, predictions, log |
| `datasets` | `shared` | `/shared`, read-only | Organizers' topic datasets: `bio`, `geo`, `space`, `city`, `gov`, `finance` |

List them:

```
fuzzball volume list
```

## 6. Run the mount check

[../fuzzball/check-data.fz](../fuzzball/check-data.fz) mounts both volumes, makes the folders in [../data/README.md](../data/README.md) and lists both mounts.

```
fuzzball workflow validate fuzzball/check-data.fz
```
```
fuzzball workflow start fuzzball/check-data.fz
```

`start` prints a workflow ID, such as `e4b8c2c0-3ad2-4249-bc82-5374bcb882e0`. Every command below takes that ID in place of `<workflow-id>`, without the angle brackets. `fuzzball workflow list` shows the IDs again.

```
fuzzball workflow describe <workflow-id>
```
```
fuzzball workflow log <workflow-id> list
```

Check: the log lists `chunks log predictions studies weights` under `/data`.

## 7. Download weights

The five files in `fuzzball/weights/` each download one Hugging Face repo into `/data/weights`. Start one, wait for `Finished`, then start the next:

```
fuzzball workflow start -n weights-1 fuzzball/weights/1-tribev2.fz
```

A single workflow with every download in it stalled its volume stage, and Fuzzball cancelled it with `job stopped responding`.

The cluster's outside connection carries about 15 MB/s in total, shared by every team. One download gets about 10 MB/s; a parallel downloader in a second job got 5 MB/s beside it. Nemotron's 80 GB takes about 2 hours. Watch progress with:

```
python3 fuzzball/pull-status.py --watch 15
```

## 8. Copy files from your machine

Files that are not on the internet (the Spark's study data, this private repo) go in through a running job. Start `fuzzball/receive.fz`, then pipe a tar into it. `workflow exec` never passes the end of input to the command, so the receiving side stops after the tar's exact byte count:

```
fuzzball workflow start -n simulaxon-receive fuzzball/receive.fz
```
```
git archive --format=tar --prefix=simulaxon/ HEAD > /tmp/src.tar
```
```
fuzzball workflow exec <workflow-id> receive -- sh -c "mkdir -p /data/src && head -c $(stat -f %z /tmp/src.tar) | tar -C /data/src -xf -" < /tmp/src.tar
```

The command stays open after the copy finishes; stop it with Ctrl-C once the files are there.

## 9. Open the app

The app's endpoint uses the cluster's private certificate authority, so a browser warns about it. A port-forward opens it at `http://127.0.0.1:18791` instead:

```
fuzzball workflow port-forward <workflow-id> app-server 18791:8791
```

## 10. Find out why a workflow failed

| Command | Shows |
|---|---|
| `fuzzball workflow describe <workflow-id>` | The error and each stage's state |
| `fuzzball workflow events <workflow-id>` | Each stage's node (`Resources allocated (node: …)`) and whether `Stage started` followed |
| `fuzzball workflow log <workflow-id> <job-name>` | The job's output |
| `fuzzball workflow describe <workflow-id> -o json` | Stage IDs: the `"id"` in the block with the stage's `"name"` |
| `fuzzball workflow why <workflow-id> <stage-id>` | The scheduler's reason for that stage's state |
| `fuzzball node show <node-id>` | A node's health, attributed failures and running stages |

The status line can stay `STAGE_STATUS_UNSPECIFIED` after the stages were cancelled. `events` shows what happened.

To find a cause, change one thing per run and run one workflow at a time on the volume: the image reference, the image scheme (`docker://` or `oras://`), a volume or none. Rerun the unchanged file after any pass: a cluster fault that clears between two runs makes the second change look like the fix.

## Errors and fixes

| Error | Cause | Fix |
|---|---|---|
| "fuzzball" Not Opened | Quarantine flag on an unnotarized binary | Step 2 |
| `no active context exists` | No context created | Step 3 |
| `parse "http:// api.fb-hack…": invalid character " "` | `\` before a space in a joined paste | Paste the one-line command in step 3 |
| `zsh: no such file or directory: https://auth…` | Command split across two lines | Paste the one-line command in step 3 |
| `job stopped responding on node …` after about 10 minutes | A volume stage running many downloads at once | Step 7: one download per workflow |
| `no route to host` naming `database-postgresql`, `10.96.73.41:7331` or another `10.x` address | Cluster network fault | Report to the organizers with the workflow ID |
| `failed to probe image cache … lookup fuzzball-objectcache on 10.96.0.10:53: no such host` | Cluster DNS fault; every image and node fails the same way | Report to the organizers; no image change avoids it |
| `building images in a workflow is not enabled on this deployment` | The cluster turns off `images:` sections | Use a published image and put the rest on `/data` (`fuzzball/render-env.fz`) |
| `field on not found in type api.WorkflowDefinition_Policy_Retry` | `retry.on` is new in Fuzzball 4.4; the cluster runs 4.3.1 | Use `retry: {attempts: N}` |
| `could not use tcp port 8791: already used` | An earlier workflow still holds the port on that node | Stop the earlier workflow |
| `Could not set lock on file "/data/log/datasets.duckdb"` | An earlier app server still holds the DuckDB lock | Stop the earlier app workflow |
| `rm: can't remove …: Directory not empty` on `/data` | A process still has a file open there; NFS keeps it as `.nfs…` | Stop that process, then remove |
