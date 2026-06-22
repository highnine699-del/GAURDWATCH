# GuardWatch v4.0 — Remote Access & High Availability

## Remote Access Configuration

GuardWatch v4.0 now supports secure remote access to the web dashboard.

### Security Features
- **Authentication Required**: Dashboard now requires username/password by default
- **IP Whitelisting**: Restrict access to specific IP addresses
- **HTTPS Support**: Optional SSL/TLS encryption for secure remote access
- **Remote Access Toggle**: Enable/disable remote access entirely

### Configuration

Edit `config.json` under the `dashboard` section:

```json
{
  "dashboard": {
    "enabled": true,
    "port": 5555,
    "host": "0.0.0.0",
    "require_auth": true,
    "username": "admin",
    "password": "guardwatch",
    "allow_remote": true,
    "allowed_hosts": [],
    "use_https": false,
    "ssl_cert": "",
    "ssl_key": ""
  }
}
```

### Settings Explained

- **require_auth**: Enable/disable authentication (default: true)
- **username**: Dashboard username (default: "admin")
- **password**: Dashboard password (default: "guardwatch")
- **allow_remote**: Allow remote connections (default: true)
- **allowed_hosts**: List of allowed IP addresses (empty = all IPs allowed)
- **use_https**: Enable HTTPS (default: false)
- **ssl_cert**: Path to SSL certificate file
- **ssl_key**: Path to SSL private key file

### Accessing Remotely

1. **HTTP Access**:
   ```
   http://YOUR_PC_IP:5555
   ```
   Login with username and password from config.

2. **HTTPS Access** (if enabled):
   ```
   https://YOUR_PC_IP:5555
   ```

### Security Recommendations

1. **Change Default Credentials**: Always change the default username/password
2. **Use HTTPS**: Enable HTTPS for production environments
3. **IP Whitelisting**: Restrict to specific IPs if possible
4. **Firewall**: Configure firewall to only allow necessary ports
5. **VPN**: Use VPN for remote access instead of exposing directly

### Setting Up HTTPS (Optional)

1. Generate SSL certificate:
   ```bash
   openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
   ```

2. Update config.json:
   ```json
   {
     "dashboard": {
       "use_https": true,
       "ssl_cert": "path/to/cert.pem",
       "ssl_key": "path/to/key.pem"
     }
   }
   ```

---

## Watchdog Mode (High Availability)

GuardWatch now includes a watchdog process that monitors and automatically restarts the main process on failure.

### Features
- **Automatic Restart**: Restarts GuardWatch if it crashes
- **Configurable Retries**: Set maximum restart attempts
- **Restart Delay**: Configurable delay between restart attempts
- **Logging**: Logs all restart events to watchdog.log

### Running with Watchdog

**Option 1: Using watchdog.bat**
```cmd
watchdog.bat
```

**Option 2: Direct Python**
```cmd
python watchdog.py --max-retries 10 --restart-delay 5
```

### Watchdog Arguments

- **--max-retries**: Maximum restart attempts (default: 5)
- **--restart-delay**: Delay between restarts in seconds (default: 10)

### Watchdog Log

All restart events are logged to `watchdog.log`:
```
[2024-06-22T09:00:00] Watchdog restart: Exit code 1 (attempt 1/10)
[2024-06-22T09:00:15] Watchdog restart: Exit code 1 (attempt 2/10)
```

### Auto-Start with Watchdog

To run GuardWatch with watchdog on Windows startup:

1. **Using Task Scheduler**:
   - Create task to run `watchdog.bat`
   - Trigger: At startup
   - Run with highest privileges

2. **Using Startup Folder**:
   - Copy `watchdog.bat` to `shell:startup`
   - Note: Console window will be visible

---

## Automatic Evidence Cleanup

GuardWatch now automatically deletes evidence older than 30 days (configurable).

### Cleanup Features
- **Startup Cleanup**: Runs cleanup when GuardWatch starts
- **Periodic Cleanup**: Runs cleanup at configurable intervals
- **Size Limit**: Removes oldest sessions if size limit exceeded
- **Compression**: Optionally compress old sessions before deletion

### Configuration

Edit `config.json` under the `retention` section:

```json
{
  "retention": {
    "enabled": true,
    "retain_days": 30,
    "compress_old": true,
    "max_size_gb": 50,
    "cleanup_on_startup": true,
    "cleanup_interval_hours": 24
  }
}
```

### Settings Explained

- **enabled**: Enable/disable retention policies
- **retain_days**: Keep evidence for this many days (default: 30)
- **compress_old**: Compress sessions before deletion
- **max_size_gb**: Maximum total evidence size in GB
- **cleanup_on_startup**: Run cleanup when GuardWatch starts
- **cleanup_interval_hours**: Hours between periodic cleanups

### How It Works

1. **Startup**: When GuardWatch starts, it immediately removes sessions older than `retain_days`
2. **Size Check**: If total evidence exceeds `max_size_gb`, oldest sessions are removed
3. **Periodic**: Every `cleanup_interval_hours`, cleanup runs again automatically
4. **Compression**: If `compress_old` is true, sessions are compressed to ZIP before deletion

### Manual Cleanup

You can also manually trigger cleanup:
```cmd
python main.py --clear
```

---

## Complete High Availability Setup

For maximum reliability:

1. **Use Watchdog Mode**: Run with `watchdog.bat`
2. **Enable Remote Access**: Configure dashboard for remote monitoring
3. **Secure with HTTPS**: Enable HTTPS for remote dashboard access
4. **Configure Cleanup**: Set appropriate retention policies
5. **Auto-Start**: Add watchdog to Windows startup

### Example Production Config

```json
{
  "dashboard": {
    "require_auth": true,
    "username": "your_secure_username",
    "password": "your_secure_password",
    "allow_remote": true,
    "allowed_hosts": ["192.168.1.100", "10.0.0.50"],
    "use_https": true,
    "ssl_cert": "/path/to/cert.pem",
    "ssl_key": "/path/to/key.pem"
  },
  "retention": {
    "enabled": true,
    "retain_days": 90,
    "compress_old": true,
    "max_size_gb": 100,
    "cleanup_on_startup": true,
    "cleanup_interval_hours": 12
  }
}
```

---

## Troubleshooting

### Remote Access Not Working

1. Check firewall settings - ensure port 5555 is allowed
2. Verify `host` is set to `0.0.0.0` in config
3. Check `allow_remote` is set to `true`
4. Verify authentication credentials
5. Check IP whitelist if `allowed_hosts` is configured

### Watchdog Not Restarting

1. Check `watchdog.log` for error messages
2. Verify Python is in PATH
3. Check max_retries hasn't been exceeded
4. Ensure main.py is in the same directory

### Cleanup Not Running

1. Verify `retention.enabled` is true
2. Check `cleanup_on_startup` is true
3. Verify evidence directory exists
4. Check session ID format (must be YYYYMMDD_HHMMSS)

---

**GuardWatch v4.0** — Now with remote access, high availability, and automatic cleanup.
