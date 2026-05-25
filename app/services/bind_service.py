import os
import re
import json
import subprocess
import logging


logger = logging.getLogger(__name__)


class BindService:
    """Manages named.conf.local and rndc commands."""

    def __init__(self, config):
        self.named_conf_local = config["BIND_NAMED_CONF_LOCAL"]
        self.rndc_path = config.get("RNDC_PATH", "/usr/sbin/rndc")
        self.rndc_host = config.get("RNDC_HOST", "127.0.0.1")
        self.rndc_port = config.get("RNDC_PORT", 953)
        self.rndc_key = config.get("RNDC_KEY", "")
        self.zone_dir = config["BIND_ZONE_DIR"]
        self.log_dir = config.get("BIND_LOG_DIR", "/var/log/bind")
        self.replication_config = config.get("REPLICATION_CONFIG", "/data/replication.json")

    # -- named.conf.local management -----------------------------------

    def _read_config(self):
        if os.path.exists(self.named_conf_local):
            with open(self.named_conf_local, "r") as f:
                return f.read()
        return "// Managed by Zonerr\n"

    def _write_config(self, content):
        os.makedirs(os.path.dirname(self.named_conf_local), exist_ok=True)
        with open(self.named_conf_local, "w") as f:
            f.write(content)

    def add_zone_to_config(self, zone_name, zone_type="forward"):
        content = self._read_config()

        pattern = r'zone\s+"' + re.escape(zone_name) + r'"\s*\{'
        if re.search(pattern, content):
            logger.info("Zone '%s' already in named.conf.local, updating.", zone_name)
            content = self._remove_zone_block(content, zone_name)

        replication = self._load_replication()
        zone_block = self._build_zone_block(zone_name, replication)

        content = content.rstrip() + "\n\n" + zone_block + "\n"
        self._write_config(content)

    def remove_zone_from_config(self, zone_name):
        content = self._read_config()
        content = self._remove_zone_block(content, zone_name)
        self._write_config(content)

    def _remove_zone_block(self, content, zone_name):
        """Remove a zone block from the config string."""
        pattern = r'zone\s+"' + re.escape(zone_name) + r'"\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\};\s*'
        return re.sub(pattern, "", content, flags=re.DOTALL)

    def _build_zone_block(self, zone_name, replication=None):
        zone_file = os.path.join(self.zone_dir, "db." + zone_name)

        if replication and replication.get("role") == "slave":
            masters = "; ".join(replication.get("masters", []))
            block = 'zone "' + zone_name + '" {\n'
            block += '    type slave;\n'
            block += '    file "' + zone_file + '";\n'
            if masters:
                block += '    masters { ' + masters + '; };\n'
            block += '};'
        else:
            block = 'zone "' + zone_name + '" {\n'
            block += '    type master;\n'
            block += '    file "' + zone_file + '";\n'

            if replication:
                allow = replication.get("allow_transfer", [])
                notify = replication.get("also_notify", [])
                if allow:
                    allow_str = "; ".join(allow)
                    block += '    allow-transfer { ' + allow_str + '; };\n'
                else:
                    block += '    allow-transfer { none; };\n'
                if notify:
                    notify_str = "; ".join(notify)
                    block += '    also-notify { ' + notify_str + '; };\n'
                    block += '    notify yes;\n'
            else:
                block += '    allow-transfer { none; };\n'

            block += '};'
        return block

    def _load_replication(self):
        if os.path.exists(self.replication_config):
            with open(self.replication_config, "r") as f:
                return json.load(f)
        return None

    def apply_replication_config(self, config):
        """Rebuild all zone blocks in named.conf.local with new replication settings."""
        os.makedirs(os.path.dirname(self.replication_config), exist_ok=True)
        with open(self.replication_config, "w") as f:
            json.dump(config, f, indent=2)

        content = self._read_config()
        zone_pattern = r'zone\s+"([^"]+)"\s*\{'
        zone_names = re.findall(zone_pattern, content)

        new_content = "// Managed by Zonerr — do not edit manually\n"
        for zname in zone_names:
            block = self._build_zone_block(zname, config)
            new_content += "\n" + block + "\n"

        self._write_config(new_content)

    # -- rndc commands -------------------------------------------------

    def _rndc_cmd(self, *args):
        cmd = [self.rndc_path, "-s", self.rndc_host, "-p", str(self.rndc_port)]
        if self.rndc_key:
            cmd.extend(["-k", self.rndc_key])
        cmd.extend(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.warning("rndc command failed: %s\n%s", " ".join(cmd), result.stderr)
                return False, result.stderr.strip()
            return True, result.stdout.strip()
        except FileNotFoundError:
            msg = "rndc not found at " + self.rndc_path + ". BIND may not be installed or rndc path is wrong."
            logger.warning(msg)
            return False, msg
        except subprocess.TimeoutExpired:
            msg = "rndc command timed out."
            logger.warning(msg)
            return False, msg
        except Exception as e:
            logger.error("rndc error: %s", e)
            return False, str(e)

    def reload(self):
        success, msg = self._rndc_cmd("reload")
        if not success:
            logger.warning("rndc reload failed: %s — trying reconfig", msg)
            success2, msg2 = self._rndc_cmd("reconfig")
            if not success2:
                logger.warning("rndc reconfig also failed: %s", msg2)
        return success, msg

    def reload_zone(self, zone_name):
        return self._rndc_cmd("reload", zone_name)

    def get_status(self):
        success, output = self._rndc_cmd("status")
        if success:
            return output
        return "Could not connect to BIND:\n" + output

    def reconfig(self):
        """Reload named.conf changes only (no zone reload)."""
        return self._rndc_cmd("reconfig")

    def flush(self):
        """Flush the DNS resolver cache."""
        return self._rndc_cmd("flush")

    def stop(self):
        """Stop BIND. Docker restart policy will bring it back."""
        return self._rndc_cmd("stop")

    # -- log reading ---------------------------------------------------

    def get_log_files(self):
        """Return a list of available log files."""
        log_dir = getattr(self, 'log_dir', '/var/log/bind')
        files = []
        if os.path.isdir(log_dir):
            for fname in sorted(os.listdir(log_dir)):
                fpath = os.path.join(log_dir, fname)
                if os.path.isfile(fpath) and fname.endswith('.log'):
                    size = os.path.getsize(fpath)
                    files.append({"name": fname, "path": fpath, "size": size})
        return files

    def read_log(self, log_name, tail=200):
        """Read the last N lines of a log file."""
        log_dir = getattr(self, 'log_dir', '/var/log/bind')
        # Sanitize — prevent directory traversal
        safe_name = os.path.basename(log_name)
        fpath = os.path.join(log_dir, safe_name)

        if not os.path.isfile(fpath):
            return f"Log file '{safe_name}' not found."

        try:
            with open(fpath, "r") as f:
                lines = f.readlines()
            if tail and tail > 0:
                lines = lines[-tail:]
            return "".join(lines)
        except Exception as e:
            return f"Error reading log: {e}"
        
    # -- config file editing -------------------------------------------

    def read_config_file(self, filepath):
        """Read a BIND config file and return its contents."""
        if not os.path.isfile(filepath):
            return f"# File not found: {filepath}\n"
        with open(filepath, "r") as f:
            return f.read()

    def write_config_file(self, filepath, content):
        """
        Write content to a BIND config file.
        Creates a .bak backup before overwriting.
        Validates with named-checkconf before committing.
        """       
        # Normalize line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Backup
        if os.path.isfile(filepath):
            bak = filepath + ".bak"
            with open(filepath, "r") as src:
                original = src.read()
            with open(bak, "w") as dst:
                dst.write(original)

        # Write new content
        with open(filepath, "w") as f:
            f.write(content)

        # Validate — only for named.conf (full config check)
        if filepath.endswith("named.conf"):
            ok, msg = self.check_conf()
            if not ok:
                # Rollback from backup
                if os.path.isfile(filepath + ".bak"):
                    with open(filepath + ".bak", "r") as bak:
                        rollback = bak.read()
                    with open(filepath, "w") as f:
                        f.write(rollback)
                raise ValueError(f"named-checkconf failed (rolled back):\n{msg}")

    def check_conf(self):
        """Run named-checkconf and return (success, output)."""
        try:
            result = subprocess.run(
                ["named-checkconf", "/etc/bind/named.conf"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or result.stdout.strip()
            return True, "Configuration OK."
        except FileNotFoundError:
            return False, "named-checkconf not found."
        except subprocess.TimeoutExpired:
            return False, "named-checkconf timed out."
        except Exception as e:
            return False, str(e)

    def get_config_paths(self):
        """Return dict of editable config files and their paths."""
        return {
            "named.conf": "/etc/bind/named.conf",
            "rndc-controls.conf": "/etc/bind/rndc-controls.conf",
        }

    # -- dig query ------------------------------------------------------

    def dig_query(self, name, qtype="A", server=None, short=False, reverse=False):
        """Run a dig query and return the output."""
        cmd = ["dig"]

        if reverse:
            cmd.append("-x")
            cmd.append(name)
        else:
            cmd.append(name)
            cmd.append(qtype)

        if server:
            cmd.append("@" + server)
        else:
            cmd.append("@bind")

        if short:
            cmd.append("+short")
        else:
            cmd.append("+noall")
            cmd.append("+answer")
            cmd.append("+authority")
            cmd.append("+comments")
            cmd.append("+stats")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            return output.strip()
        except subprocess.TimeoutExpired:
            return "Query timed out after 10 seconds."
        except FileNotFoundError:
            return "dig not found. Is bind9-dnsutils installed?"
        except Exception as e:
            return f"Error: {e}"
        