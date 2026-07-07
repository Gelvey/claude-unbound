# Freebuff2API Troubleshooting Guide

## Quick Diagnosis

### 1. Check if Docker is installed and running
```bash
docker info
```
If this fails, Docker is not installed or not running.

### 2. Check if Freebuff container exists
```bash
docker ps -a --filter name=freebuff2api
```

### 3. Check container logs
```bash
docker logs freebuff2api
```

---

## Common Issues and Fixes

### Issue: "Permission denied" when starting Freebuff

**Symptoms:**
- Admin panel shows "⚠ Sudo Required" warning
- Docker commands fail with permission error

**Solution: Add user to docker group**
```bash
# Add your user to the docker group
sudo usermod -aG docker $USER

# Apply group changes (option 1 - log out and back in)
logout

# Apply group changes (option 2 - use newgrp)
newgrp docker

# Verify it works
docker info
```

**Why this happens:** Docker daemon runs as root. By default, only root and members of the `docker` group can interact with it.

---

### Issue: Container shows "Stopped" but admin says "Started"

**Cause:** This was a bug in the old code. The admin panel checked an in-memory variable instead of querying Docker.

**Solution:** Update to the latest version. The new code queries Docker directly via `docker inspect`.

**Verify with:**
```bash
docker ps --filter name=freebuff2api --format '{{.Status}}'
```
Should show "Up X minutes" if running.

---

### Issue: Container won't start - port already in use

**Symptoms:**
```
Error: Bind for 0.0.0.0:8080 failed: port is already allocated
```

**Solution:**
1. Find what's using the port:
   ```bash
   sudo lsof -i :8080
   # or
   sudo netstat -tulpn | grep 8080
   ```

2. Stop the conflicting service or change Freebuff port in admin panel settings

3. If you need to kill the process:
   ```bash
   sudo kill -9 <PID>
   ```

---

### Issue: Container starts but immediately exits

**Check logs:**
```bash
docker logs freebuff2api
```

**Common causes:**
1. **Invalid credentials:** Check if auth tokens are valid
   ```bash
   cat ~/.config/manicode/credentials.json
   ```

2. **Config file missing/broken:** Regenerate with "Setup" button in admin panel

3. **Network issues:** Container can't reach upstream servers

**Fix:**
1. Click "Setup" in admin panel to regenerate config
2. Check credentials are valid
3. Verify container has network access:
   ```bash
   docker exec freebuff2api ping -c 3 google.com
   ```

---

### Issue: Health check fails even though container is running

**Check if port is exposed correctly:**
```bash
docker port freebuff2api
```

**Test health endpoint manually:**
```bash
curl -v http://127.0.0.1:8080/healthz
```

**Common issues:**
1. Port not mapped: Check docker run command includes `-p 8080:8080`
2. Container listening on wrong port: Check config.json LISTEN_ADDR
3. Firewall blocking localhost: Rare, but check iptables

---

### Issue: Models won't discover

**Test model endpoint:**
```bash
curl -s http://127.0.0.1:8080/v1/models | jq .
```

**Common causes:**
1. Freebuff instance not running (check health first)
2. Auth tokens not configured
3. Upstream API unreachable from container

---

## Manual Docker Commands

### Start container manually
```bash
docker run -d \
  --name freebuff2api \
  -p 8080:8080 \
  -v ~/.fcc/freebuff2api/config.json:/app/config.json:ro \
  ghcr.io/gelvey/freebuff2api:latest \
  -config /app/config.json
```

### Stop and remove container
```bash
docker stop freebuff2api
docker rm freebuff2api
```

### Restart container
```bash
docker restart freebuff2api
```

### View container details
```bash
docker inspect freebuff2api
```

### Pull latest image
```bash
docker pull ghcr.io/gelvey/freebuff2api:latest
```

---

## Getting Help

1. **Check admin panel Health & Status section** - shows Docker container state + health endpoint

2. **Check Docker logs:**
   ```bash
   docker logs --tail 100 freebuff2api
   ```

3. **Test Docker works independently:**
   ```bash
   docker run --rm hello-world
   ```

4. **Verify credentials are configured:**
   ```bash
   cat ~/.config/manicode/credentials.json
   ```

5. **Regenerate config from scratch:**
   - Click "Setup" in admin panel
   - Or manually edit `~/.fcc/freebuff2api/config.json`

---

## Advanced: Building from Source (if Docker unavailable)

If you can't use Docker, Freebuff can be built from source with Go:

### Install Go
```bash
# macOS
brew install go

# Linux
sudo apt install golang-go  # Debian/Ubuntu
sudo dnf install golang     # Fedora
```

### Build Freebuff2API
```bash
cd ~/.fcc
git clone --depth=1 https://github.com/Quorinex/Freebuff2API.git freebuff2api
cd freebuff2api
CGO_ENABLED=0 go build -ldflags="-s -w" -trimpath -o Freebuff2API .
```

### Run binary
```bash
./Freebuff2API -config config.json
```

---

## Need More Help?

Check the [FREEBUFF_FIXES_SUMMARY.md](./FREEBUFF_FIXES_SUMMARY.md) for technical details about the recent overhaul.
